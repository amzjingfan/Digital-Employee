from __future__ import annotations

import argparse
import json

from sqlmodel import Session, select

from app.agents.releases import PRODUCTION_ROLES, publish_agent_release
from app.db.database import engine, set_tenant_context
from app.db.models import AgentProfile, User


def publish(tenant_id: str, actor_username: str | None = None) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    with Session(engine) as db:
        set_tenant_context(db, tenant_id)
        actor_query = select(User).where(User.tenant_id == tenant_id, User.role == "admin")
        if actor_username:
            actor_query = actor_query.where(User.username == actor_username)
        actor = db.exec(actor_query.order_by(User.created_at)).first()
        if not actor:
            raise RuntimeError("No tenant administrator is available to sign the agent release")
        agents = db.exec(
            select(AgentProfile).where(
                AgentProfile.tenant_id == tenant_id,
                AgentProfile.status == "active",
                AgentProfile.is_overall.is_(False),
            )
        ).all()
        by_role = {
            str((row.metadata_json or {}).get("business_role") or ""): row for row in agents
        }
        missing = sorted(PRODUCTION_ROLES - set(by_role))
        if missing:
            raise RuntimeError(f"Missing production digital employees: {', '.join(missing)}")
        for role in sorted(PRODUCTION_ROLES):
            agent = by_role[role]
            release = publish_agent_release(
                db,
                tenant_id=tenant_id,
                agent_id=agent.id,
                actor=actor,
                reason="Reviewed cross-border production capability baseline",
            )
            results.append(
                {
                    "role": role,
                    "agent_id": agent.id,
                    "release_id": release.id,
                    "version": release.version,
                    "snapshot_digest": release.snapshot_digest,
                }
            )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", default="tenant_demo")
    parser.add_argument("--actor-username", default=None)
    args = parser.parse_args()
    print(
        json.dumps(
            {"tenant_id": args.tenant_id, "releases": publish(args.tenant_id, args.actor_username)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
