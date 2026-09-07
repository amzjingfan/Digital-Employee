from __future__ import annotations

import argparse
import json

from sqlmodel import Session, select

from app.agents.branching import (
    visible_knowledge_base_versions,
    visible_published_skills,
    visible_tool_rows,
)
from app.agents.releases import verify_agent_release_for_execution
from app.crossborder.capability_pack import ROLE_PACKS
from app.db.database import engine, set_tenant_context
from app.db.models import (
    AgentProfile,
    AgentServiceIdentity,
    User,
    WorkTask,
    WorkTaskRun,
)
from app.security.permissions import gallery_agent_visible_to_user
from app.tools import ToolExecutor
from app.tools.tool_schema import ToolCall
from app.work_tasks.snapshots import build_execution_snapshot, execution_snapshot_digest


def verify(tenant_id: str) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    with Session(engine) as db:
        set_tenant_context(db, tenant_id)
        agents = db.exec(select(AgentProfile).where(AgentProfile.tenant_id == tenant_id)).all()
        by_role = {
            str((agent.metadata_json or {}).get("business_role") or ""): agent for agent in agents
        }
        supervisor_users = db.exec(
            select(User).where(
                User.tenant_id == tenant_id,
                User.business_role == "operations_supervisor",
            )
        ).all()
        assert supervisor_users, "No operations supervisor user is mapped for gallery verification"
        for index, spec in enumerate(ROLE_PACKS, start=1):
            agent = by_role[spec.role]
            skills = visible_published_skills(db, tenant_id, agent.id)
            knowledge = visible_knowledge_base_versions(db, tenant_id, agent.id)
            tools = visible_tool_rows(db, tenant_id, agent.id, include_inactive=False)
            assert [item.skill_id for item in skills] == [spec.skill_id]
            assert len(knowledge) == 1
            assert len(tools) == 1
            assert tools[0].allowed_skills_json == [spec.skill_id]
            assert tools[0].config_json["production"]["risk_class"] == "read_only"
            metadata = agent.metadata_json or {}
            allowed_roles = metadata.get("gallery_allowed_business_roles")
            assert metadata.get("published_to_gallery") is True
            assert metadata.get("gallery_template_kind") == "reviewed_production_role"
            assert isinstance(allowed_roles, list)
            assert spec.role in allowed_roles
            assert "operations_supervisor" in allowed_roles
            assert "platform_admin" in allowed_roles
            role_viewer = User(
                id=f"verify-viewer-{index}",
                tenant_id=tenant_id,
                username=f"verify-viewer-{index}",
                business_role=spec.role,
                password_hash="verification-only",
            )
            supervisor = User(
                id=f"verify-supervisor-{index}",
                tenant_id=tenant_id,
                username=f"verify-supervisor-{index}",
                business_role="operations_supervisor",
                password_hash="verification-only",
            )
            disallowed_role = next(item.role for item in ROLE_PACKS if item.role not in allowed_roles)
            disallowed = User(
                id=f"verify-disallowed-{index}",
                tenant_id=tenant_id,
                username=f"verify-disallowed-{index}",
                business_role=disallowed_role,
                password_hash="verification-only",
            )
            assert gallery_agent_visible_to_user(agent, role_viewer)
            assert gallery_agent_visible_to_user(agent, supervisor)
            assert not gallery_agent_visible_to_user(agent, disallowed)
            assert all(
                gallery_agent_visible_to_user(agent, user) for user in supervisor_users
            )

            call = ToolExecutor(db).execute(
                tenant_id,
                ToolCall(name=tools[0].name, arguments={"limit": 5}),
                active_skill_id=spec.skill_id,
                agent_id=agent.id,
                session_id=f"verify-{index}",
            )
            assert call.success, call.model_dump(mode="json")
            assert isinstance(call.data, dict)
            assert call.data["business_role"] == spec.role
            assert call.data["data_quality"]["credentials_included"] is False

            identity = db.exec(
                select(AgentServiceIdentity).where(
                    AgentServiceIdentity.tenant_id == tenant_id,
                    AgentServiceIdentity.agent_id == agent.id,
                    AgentServiceIdentity.business_role == spec.role,
                    AgentServiceIdentity.status == "active",
                )
            ).one()
            task = WorkTask(
                id=f"verify-task-{index}",
                tenant_id=tenant_id,
                idempotency_key=f"verify-{spec.role}",
                title=f"Verify {spec.role}",
                owner_business_role=spec.role,
                assignee_agent_id=agent.id,
                assigned_by_user_id="verification",
            )
            run = WorkTaskRun(
                id=f"verify-run-{index}",
                tenant_id=tenant_id,
                task_id=task.id,
                attempt_no=1,
                generation=1,
                agent_id=agent.id,
                session_id=f"verify-session-{index}",
                service_identity_id=identity.id,
            )
            release = verify_agent_release_for_execution(db, agent)
            snapshot = build_execution_snapshot(
                db,
                task=task,
                run=run,
                agent=agent,
                agent_release=release,
                service_identity=identity,
            )
            assert len(snapshot.sop_snapshots_json) == 1
            assert len(snapshot.knowledge_snapshots_json) == 1
            assert len(snapshot.tool_snapshots_json) == 1
            assert execution_snapshot_digest(snapshot) == snapshot.snapshot_digest
            assert snapshot.agent_snapshot_json["release_id"] == release.id
            assert snapshot.agent_snapshot_json["release_version"] == release.version
            assert snapshot.agent_snapshot_json["release_digest"] == release.snapshot_digest
            safe = json.dumps(
                {
                    "snapshot": snapshot.model_dump(mode="json"),
                    "tool_result": call.model_dump(mode="json"),
                },
                ensure_ascii=False,
            ).lower()
            for forbidden in ("client_secret", "access_token", "refresh_token", "api_key"):
                assert forbidden not in safe
            results.append(
                {
                    "business_role": spec.role,
                    "agent_id": agent.id,
                    "skill_id": spec.skill_id,
                    "knowledge_version_id": next(iter(knowledge.values())).id,
                    "tool_name": tools[0].name,
                    "tool_http_call": "passed",
                    "gallery_published": True,
                    "gallery_allowed_business_roles": allowed_roles,
                    "gallery_role_gate_verified": True,
                    "mapped_supervisor_visibility_verified": True,
                    "snapshot_counts": {"sops": 1, "knowledge": 1, "tools": 1},
                    "snapshot_digest_verified": True,
                    "agent_release": {
                        "id": release.id,
                        "version": release.version,
                        "digest": release.snapshot_digest,
                    },
                }
            )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", default="tenant_demo")
    args = parser.parse_args()
    print(
        json.dumps(
            {"tenant_id": args.tenant_id, "results": verify(args.tenant_id)}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
