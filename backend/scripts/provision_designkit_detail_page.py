"""Install the user-supplied DesignKit package for the designer employee.

The script stores the package as auditable Skill source and binds a read-only
internal API.  It deliberately does not install or authenticate the DesignKit
CLI and does not create a fake MCP server when the package has no MCP endpoint.
"""

from __future__ import annotations

import argparse
import json

from sqlmodel import Session, select

from app.creative.designkit_package import provision_designkit_package
from app.db import engine
from app.db.database import set_tenant_context
from app.db.models import User


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", default="tenant_demo")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--zip", dest="zip_path", required=True)
    parser.add_argument("--actor-user-id", default="admin")
    parser.add_argument("--tool-base-url", default=None)
    args = parser.parse_args()
    with Session(engine) as db:
        # PostgreSQL RLS hides tenant rows until the same tenant context used
        # by the API request is established on this administrative session.
        set_tenant_context(db, args.tenant_id)
        actor = db.exec(
            select(User).where(
                User.tenant_id == args.tenant_id,
                User.id == args.actor_user_id,
            )
        ).first()
        if actor is None:
            raise SystemExit(f"actor user not found: {args.actor_user_id}")
        result = provision_designkit_package(
            db,
            tenant_id=args.tenant_id,
            agent_id=args.agent_id,
            zip_path=args.zip_path,
            actor=actor,
            tool_base_url=args.tool_base_url,
        )
        print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
