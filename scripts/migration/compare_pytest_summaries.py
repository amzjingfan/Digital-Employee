from __future__ import annotations

import json
import sys
from pathlib import Path


def load(path: str) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main() -> int:
    new = load(sys.argv[1])
    old = load(sys.argv[2])
    new_failed = set(new["normalizedFailedNodes"])
    old_failed = set(old["normalizedFailedNodes"])
    new_errors = set(new["normalizedErrorNodes"])
    old_errors = set(old["normalizedErrorNodes"])
    new_skipped = set(new["normalizedSkippedNodes"])
    old_skipped = set(old["normalizedSkippedNodes"])
    count_keys = ("tests", "passed", "failures", "errors", "skipped")
    new_counts = {key: new[key] for key in count_keys}
    old_counts = {key: old[key] for key in count_keys}
    result = {
        "testCountMatches": new["tests"] == old["tests"],
        "countsMatch": new_counts == old_counts,
        "newCounts": new_counts,
        "oldCounts": old_counts,
        "failedSetsMatch": new_failed == old_failed,
        "newOnlyFailed": sorted(new_failed - old_failed),
        "oldOnlyFailed": sorted(old_failed - new_failed),
        "errorSetsMatch": new_errors == old_errors,
        "newOnlyErrors": sorted(new_errors - old_errors),
        "oldOnlyErrors": sorted(old_errors - new_errors),
        "skippedSetsMatch": new_skipped == old_skipped,
        "newOnlySkipped": sorted(new_skipped - old_skipped),
        "oldOnlySkipped": sorted(old_skipped - new_skipped),
    }
    result["equivalent"] = (
        result["countsMatch"]
        and result["failedSetsMatch"]
        and result["errorSetsMatch"]
        and result["skippedSetsMatch"]
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["equivalent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
