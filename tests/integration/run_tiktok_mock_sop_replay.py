from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.tiktok.mock_replay import run_tiktok_mock_sop_replays

if __name__ == "__main__":
    print(json.dumps(run_tiktok_mock_sop_replays(), ensure_ascii=False, indent=2))
