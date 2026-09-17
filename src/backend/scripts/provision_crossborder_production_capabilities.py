from __future__ import annotations

import argparse
import json

from sqlmodel import Session

from app.config import get_settings
from app.crossborder import provision_crossborder_capabilities
from app.db.database import engine


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", default="tenant_demo")
    parser.add_argument("--tool-base-url", default=None)
    args = parser.parse_args()
    tool_base_url = args.tool_base_url or get_settings().normalized_tool_base_url
    with Session(engine) as db:
        summaries = provision_crossborder_capabilities(
            db, tenant_id=args.tenant_id, tool_base_url=tool_base_url
        )
    print(json.dumps({"tenant_id": args.tenant_id, "capabilities": summaries}, ensure_ascii=False))


if __name__ == "__main__":
    main()
