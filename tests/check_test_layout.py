"""Fail when tracked executable tests live outside the root tests directory."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SKILL_EVAL = re.compile(r"^skills/[^/]+/evals/cases\.json$")
SKILL_EVAL_PREFIX = re.compile(r"^skills/[^/]+/evals/")
TEST_PATTERNS = (
    ("Python test module", re.compile(r"^(?:test_.*|.*_test)\.py$")),
    (
        "JavaScript/TypeScript test module",
        re.compile(r"^.*\.(?:test|spec)\.(?:js|jsx|ts|tsx|mjs|mts|cjs|cts)$"),
    ),
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
    for kind, pattern in TEST_PATTERNS:
        if pattern.fullmatch(basename):
            return kind
    return None


def main() -> int:
    tracked = _tracked_paths()
    violations: list[tuple[str, str]] = []
    for path in tracked:
        if path.startswith("tests/") or ALLOWED_SKILL_EVAL.fullmatch(path):
            continue
        kind = _kind(path)
        if kind:
            violations.append((path, kind))

    if violations:
        print("Executable tests must be tracked under tests/:")
        for path, kind in violations:
            print(f"- {path} ({kind})")
        return 1

    print(f"OK: {len(tracked)} tracked paths satisfy the root test boundary.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
