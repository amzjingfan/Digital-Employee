from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import casbin
from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.db import get_session
from app.db.models import (
    AuthorizationDecision,
    AuthorizationPolicyRelease,
    BusinessResource,
    BusinessResourceScope,
    User,
)
from app.security.auth import get_current_user

ENTERPRISE_CAPABILITY_OBJECTS: dict[str, str] = {
    "agents": "/api/enterprise/agents",
    "teams": "/api/enterprise/teams",
    "channels": "/api/enterprise/channels",
    "scheduled_tasks": "/api/enterprise/scheduled-tasks",
    "memories": "/api/enterprise/memories",
    "feedback": "/api/enterprise/feedback",
    "knowledge": "/api/enterprise/knowledge",
    "general_skills": "/api/enterprise/general-skills",
    "skills": "/api/enterprise/skills",
    "tools": "/api/enterprise/tools",
    "models": "/api/enterprise/model-configs",
    "runtime_settings": "/api/enterprise/ui-config",
    "identity_roles": "/api/enterprise/identity-role-mappings",
    "authorization": "/api/enterprise/authorization-decisions",
    "business_resources": "/api/enterprise/business-resources",
    "bi": "/api/enterprise/bi",
    "operations_reports": "/api/enterprise/operations-reports",
    "work_tasks": "/api/enterprise/work-tasks",
    "tiktok": "/api/enterprise/tiktok",
}

_CAPABILITY_ACTIONS: tuple[tuple[str, str, str], ...] = (
    ("view", "GET", ""),
    ("create", "POST", ""),
    ("update", "PATCH", "/resource"),
    ("delete", "DELETE", "/resource"),
)


@dataclass(frozen=True)
class AuthorizationResult:
    allowed: bool
    role: str
    reason: str
    policy_version: str


@dataclass(frozen=True)
class ContextPolicy:
    subject: str
    tenant_id: str
    department_id: str
    store_id: str
    resource_id: str
    action_pattern: str
    effect: str = "allow"


CONTEXT_MODEL = """
[request_definition]
r = sub, tenant, department, store, resource, act

[policy_definition]
p = sub, tenant, department, store, resource, act, eft

[policy_effect]
e = some(where (p.eft == allow)) && !some(where (p.eft == deny))

[matchers]
m = r.sub == p.sub && r.tenant == p.tenant && (p.department == "*" || r.department == p.department) && (p.store == "*" || r.store == p.store) && (p.resource == "*" || r.resource == p.resource) && regexMatch(r.act, p.act)
"""

POLICY_SUBJECTS = {
    "tenant_admin",
    "tenant_member",
    "operations_supervisor",
    "after_sales_specialist",
    "listing_compliance_specialist",
    "logistics_exception_specialist",
    "advertising_inspection_specialist",
    "designer",
    "procurement_specialist",
    "tiktok_bd_specialist",
    "tiktok_content_specialist",
    "tiktok_shop_operator",
    "tiktok_media_buyer",
    "tiktok_tap_manager",
    "tiktok_live_operator",
}


def authorize(
    settings: Settings,
    *,
    user: User,
    object_path: str,
    action: str,
    db: Session | None = None,
) -> AuthorizationResult:
    if not settings.casbin_enabled:
        return AuthorizationResult(
            allowed=True,
            role=_policy_role(user),
            reason="casbin_disabled",
            policy_version="disabled",
        )

    model_path, policy_path = _policy_paths(settings)
    active_release = _active_policy_release(db, user.tenant_id) if db else None
    if active_release:
        enforcer = _load_text_enforcer(
            str(model_path),
            active_release.policy_digest,
            active_release.policy_text,
        )
        policy_version = f"r{active_release.version}:{active_release.policy_digest[:12]}"
    else:
        enforcer, policy_version = _load_enforcer(str(model_path), str(policy_path))
    role = _policy_role(user)
    allowed, explanation = enforcer.enforce_ex(
        role,
        user.tenant_id,
        object_path,
        action.upper(),
    )
    reason = _decision_reason(bool(allowed), explanation)
    return AuthorizationResult(
        allowed=bool(allowed),
        role=role,
        reason=reason,
        policy_version=policy_version,
    )


def enterprise_capabilities(
    settings: Settings,
    *,
    user: User,
    db: Session | None = None,
) -> dict[str, list[str]]:
    """Return a UI capability manifest derived from the active Casbin policy.

    The manifest improves navigation and read-only UX. API authorization remains
    authoritative and is still evaluated and audited for every enterprise request.
    """
    capabilities: dict[str, list[str]] = {}
    for module, object_path in ENTERPRISE_CAPABILITY_OBJECTS.items():
        allowed_actions = [
            capability
            for capability, method, suffix in _CAPABILITY_ACTIONS
            if authorize(
                settings,
                user=user,
                object_path=f"{object_path}{suffix}",
                action=method,
                db=db,
            ).allowed
        ]
        if allowed_actions:
            capabilities[module] = allowed_actions
    capabilities["accounts"] = ["view", "create", "update", "delete"] if user.role == "admin" else []
    return capabilities


