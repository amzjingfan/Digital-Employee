"""Business-owner gated publication of the five TikTok production employees.

The command is intentionally a dry run unless ``--apply`` and an approval
reference are supplied.  Bootstrap only creates reviewed seed assets; it must
never silently turn those assets into production releases.
"""

from __future__ import annotations

import argparse
import json

from sqlmodel import Session, select

from app.agents.releases import (
    _validate_production_readiness,
    build_agent_release_snapshot,
    publish_agent_release,
)
from app.db.database import engine, set_tenant_context
from app.db.models import AgentProfile, User
from app.tiktok.service import TIKTOK_AGENT_CATALOG


def preflight(
    tenant_id: str,
    actor_username: str | None = None,
) -> tuple[User, list[dict[str, object]]]:
    with Session(engine) as db:
        set_tenant_context(db, tenant_id)
        actor_query = select(User).where(User.tenant_id == tenant_id, User.role == "admin")
        if actor_username:
            actor_query = actor_query.where(User.username == actor_username)
        actor = db.exec(actor_query.order_by(User.created_at)).first()
        if not actor:
            raise RuntimeError("No tenant administrator is available to approve the agent release")
        agents = db.exec(
            select(AgentProfile).where(
                AgentProfile.tenant_id == tenant_id,
                AgentProfile.status == "active",
                AgentProfile.is_overall.is_(False),
            )
        ).all()
        by_name = {row.name: row for row in agents}
        missing = sorted(
            slug for slug, name, _role, _department in TIKTOK_AGENT_CATALOG if name not in by_name
        )
        if missing:
            raise RuntimeError(f"Missing TikTok production digital employees: {', '.join(missing)}")
        results: list[dict[str, object]] = []
        for slug, name, role, _department in TIKTOK_AGENT_CATALOG:
            agent = by_name[name]
            snapshot = build_agent_release_snapshot(db, agent)
            try:
                _validate_production_readiness(db, agent, snapshot)
            except ValueError as exc:
                results.append(
                    {"role": role, "agent_id": agent.id, "ready": False, "error": str(exc)}
                )
            else:
                results.append(
                    {
                        "role": role,
                        "agent_id": agent.id,
                        "ready": True,
                        "current_release_state": agent.release_state,
                    }
                )
        return actor, results


def publish(
    tenant_id: str,
    actor_username: str | None = None,
    *,
    apply: bool = False,
    approval_reference: str | None = None,
) -> dict[str, object]:
    actor, checks = preflight(tenant_id, actor_username)
    not_ready = [row for row in checks if row.get("ready") is not True]
    if not apply:
        return {"tenant_id": tenant_id, "mode": "dry_run", "ready": not not_ready, "checks": checks}
    if not approval_reference or not approval_reference.strip():
        raise RuntimeError("--approval-reference is required with --apply")
    if not_ready:
        raise RuntimeError("TikTok production release preflight failed; no release was published")

    releases: list[dict[str, object]] = []
    with Session(engine) as db:
        set_tenant_context(db, tenant_id)
        agents = db.exec(
            select(AgentProfile).where(
                AgentProfile.tenant_id == tenant_id,
                AgentProfile.status == "active",
                AgentProfile.is_overall.is_(False),
            )
        ).all()
        by_id = {row.id: row for row in agents}
        for check in checks:
            role = str(check["role"])
            agent = by_id.get(str(check["agent_id"]))
            if not agent:
                raise RuntimeError(f"TikTok employee disappeared during publish: {role}")
            release = publish_agent_release(
                db,
                tenant_id=tenant_id,
                agent_id=agent.id,
                actor=actor,
                reason=f"Business owner approval {approval_reference.strip()}: TikTok production baseline",
            )
            releases.append(
                {
                    "role": role,
                    "agent_id": agent.id,
                    "release_id": release.id,
                    "version": release.version,
                    "snapshot_digest": release.snapshot_digest,
                }
            )
    return {
        "tenant_id": tenant_id,
        "mode": "apply",
        "approval_reference": approval_reference.strip(),
        "actor": actor.username,
        "releases": releases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", default="tenant_demo")
    parser.add_argument("--actor-username", default=None)
    parser.add_argument("--approval-reference", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            publish(
                args.tenant_id,
                args.actor_username,
                apply=args.apply,
                approval_reference=args.approval_reference,
            ),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
