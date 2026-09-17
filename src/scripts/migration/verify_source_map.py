from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SNAPSHOT = "6f3933a0b75333e555848ff70932a5d7874290ee"
FINAL = "fc1dd456445a0eccbe053fa0d19987a4b37102d9"
INDEX_PATH = REPO / "docs/migration/source-index-before-layout.tsv"
OUTPUT_PATH = REPO / "docs/migration/final-source-map.tsv"
SUMMARY_PATH = REPO / ".dev/final-source-map-summary.json"
ADDITIONS_PATH = REPO / ".dev/final-source-map-additions.txt"

REVIEWED_COMMITS = {
    "07b1cd19131357127963394f3469d7488cdc5fbe": "task-2-flat-root",
    "d081397d29f85284849674a2b21b9d6185fb8fa6": "task-3-backend-tests",
    "963d0730c05213ec6d05cce5ded5c515779ca1e6": "task-4-frontend-tests",
    "db849b773f7bb9a68d7027e8bb3c05d6006d2062": "task-5-runner-tests",
    "c2ccf97600ed3ef27b21d3d9d987db0baabc02d3": "task-5-layout-guard-fix",
    "815ee54c931c5a0842f4fdfc6f9989e2790b1fe3": "task-6-workflow-memory",
    "29ec25c57afc044cf12be6e972ba0f5e15a8ffcb": "task-6-doc-path-fix",
    "fc1dd456445a0eccbe053fa0d19987a4b37102d9": "task-8-workflow-contract-fix",
}

EXPECTED_COMMITS = [
    "e8a3affcbe80ecdea1c184e3004f55751c8a0b91",
    *REVIEWED_COMMITS,
]

REVIEWED_MODE_CHANGES = {
    "scripts/dev_down.sh": ("100644", "100755", "task-8-unix-executable-bit"),
    "scripts/dev_status.sh": ("100644", "100755", "task-8-unix-executable-bit"),
    "scripts/dev_up.sh": ("100644", "100755", "task-8-unix-executable-bit"),
}

RUNNER_MOVES = {
    "backend/scripts/run_designkit_e2e.py": "tests/integration/run_designkit_e2e.py",
    "backend/scripts/run_tiktok_mock_sop_replay.py": (
        "tests/integration/run_tiktok_mock_sop_replay.py"
    ),
    "packaging/_docker_test_linux.sh": "tests/packaging/docker_test_linux.sh",
    "packaging/smoke_macos_app.sh": "tests/packaging/smoke_macos_app.sh",
    "packaging/smoke_sandbox_bundle.py": "tests/packaging/smoke_sandbox_bundle.py",
    "packaging/smoke_sandbox_runtime.py": "tests/packaging/smoke_sandbox_runtime.py",
}


def git(*args: str) -> bytes:
    return subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=REPO,
        check=True,
        capture_output=True,
    ).stdout


def tree(commit: str) -> dict[str, tuple[str, str]]:
    entries: dict[str, tuple[str, str]] = {}
    for record in git("ls-tree", "-r", "-z", "--full-tree", commit).split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_type, blob = metadata.decode("ascii").split()
        if object_type != "blob":
            raise RuntimeError(f"Unexpected tree object type: {object_type}")
        path = raw_path.decode("utf-8", errors="surrogateescape")
        entries[path] = (mode, blob)
    return entries


def source_index() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in INDEX_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or line == "original_path\tblob_id":
            continue
        path, blob = line.split("\t", 1)
        if path in rows:
            raise RuntimeError(f"Duplicate source-index path: {path}")
        rows[path] = blob
    return rows


def destination(original: str) -> str:
    path = original.removeprefix("source/")
    if path.startswith("backend/tests/"):
        return "tests/backend/" + path.removeprefix("backend/tests/")
    if path.startswith("frontend-enterprise/src/") and path.endswith(
        (".test.ts", ".test.tsx")
    ):
        return "tests/frontend/" + path.removeprefix("frontend-enterprise/src/")
    return RUNNER_MOVES.get(path, path)


def reviewed_targets() -> dict[str, set[str]]:
    reasons: dict[str, set[str]] = defaultdict(set)
    for commit, reason in REVIEWED_COMMITS.items():
        parent = git("rev-parse", f"{commit}^").decode("ascii").strip()
        output = git(
            "diff-tree",
            "--no-commit-id",
            "-r",
            "-M20%",
            "--name-status",
            parent,
            commit,
        ).decode("utf-8", errors="surrogateescape")
        for line in output.splitlines():
            fields = line.split("\t")
            status = fields[0]
            changed_path = fields[-1] if status.startswith(("R", "C")) else fields[1]
            reasons[changed_path].add(reason)
    return reasons