def require_enterprise_permission(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> User:
    result = authorize(
        get_settings(),
        user=current_user,
        object_path=request.url.path,
        action=request.method,
        db=db,
    )
    request_id = str(getattr(request.state, "request_id", "")) or f"req_{uuid4().hex}"
    request.state.request_id = request_id
    store_id = (
        (request.query_params.get("store_id") or "")[:128]
        if "query_string" in request.scope
        else ""
    )
    db.add(
        AuthorizationDecision(
            tenant_id=current_user.tenant_id,
            subject_id=current_user.id,
            role=result.role,
            department_id=(current_user.business_role or "")[:128],
            store_id=store_id,
            resource_type="api",
            object=request.url.path[:512],
            action=request.method.upper()[:16],
            effect="allow" if result.allowed else "deny",
            reason=result.reason,
            policy_version=result.policy_version,
            request_id=request_id,
        )
    )
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Authorization audit is unavailable") from exc
    if not result.allowed:
        raise HTTPException(status_code=403, detail="Permission denied")
    return current_user


def clear_authorization_cache() -> None:
    _load_enforcer.cache_clear()
    _load_text_enforcer.cache_clear()


def default_policy_text(settings: Settings) -> str:
    _, policy_path = _policy_paths(settings)
    return policy_path.read_text(encoding="utf-8")


def policy_digest(policy_text: str) -> str:
    return hashlib.sha256(policy_text.encode("utf-8")).hexdigest()


def validate_policy_text(
    settings: Settings,
    *,
    tenant_id: str,
    policy_text: str,
) -> dict[str, object]:
    encoded = policy_text.encode("utf-8")
    if not encoded or len(encoded) > 128 * 1024:
        raise ValueError("Policy must contain 1 to 131072 UTF-8 bytes")
    rules = _parse_policy_rules(policy_text, tenant_id=tenant_id)
    if not rules:
        raise ValueError("Policy must contain at least one rule")
    if len(rules) > 1000:
        raise ValueError("Policy cannot contain more than 1000 rules")
    model_path, _ = _policy_paths(settings)
    digest = policy_digest(policy_text)
    enforcer = _load_text_enforcer(str(model_path), digest, policy_text)
    safety_checks = (
        ("/api/enterprise/agents", "GET"),
        ("/api/enterprise/agents", "POST"),
        ("/api/enterprise/authorization-policies", "GET"),
        ("/api/enterprise/authorization-policies/release", "POST"),
        ("/api/enterprise/authorization-policies/release", "PUT"),
        ("/api/enterprise/authorization-policies/release", "DELETE"),
    )
    if not all(
        enforcer.enforce("tenant_admin", tenant_id, object_path, action)
        for object_path, action in safety_checks
    ):
        raise ValueError("Policy must preserve tenant administrator recovery access")
    return {"valid": True, "rule_count": len(rules), "policy_digest": digest}


def authorize_context(
    *,
    policies: list[ContextPolicy],
    subject_type: str,
    role: str,
    tenant_id: str,
    department_id: str,
    store_id: str,
    resource_id: str,
    action: str,
) -> AuthorizationResult:
    if subject_type not in {"human", "service"}:
        return AuthorizationResult(False, role, "unknown_subject_type", "context:invalid")
    subject = role if subject_type == "human" else f"service:{role}"
    model = casbin.Model()
    model.load_model_from_text(CONTEXT_MODEL)
    enforcer = casbin.Enforcer(model)
    canonical: list[str] = []
    for policy in policies:
        values = (
            policy.subject,
            policy.tenant_id,
            policy.department_id,
            policy.store_id,
            policy.resource_id,
            policy.action_pattern,
            policy.effect,
        )
        enforcer.add_policy(*values)
        canonical.append("\x1f".join(values))
    scope_digest = hashlib.sha256("\n".join(sorted(canonical)).encode("utf-8")).hexdigest()[:16]
    allowed, explanation = enforcer.enforce_ex(
        subject,
        tenant_id,
        department_id,
        store_id,
        resource_id,
        action.upper(),
    )
    return AuthorizationResult(
        bool(allowed),
        role,
        _decision_reason(bool(allowed), explanation),
        f"context:{scope_digest}",
    )


def authorize_business_resource(
    settings: Settings,
    *,
    db: Session,
    user: User,
    resource: BusinessResource,
    action: str,
    subject_type: str = "human",
) -> AuthorizationResult:
    role = _policy_role(user)
    if not settings.casbin_enabled:
        return AuthorizationResult(True, role, "casbin_disabled", "disabled")
    policies: list[ContextPolicy] = []
    if role in {"tenant_admin", "operations_supervisor"}:
        for policy_subject in (role, f"service:{role}"):
            policies.append(
                ContextPolicy(
                    subject=policy_subject,
                    tenant_id=resource.tenant_id,
                    department_id="*",
                    store_id="*",
                    resource_id="*",
                    action_pattern="(READ|REQUEST)",
                )
            )
    scopes = db.exec(
        select(BusinessResourceScope).where(
            BusinessResourceScope.tenant_id == resource.tenant_id,
            BusinessResourceScope.resource_id == resource.id,
        )
    ).all()
    for scope in scopes:
        action_pattern = "READ" if scope.access_level == "viewer" else "(READ|REQUEST)"
        for policy_subject in (scope.business_role, f"service:{scope.business_role}"):
            policies.append(
                ContextPolicy(
                    subject=policy_subject,
                    tenant_id=resource.tenant_id,
                    department_id=scope.business_role,
                    store_id=resource.code if resource.resource_type == "store" else "*",
                    resource_id=resource.id,
                    action_pattern=action_pattern,
                )
            )
    return authorize_context(
        policies=policies,
        subject_type=subject_type,
        role=role,
        tenant_id=user.tenant_id,
        department_id=user.business_role or role,
        store_id=resource.code if resource.resource_type == "store" else "*",
        resource_id=resource.id,
        action=action,
    )


def _policy_role(user: User) -> str:
    if user.role == "admin":
        return "tenant_admin"
    business_role = (user.business_role or "").strip()
    if business_role in {
        "operations_supervisor",
        "after_sales_specialist",
        "listing_compliance_specialist",
        "logistics_exception_specialist",
        "advertising_inspection_specialist",
        "designer",
        "procurement_specialist",
        "tiktok_bd_specialist",
        "tiktok_content_specialist",
        "tiktok_shop_operator",
        "tiktok_media_buyer",
        "tiktok_tap_manager",
        "tiktok_live_operator",
    }:
        return business_role
    if user.role == "member":
        return "tenant_member"
    return "tenant_unknown"


def _policy_paths(settings: Settings) -> tuple[Path, Path]:
    root = Path(__file__).resolve().parent
    model = Path(settings.casbin_model_path).resolve() if settings.casbin_model_path else root / "casbin_model.conf"
    policy = (
        Path(settings.casbin_policy_path).resolve()
        if settings.casbin_policy_path
        else root / "casbin_policy.csv"
    )
    if not model.is_file() or not policy.is_file():
        raise HTTPException(status_code=503, detail="Authorization policy is unavailable")
    return model, policy


@lru_cache(maxsize=4)
def _load_enforcer(model_path: str, policy_path: str) -> tuple[casbin.Enforcer, str]:
    model_bytes = Path(model_path).read_bytes()
    policy_bytes = Path(policy_path).read_bytes()
    policy_version = hashlib.sha256(model_bytes + b"\0" + policy_bytes).hexdigest()[:16]
    return casbin.Enforcer(model_path, policy_path), policy_version


@lru_cache(maxsize=64)
def _load_text_enforcer(
    model_path: str,
    digest: str,
    policy_text: str,
) -> casbin.Enforcer:
    del digest
    model = casbin.Model()
    model.load_model(model_path)
    enforcer = casbin.Enforcer(model)
    for rule in _parse_policy_rules(policy_text):
        enforcer.add_policy(*rule)
    return enforcer


def _parse_policy_rules(
    policy_text: str,
    *,
    tenant_id: str | None = None,
) -> list[list[str]]:
    rules: list[list[str]] = []
    for line_number, raw_line in enumerate(io.StringIO(policy_text), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        cells = [cell.strip() for cell in next(csv.reader([line], skipinitialspace=True))]
        if len(cells) != 6 or cells[0] != "p":
            raise ValueError(f"Invalid Casbin policy rule at line {line_number}")
        subject, domain, object_path, action_pattern, effect = cells[1:]
        if subject not in POLICY_SUBJECTS:
            raise ValueError(f"Unsupported policy subject at line {line_number}: {subject}")
        if tenant_id is not None and domain not in {"*", tenant_id}:
            raise ValueError(f"Policy domain escapes the current tenant at line {line_number}")
        if not object_path.startswith("/api/enterprise/"):
            raise ValueError(f"Policy object must be an enterprise API path at line {line_number}")
        try:
            re.compile(action_pattern)
        except re.error as exc:
            raise ValueError(f"Invalid action expression at line {line_number}") from exc
        if effect not in {"allow", "deny"}:
            raise ValueError(f"Invalid policy effect at line {line_number}")
        rules.append([subject, domain, object_path, action_pattern, effect])
    return rules


def _active_policy_release(
    db: Session | None,
    tenant_id: str,
) -> AuthorizationPolicyRelease | None:
    if db is None:
        return None
    return db.exec(
        select(AuthorizationPolicyRelease)
        .where(
            AuthorizationPolicyRelease.tenant_id == tenant_id,
            AuthorizationPolicyRelease.status == "published",
        )
        .order_by(AuthorizationPolicyRelease.version.desc())
    ).first()


def _decision_reason(allowed: bool, explanation: list[str]) -> str:
    if explanation:
        effect = str(explanation[-1]).lower()
        if effect in {"allow", "deny"}:
            return f"matched_{effect}_policy"
    return "matched_allow_policy" if allowed else "no_matching_allow_policy"
