"""Deterministic, read-only checks for the P3-A TikTok no-live-write boundary."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

_HTTP_ROUTE_METHODS = {"delete", "get", "patch", "post", "put"}
_MUTATING_HTTP_METHODS = {"delete", "patch", "post", "put", "request", "send"}
_HTTP_CLIENT_FACTORY_NAMES = {"AsyncClient", "Client", "Session"}
_REVIEWED_HTTP_MODULES = {"httpx", "requests"}
_UNREVIEWED_NETWORK_MODULES = {"aiohttp", "http.client", "urllib.request", "urllib3"}

# P3-A permits internal bootstrap, authorization, release and Sandbox operations, but it
# freezes every externally reachable TikTok route. A new route therefore needs an explicit
# security review before this release gate can pass again.
_APPROVED_TIKTOK_ROUTES = {
    ("GET", "/authorizations/callback"),
    ("GET", "/authorizations/official/callback"),
    ("GET", "/connector/read"),
    ("GET", "/creator-pool"),
    ("GET", "/data-validation"),
    ("GET", "/history"),
    ("GET", "/mock/authorize"),
    ("GET", "/mock-sop-replays/exception-matrix"),
    ("GET", "/overview"),
    ("GET", "/production-readiness"),
    ("GET", "/release-preflight"),
    ("GET", "/shadow/status"),
    ("POST", "/authorizations/exchange"),
    ("POST", "/authorizations/{authorization_id}/revoke"),
    ("POST", "/authorizations/official/start"),
    ("POST", "/authorizations/start"),
    ("POST", "/bootstrap"),
    ("POST", "/bootstrap-assets"),
    ("POST", "/creator-claims/{entry_id}"),
    ("POST", "/creator-assignments/{entry_id}"),
    ("POST", "/creator-follow-ups/{entry_id}"),
    ("POST", "/creator-pool"),
    ("POST", "/creator-reflow-approvals/{entry_id}"),
    ("POST", "/creator-reflow-proposals/{entry_id}"),
    ("POST", "/data-validation/bootstrap"),
    ("POST", "/data-validation/runs/mock"),
    ("POST", "/data-validation/runs/recorded"),
    ("POST", "/history/confirm"),
    ("POST", "/history/facts/{fact_id}/reconciliations"),
    ("POST", "/history/import"),
    ("POST", "/m2m/verify"),
    ("POST", "/memberships/reconcile"),
    ("POST", "/mock-sop-replays/execute-sandbox"),
    ("POST", "/mock-sop-replays/run"),
    ("POST", "/releases/publish"),
    ("POST", "/shadow/evaluations"),
    ("POST", "/shadow/heartbeat"),
    ("POST", "/shadow/start"),
    ("PUT", "/data-validation/capability-evidence/{entry_code}"),
    ("PUT", "/data-validation/field-contracts/{field_code}"),
    ("PUT", "/data-validation/pilot-scope"),
}

_EXPECTED_SKILL_IDS = {
    "joukir-ad-inspection",
    "joukir-content-angle",
    "joukir-creative-qc",
    "joukir-creator-match",
    "joukir-creator-profile",
    "joukir-live-plan",
    "joukir-policy-check",
    "joukir-product-truth",
    "joukir-shop-health",
    "joukir-short-video-script",
    "joukir-storyboard",
    "joukir-tiktok-account-audit",
}

_EXPECTED_TIKTOK_PYTHON_FILES = {
    "backend/app/api/tiktok.py",
    "backend/app/tiktok/__init__.py",
    "backend/app/tiktok/connector.py",
    "backend/app/tiktok/creator_pool.py",
    "backend/app/tiktok/data_validation.py",
    "backend/app/tiktok/mock_replay.py",
    "backend/app/tiktok/oauth.py",
    "backend/app/tiktok/official.py",
    "backend/app/tiktok/p3b1_history.py",
    "backend/app/tiktok/recorded_validation.py",
    "backend/app/tiktok/release_evidence.py",
    "backend/app/tiktok/release_gate.py",
    "backend/app/tiktok/schema.py",
    "backend/app/tiktok/service.py",
    "backend/app/tiktok/shadow.py",
    "backend/app/tiktok/shadow_worker.py",
}


def _default_repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("top-level JSON value must be an object")
    return value


def _parse_python(path: Path, repository_root: Path) -> ast.Module:
    relative = path.relative_to(repository_root).as_posix()
    return ast.parse(path.read_text(encoding="utf-8"), filename=relative)


def _route_surface(path: Path, repository_root: Path) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for node in ast.walk(_parse_python(path, repository_root)):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            owner = decorator.func.value
            method = decorator.func.attr.lower()
            if (
                not isinstance(owner, ast.Name)
                or owner.id != "router"
                or method not in _HTTP_ROUTE_METHODS
                or not decorator.args
                or not isinstance(decorator.args[0], ast.Constant)
                or not isinstance(decorator.args[0].value, str)
            ):
                continue
            routes.add((method.upper(), decorator.args[0].value))
    return routes


def _http_client_names(tree: ast.Module) -> set[str]:
    module_aliases = _http_module_aliases(tree)
    names: set[str] = set()
    for node in ast.walk(tree):
        candidates: list[tuple[ast.AST, ast.AST | None]] = []
        if isinstance(node, (ast.AsyncWith, ast.With)):
            candidates.extend((item.context_expr, item.optional_vars) for item in node.items)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            candidates.extend((node.value, target) for target in targets)
        for expression, target in candidates:
            if not isinstance(expression, ast.Call) or not isinstance(expression.func, ast.Attribute):
                continue
            owner = expression.func.value
            if (
                isinstance(owner, ast.Name)
                and owner.id in module_aliases
                and expression.func.attr in _HTTP_CLIENT_FACTORY_NAMES
                and isinstance(target, ast.Name)
            ):
                names.add(target.id)
    return names


def _http_module_aliases(tree: ast.Module) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import):
            continue
        for imported in node.names:
            if imported.name in _REVIEWED_HTTP_MODULES:
                aliases.add(imported.asname or imported.name)
    return aliases


def _unreviewed_network_imports(path: Path, repository_root: Path) -> list[str]:
    findings: list[str] = []
    relative = path.relative_to(repository_root).as_posix()
    for node in ast.walk(_parse_python(path, repository_root)):
        names = [item.name for item in node.names] if isinstance(node, ast.Import) else []
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
        for name in names:
            if name in _UNREVIEWED_NETWORK_MODULES:
                findings.append(f"{relative}:{node.lineno}:{name}")
    return findings


def _mutating_http_calls(path: Path, repository_root: Path) -> list[str]:
    tree = _parse_python(path, repository_root)
    clients = _http_client_names(tree)
    module_aliases = _http_module_aliases(tree)
    findings: list[str] = []
    relative = path.relative_to(repository_root).as_posix()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        method = node.func.attr.lower()
        if method not in _MUTATING_HTTP_METHODS:
            continue
        owner = node.func.value
        is_client_call = isinstance(owner, ast.Name) and owner.id in clients
        is_module_call = isinstance(owner, ast.Name) and owner.id in module_aliases
        is_inline_client_call = (
            isinstance(owner, ast.Call)
            and isinstance(owner.func, ast.Attribute)
            and isinstance(owner.func.value, ast.Name)
            and owner.func.value.id in module_aliases
            and owner.func.attr in _HTTP_CLIENT_FACTORY_NAMES
        )
        if is_client_call or is_module_call or is_inline_client_call:
            findings.append(f"{relative}:{node.lineno}:{method.upper()}")
    return findings


def _business_execution_imports(path: Path, repository_root: Path) -> list[str]:
    findings: list[str] = []
    relative = path.relative_to(repository_root).as_posix()
    for node in ast.walk(_parse_python(path, repository_root)):
        module = node.module if isinstance(node, ast.ImportFrom) else None
        if module and module.startswith("app.business_execution"):
            findings.append(f"{relative}:{node.lineno}:{module}")
    return findings


def verify_tiktok_live_write_disabled(repository_root: Path | None = None) -> dict[str, Any]:
    """Audit the frozen API, outbound HTTP verbs and Skill declarations without side effects."""

    root = (repository_root or _default_repository_root()).resolve()
    issues: list[str] = []
    api_path = root / "backend" / "app" / "api" / "tiktok.py"
    tiktok_path = root / "backend" / "app" / "tiktok"
    registry_path = root / "skills" / "joukir-tiktok-pack" / "registry.json"

    try:
        routes = _route_surface(api_path, root)
    except (OSError, SyntaxError, ValueError) as exc:
        routes = set()
        issues.append(f"route_surface_unreadable:{type(exc).__name__}")
    else:
        unexpected_routes = sorted(routes - _APPROVED_TIKTOK_ROUTES)
        missing_routes = sorted(_APPROVED_TIKTOK_ROUTES - routes)
        issues.extend(f"unreviewed_tiktok_route:{method} {path}" for method, path in unexpected_routes)
        issues.extend(f"missing_frozen_tiktok_route:{method} {path}" for method, path in missing_routes)

    python_files = sorted([api_path, *tiktok_path.glob("*.py")])
    python_surface = {path.relative_to(root).as_posix() for path in python_files}
    issues.extend(
        f"missing_tiktok_python_surface:{path}"
        for path in sorted(_EXPECTED_TIKTOK_PYTHON_FILES - python_surface)
    )
    issues.extend(
        f"unreviewed_tiktok_python_surface:{path}"
        for path in sorted(python_surface - _EXPECTED_TIKTOK_PYTHON_FILES)
    )
    for path in python_files:
        try:
            issues.extend(f"outbound_http_mutation:{item}" for item in _mutating_http_calls(path, root))
            issues.extend(
                f"unreviewed_network_dependency:{item}"
                for item in _unreviewed_network_imports(path, root)
            )
            issues.extend(
                f"business_execution_surface:{item}"
                for item in _business_execution_imports(path, root)
            )
        except (OSError, SyntaxError, ValueError) as exc:
            relative = path.relative_to(root).as_posix()
            issues.append(f"python_surface_unreadable:{relative}:{type(exc).__name__}")

    skill_ids: set[str] = set()
    try:
        registry = _read_json(registry_path)
        if registry.get("external_write") is not False:
            issues.append("skill_registry_external_write_not_false")
        entries = registry.get("skills")
        if not isinstance(entries, list):
            raise TypeError("skills must be a list")
        skills_root = (root / "skills").resolve()
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("skill_id"), str):
                issues.append("skill_registry_entry_invalid")
                continue
            skill_id = entry["skill_id"]
            skill_ids.add(skill_id)
            skill_dir = (registry_path.parent / str(entry.get("path", ""))).resolve()
            if not skill_dir.is_relative_to(skills_root):
                issues.append(f"skill_path_outside_repository:{skill_id}")
                continue
            try:
                manifest = _read_json(skill_dir / "manifest.json")
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                issues.append(f"skill_manifest_unreadable:{skill_id}:{type(exc).__name__}")
                continue
            if manifest.get("skill_id") != skill_id:
                issues.append(f"skill_manifest_id_mismatch:{skill_id}")
            if manifest.get("external_write") is not False:
                issues.append(f"skill_external_write_not_false:{skill_id}")
        missing = sorted(_EXPECTED_SKILL_IDS - skill_ids)
        extra = sorted(skill_ids - _EXPECTED_SKILL_IDS)
        issues.extend(f"skill_missing:{skill_id}" for skill_id in missing)
        issues.extend(f"skill_unreviewed:{skill_id}" for skill_id in extra)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        issues.append(f"skill_registry_unreadable:{type(exc).__name__}")

    return {
        "ok": not issues,
        "gate": "tiktok_live_write_disabled",
        "route_count": len(routes),
        "skill_count": len(skill_ids),
        "python_file_count": len(python_files),
        "issues": sorted(set(issues)),
    }
