"""Emit a machine-readable, read-only P3-A TikTok live-write surface report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.tiktok.release_gate import verify_tiktok_live_write_disabled


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify that P3-A exposes no TikTok Live writes")
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Joukir source repository root",
    )
    args = parser.parse_args()
    result = verify_tiktok_live_write_disabled(args.repository_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if not result["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
