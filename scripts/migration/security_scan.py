from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASELINE = "e0cb8df042b3a5f856c60b45cf7e9c2bafbc23b5"

PATTERNS = {
    "private_key_header": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", re.IGNORECASE
    ),
    "credential_url": re.compile(
        r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|amqp|https?)://"
        r"[^/\s:@]+:[^@\s/]+@",
        re.IGNORECASE,
    ),
    "known_token": re.compile(
        r"(?:\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|"
        r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b|\bsk_live_[A-Za-z0-9]{16,}\b)"
    ),
    "sensitive_assignment": re.compile(
        r"(?im)^\s*[A-Za-z_][A-Za-z0-9_]*(?:PASSWORD|PASSWD|TOKEN|SECRET|API_KEY|"
        r"DATABASE_URL|ACCESS_KEY|PRIVATE_KEY)[A-Za-z0-9_]*\s*[:=]\s*"
        r"(?!\s*(?:$|none\b|null\b|false\b|true\b|changeme\b|example\b|dummy\b|"
        r"placeholder\b|<))[^#\r\n]{4,}\r?$"
    ),
}

ARTIFACT_SEGMENTS = {
    ".dev",
    ".venv",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
}
ARTIFACT_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
    ".pid",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
}
ALLOWED_ARTIFACT_PATHS = {"frontend-enterprise/.env.example"}


def git(*args: str) -> bytes:
    return subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=REPO,
        check=True,
        capture_output=True,
    ).stdout


def commit_files(treeish: str) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    records = git("ls-tree", "-r", "-z", "--full-tree", treeish).split(b"\0")
    for record in records:
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        _mode, object_type, blob = metadata.decode("ascii").split()
        if object_type != "blob":
            continue
        path = raw_path.decode("utf-8", errors="surrogateescape")
        result[path] = git("cat-file", "blob", blob)
    return result


def worktree_files() -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    paths = git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0")
    for raw_path in paths:
        if not raw_path:
            continue
        path = raw_path.decode("utf-8", errors="surrogateescape")
        disk_path = REPO / Path(path)
        if disk_path.is_file():
            result[path] = disk_path.read_bytes()
    return result


def scan(files: dict[str, bytes]) -> tuple[dict[str, list[dict[str, object]]], dict[str, Counter[str]]]:
    findings: dict[str, list[dict[str, object]]] = defaultdict(list)
    signatures: dict[str, Counter[str]] = defaultdict(Counter)
    for path, data in files.items():
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        for category, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings[category].append({"path": path, "line": line})
                digest = hashlib.sha256(match.group(0).strip().encode("utf-8")).hexdigest()
                signatures[category][digest] += 1
    return dict(findings), dict(signatures)


def artifact_candidates(paths: set[str]) -> list[str]:
    candidates: list[str] = []
    for path in sorted(paths):
        normalized = path.replace("\\", "/")
        parts = normalized.split("/")
        name = parts[-1].casefold()
        suffix = Path(name).suffix.casefold()
        env_file = name == ".env" or name.startswith(".env.")
        artifact = bool(set(parts) & ARTIFACT_SEGMENTS) or suffix in ARTIFACT_SUFFIXES or env_file
        if name == "skills.zip":
            artifact = True
        if artifact and normalized not in ALLOWED_ARTIFACT_PATHS and name != "skills.zip":
            candidates.append(path)
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worktree", action="store_true")
    args = parser.parse_args()

    baseline_files = commit_files(BASELINE)
    final_files = worktree_files() if args.worktree else commit_files("HEAD")
    baseline_findings, baseline_signatures = scan(baseline_files)
    final_findings, final_signatures = scan(final_files)

    new_candidates: dict[str, int] = {}
    for category in PATTERNS:
        delta = final_signatures.get(category, Counter()) - baseline_signatures.get(
            category, Counter()
        )
        new_candidates[category] = sum(delta.values())

    summary = {
        "mode": "worktree" if args.worktree else "HEAD",
        "baselineCounts": {
            category: len(baseline_findings.get(category, [])) for category in PATTERNS
        },
        "finalCounts": {
            category: len(final_findings.get(category, [])) for category in PATTERNS
        },
        "newCandidateCounts": new_candidates,
        "finalLocations": final_findings,
        "artifactViolations": artifact_candidates(set(final_files)),
    }
    output = REPO / ".dev" / (
        "security-scan-worktree.json" if args.worktree else "security-scan-head.json"
    )
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "mode": summary["mode"],
                "baselineCounts": summary["baselineCounts"],
                "finalCounts": summary["finalCounts"],
                "newCandidateCounts": summary["newCandidateCounts"],
                "artifactViolationCount": len(summary["artifactViolations"]),
            },
            separators=(",", ":"),
        )
    )
    return 0 if not any(new_candidates.values()) and not summary["artifactViolations"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
