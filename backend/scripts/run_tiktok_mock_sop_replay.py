from __future__ import annotations

import json

from app.tiktok.mock_replay import run_tiktok_mock_sop_replays

if __name__ == "__main__":
    print(json.dumps(run_tiktok_mock_sop_replays(), ensure_ascii=False, indent=2))
