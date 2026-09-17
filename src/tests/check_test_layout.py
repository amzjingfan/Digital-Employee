"""Fail when tracked executable tests live outside ``src/tests``."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_ROOT_PREFIXES = (
    "backend/",
    "deploy/",
    "frontend-enterprise/",
    "packaging/",
    "scripts/",
    "skills/",
    "tests/",
)
ALLOWED_SKILL_EVAL = re.compile(r"^src/skills/[^/]+/evals/cases\.json$")
SKILL_EVAL_PREFIX = re.compile(r"^src/skills/[^/]+/evals/")
SUPPORTED_FRONTEND_TEST = re.compile(r"^.*\.test\.(?:ts|tsx)$")
FRONTEND_TEST_CANDIDATE = re.compile(
    r"^.*\.(?:test|spec)\.(?:js|jsx|ts|tsx|mjs|mts|cjs|cts)$"
)
UNSUPPORTED_FRONTEND_TEST = "unsupported frontend test filename"
TEST_PATTERNS = (
    ("Python test module", re.compile(r"^(?:test_.*|.*_test)\.py$")),
    ("frontend test module", SUPPORTED_FRONTEND_TEST),
    (
        "smoke runner",
        re.compile(r"^smoke[_-].*\.(?:py|sh|ps1|js|ts|mjs|cjs|bat|cmd)$"),
    ),
    (
        "Docker test script",
        re.compile(r"^_?docker[_-]test.*\.(?:py|sh|ps1|bat|cmd)$"),
    ),
    (
        "integration runner",
        re.compile(r"^run_.*_(?:e2e|replay)\.py$"),
    ),
)


def _tracked_paths() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return [
        raw.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        for raw in completed.stdout.split(b"\0")
        if raw
    ]


def _kind(path: str) -> str | None:
    if SKILL_EVAL_PREFIX.match(path):
        return "skill evaluation asset"
    basename = path.rsplit("/", 1)[-1]
    if FRONTEND_TEST_CANDIDATE.fullmatch(basename) and not SUPPORTED_FRONTEND_TEST.fullmatch(
        basename
    ):
        return UNSUPPORTED_FRONTEND_TEST
    for kind, pattern in TEST_PATTERNS:
        if pattern.fullmatch(basename):
            return kind
    return None


def main() -> int:
    tracked = _tracked_paths()
    violations: list[tuple[str, str]] = []
    for path in tracked:
        if path.startswith(FORBIDDEN_ROOT_PREFIXES):
            violations.append((path, "executable project path outside src/"))
            continue
        if ALLOWED_SKILL_EVAL.fullmatch(path):
            continue
        kind = _kind(path)
        if kind is None:
            continue
        if path.startswith("src/tests/") and kind != UNSUPPORTED_FRONTEND_TEST:
            continue
        violations.append((path, kind))

    if violations:
        print("Test layout violations:")
        for path, kind in violations:
            print(f"- {path} ({kind})")
        return 1

    print(f"OK: {len(tracked)} tracked paths satisfy the src/tests boundary.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