def main() -> None:
    actual_commits = git("rev-list", "--reverse", f"{SNAPSHOT}..{FINAL}").decode(
        "ascii"
    ).splitlines()
    if actual_commits != EXPECTED_COMMITS:
        raise RuntimeError("Reviewed migration commit chain differs from the pinned source tree")

    baseline = tree(SNAPSHOT)
    final = tree(FINAL)
    indexed = source_index()
    if len(indexed) != 1154:
        raise RuntimeError(f"Expected 1154 source-index rows, got {len(indexed)}")
    if set(indexed) != set(baseline):
        missing = sorted(set(baseline) - set(indexed))
        extra = sorted(set(indexed) - set(baseline))
        raise RuntimeError(f"Index/tree mismatch: missing={missing}, extra={extra}")
    for path, blob in indexed.items():
        if baseline[path][1] != blob:
            raise RuntimeError(f"Index blob mismatch: {path}")

    mapped = {path: destination(path) for path in indexed}
    targets = list(mapped.values())
    if len(set(targets)) != len(targets):
        raise RuntimeError("Destination collision")
    folded: dict[str, list[str]] = defaultdict(list)
    for target in targets:
        folded[target.casefold()].append(target)
    collisions = [values for values in folded.values() if len(values) > 1]
    if collisions:
        raise RuntimeError(f"Case-folded destination collisions: {collisions}")

    reasons = reviewed_targets()
    rows: list[list[str]] = []
    missing_targets: list[str] = []
    reviewed_mode_changes: list[str] = []
    unexplained_mode_changes: list[str] = []
    unexplained: list[str] = []
    exact = 0
    edited = 0
    for original in indexed:
        final_path = mapped[original]
        baseline_mode, baseline_blob = baseline[original]
        if final_path not in final:
            missing_targets.append(final_path)
            continue
        final_mode, final_blob = final[final_path]
        mode_reason = "unchanged"
        if baseline_mode != final_mode:
            expected = REVIEWED_MODE_CHANGES.get(final_path)
            if expected and expected[:2] == (baseline_mode, final_mode):
                reviewed_mode_changes.append(final_path)
                mode_reason = expected[2]
            else:
                unexplained_mode_changes.append(final_path)
                mode_reason = "UNEXPLAINED"
        if baseline_blob == final_blob:
            disposition = "exact"
            reason = "path-only-or-unchanged"
            exact += 1
        else:
            disposition = "reviewed-edit"
            labels = sorted(reasons.get(final_path, ()))
            if not labels:
                unexplained.append(final_path)
                reason = "UNEXPLAINED"
            else:
                reason = ",".join(labels)
            edited += 1
        rows.append(
            [
                original,
                baseline_mode,
                baseline_blob,
                final_path,
                final_mode,
                final_blob,
                disposition,
                reason,
                mode_reason,
            ]
        )

    if (
        missing_targets
        or unexplained_mode_changes
        or unexplained
        or set(reviewed_mode_changes) != set(REVIEWED_MODE_CHANGES)
    ):
        raise RuntimeError(
            "Mapping verification failed: "
            f"missing={missing_targets}, modes={unexplained_mode_changes}, "
            f"unexplained={unexplained}"
        )

    header = [
        "original_path",
        "baseline_mode",
        "baseline_blob",
        "final_path",
        "final_mode",
        "final_blob",
        "disposition",
        "change_reason",
        "mode_change_reason",
    ]
    OUTPUT_PATH.write_text(
        "\t".join(header)
        + "\n"
        + "\n".join("\t".join(row) for row in rows)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    additions = sorted(set(final) - set(targets))
    ADDITIONS_PATH.write_text("\n".join(additions) + "\n", encoding="utf-8", newline="\n")
    summary = {
        "snapshotCommit": SNAPSHOT,
        "finalCommit": git("rev-parse", FINAL).decode("ascii").strip(),
        "indexedPaths": len(indexed),
        "mappedPaths": len(rows),
        "uniqueTargets": len(set(targets)),
        "caseInsensitiveCollisionGroups": len(collisions),
        "missingTargets": len(missing_targets),
        "modeMismatches": len(reviewed_mode_changes)
        + len(unexplained_mode_changes),
        "reviewedModeChanges": len(reviewed_mode_changes),
        "unexplainedModeChanges": len(unexplained_mode_changes),
        "exactBlobs": exact,
        "reviewedEdits": edited,
        "unexplainedEdits": len(unexplained),
        "intentionalAdditions": len(additions),
    }
    SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(summary, separators=(",", ":")))


if __name__ == "__main__":
    main()
