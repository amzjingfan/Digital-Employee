from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.agents.releases import (
    AgentReleaseError,
    diff_agent_releases,
    mark_agent_draft_if_changed,
    publish_agent_release,
    rollback_agent_release,
    verify_agent_release_for_execution,
)
from app.db.models import (
    AgentProfile,
    AgentRelease,
    AgentReleaseEvent,
    AgentResourceBinding,
    AgentServiceIdentity,
    KnowledgeBaseVersion,
    Skill,
    Tenant,
    Tool,
    User,
)


def _engine():
    result = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(result)
    return result


def _seed(db: Session) -> tuple[User, AgentProfile]:
    actor = User(
        id="user-admin",
        tenant_id="tenant-a",
        username="admin",
        role="admin",
        business_role="platform_admin",
        password_hash="unused",
    )
    agent = AgentProfile(
        id="agent-logistics",
        tenant_id="tenant-a",
        name="物流异常专员",
        description="只读研判物流异常",
        metadata_json={"business_role": "logistics_exception_specialist"},
    )
    db.add(Tenant(id="tenant-a", name="Tenant A"))
    db.add(actor)
    db.add(agent)
    for resource_type, resource_id in (
        ("skill", "skill-row-1"),
        ("knowledge_base", "kb-carriers"),
        ("tool", "tool-track"),
    ):
        db.add(
            AgentResourceBinding(
                tenant_id="tenant-a",
                agent_id=agent.id,
                resource_type=resource_type,
                resource_id=resource_id,
                status="active",
                metadata_json={"review_status": "approved"},
            )
        )
    db.commit()
    return actor, agent


def _capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    skill = Skill(
        id="skill-row-1",
        tenant_id="tenant-a",
        skill_id="logistics-triage",
        version="1.0.0",
        name="物流异常分诊",
        status="published",
        content_json={"nodes": [{"node_id": "start", "type": "start"}], "edges": []},
    )
    knowledge = KnowledgeBaseVersion(
        id="kbver-1",
        tenant_id="tenant-a",
        knowledge_base_id="kb-carriers",
        version="1.0.0",
        name="物流规则",
        metadata_json={"review_status": "approved"},
    )
    tool = Tool(
        id="tool-track",
        tenant_id="tenant-a",
        name="track_shipment",
        display_name="查询物流轨迹",
        method="GET",
        url="https://carrier.example.test/track",
    )
    monkeypatch.setattr(
        "app.agents.releases.visible_published_skills", lambda *args, **kwargs: [skill]
    )
    monkeypatch.setattr(
        "app.agents.releases.visible_knowledge_base_versions",
        lambda *args, **kwargs: {"kb-carriers": knowledge},
    )
    monkeypatch.setattr(
        "app.agents.releases.visible_tool_rows", lambda *args, **kwargs: [tool]
    )


def test_production_publish_requires_dedicated_service_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capabilities(monkeypatch)
    with Session(_engine()) as db:
        actor, agent = _seed(db)
        with pytest.raises(AgentReleaseError, match="service identity"):
            publish_agent_release(
                db,
                tenant_id=agent.tenant_id,
                agent_id=agent.id,
                actor=actor,
                reason="Initial production publication",
            )


def test_publish_drift_republish_diff_and_rollback_are_versioned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capabilities(monkeypatch)
    with Session(_engine()) as db:
        actor, agent = _seed(db)
        db.add(
            AgentServiceIdentity(
                tenant_id="tenant-a",
                agent_id=agent.id,
                business_role="logistics_exception_specialist",
                issuer="https://identity.example.test",
                token_endpoint="https://identity.example.test/token",
                jwks_uri="https://identity.example.test/jwks",
                application_owner="admin",
                application_name="app-logistics",
                client_id="logistics-client",
                client_id_fingerprint="sha256:client",
                credential_ref="casdoor:admin/app-logistics",
            )
        )
        db.commit()

        first = publish_agent_release(
            db,
            tenant_id=agent.tenant_id,
            agent_id=agent.id,
            actor=actor,
            reason="Initial production publication",
        )
        assert first.version == 1
        assert verify_agent_release_for_execution(db, agent).id == first.id

        agent.description = "更新后的物流异常研判规则"
        db.add(agent)
        db.flush()
        assert mark_agent_draft_if_changed(
            db, agent, actor=actor, reason="Profile description changed"
        )
        db.commit()
        with pytest.raises(AgentReleaseError, match="unpublished changes"):
            verify_agent_release_for_execution(db, agent)

        second = publish_agent_release(
            db,
            tenant_id=agent.tenant_id,
            agent_id=agent.id,
            actor=actor,
            reason="Publish reviewed profile update",
        )
        assert second.version == 2
        assert first.snapshot_json["agent"]["description"] == "只读研判物流异常"
        assert any(change["path"] == "agent.description" for change in diff_agent_releases(first, second))

        third = rollback_agent_release(
            db,
            tenant_id=agent.tenant_id,
            agent_id=agent.id,
            target_release_id=first.id,
            actor=actor,
            reason="Rollback reviewed profile regression",
        )
        db.refresh(agent)
        assert third.version == 3
        assert third.source_release_id == first.id
        assert agent.description == "只读研判物流异常"
        assert agent.published_release_id == third.id
        assert verify_agent_release_for_execution(db, agent).id == third.id

        releases = db.exec(
            select(AgentRelease).where(AgentRelease.agent_id == agent.id).order_by(AgentRelease.version)
        ).all()
        assert [row.status for row in releases] == ["superseded", "superseded", "published"]
        events = db.exec(
            select(AgentReleaseEvent)
            .where(AgentReleaseEvent.agent_id == agent.id)
            .order_by(AgentReleaseEvent.occurred_at)
        ).all()
        assert [row.event_type for row in events] == [
            "published",
            "draft_changed",
            "published",
            "rolled_back",
        ]
