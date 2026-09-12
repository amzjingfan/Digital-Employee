from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.etree import ElementTree


def main() -> None:
    report_path = Path(sys.argv[1])
    root = ElementTree.parse(report_path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    cases = [case for suite in suites for case in suite.findall("testcase")]
    failed = []
    normalized_failed = []
    errored = []
    normalized_errored = []
    skipped = []
    normalized_skipped = []
    for case in cases:
        classname = case.get("classname", "")
        node = f"{classname}::{case.get('name', '')}".strip(":")
        class_parts = classname.split(".")
        test_index = next(
            (index for index, part in enumerate(class_parts) if part.startswith("test_")),
            0,
        )
        normalized = (
            f"{'.'.join(class_parts[test_index:])}::{case.get('name', '')}".strip(":")
        )
        if case.find("failure") is not None:
            failed.append(node)
            normalized_failed.append(normalized)
        if case.find("error") is not None:
            errored.append(node)
            normalized_errored.append(normalized)
        if case.find("skipped") is not None:
            skipped.append(node)
            normalized_skipped.append(normalized)
    result = {
        "tests": len(cases),
        "passed": sum(
            1
            for case in cases
            if case.find("failure") is None
            and case.find("error") is None
            and case.find("skipped") is None
        ),
        "failures": sum(case.find("failure") is not None for case in cases),
        "errors": sum(case.find("error") is not None for case in cases),
        "skipped": len(skipped),
        "durationSeconds": round(sum(float(case.get("time", "0")) for case in cases), 3),
        "failedNodes": sorted(failed),
        "normalizedFailedNodes": sorted(normalized_failed),
        "errorNodes": sorted(errored),
        "normalizedErrorNodes": sorted(normalized_errored),
        "skippedNodes": sorted(skipped),
        "normalizedSkippedNodes": sorted(normalized_skipped),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
