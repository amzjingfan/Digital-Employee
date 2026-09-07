from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from app.db.models import (
    AgentProfile,
    AgentRelease,
    AgentServiceIdentity,
    KnowledgeBaseVersion,
    Skill,
    Tool,
    WorkTask,
    WorkTaskRun,
)
from app.work_tasks.snapshots import (
    WorkTaskSnapshotError,
    build_execution_snapshot,
    execution_snapshot_digest,
)


def _objects():
    agent = AgentProfile(
        id="agent-logistics",
        tenant_id="tenant-a",
        name="物流异常专员",
        persona_prompt="仅处理物流异常。",
        harness_max_actions=12,
        metadata_json={"business_role": "logistics_exception_specialist"},
    )
    release = AgentRelease(
        id="agent-release-3",
        tenant_id="tenant-a",
        agent_id=agent.id,
        version=3,
        snapshot_digest="sha256:agent-release",
        created_by_user_id="user-manager",
        release_reason="Production release",
    )
    agent.release_state = "published"
    agent.published_release_id = release.id
    agent.published_release_version = release.version
    identity = AgentServiceIdentity(
        id="identity-logistics",
        tenant_id="tenant-a",
        agent_id=agent.id,
        business_role="logistics_exception_specialist",
        issuer="https://identity.example.test",
        token_endpoint="https://identity.example.test/token",
        jwks_uri="https://identity.example.test/jwks",
        application_owner="admin",
        application_name="app-logistics",
        client_id="raw-client-id-must-not-be-snapshotted",
        client_id_fingerprint="sha256:client-fingerprint",
        credential_ref="casdoor:admin/app-logistics",
    )
    task = WorkTask(
        id="task-1",
        tenant_id="tenant-a",
        idempotency_key="snapshot-test-1",
        title="物流检查",
        owner_business_role="logistics_exception_specialist",
        assigned_by_user_id="user-manager",
        assignee_agent_id=agent.id,
    )
    run = WorkTaskRun(
        id="run-1",
        tenant_id="tenant-a",
        task_id=task.id,
        attempt_no=1,
        generation=1,
        agent_id=agent.id,
        session_id="session-1",
    )
    skill = Skill(
        id="skill-row-1",
        tenant_id="tenant-a",
        skill_id="logistics-triage",
        version="2.3.1",
        name="物流异常分诊",
        status="published",
        content_json={"nodes": [{"node_id": "start", "type": "start"}], "edges": []},
    )
    knowledge = KnowledgeBaseVersion(
        id="kbver-7",
        tenant_id="tenant-a",
        knowledge_base_id="kb-carriers",
        version="7.0.0",
        name="承运商规则",
    )
    tool = Tool(
        id="tool-track",
        tenant_id="tenant-a",
        name="track_shipment",
        display_name="查询物流轨迹",
        method="GET",
        url="https://carrier.example.test/track",
        auth_json={"bearer_token": "must-be-hashed-not-copied"},
    )
    return agent, release, identity, task, run, skill, knowledge, tool


def test_snapshot_freezes_versions_and_excludes_raw_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, release, identity, task, run, skill, knowledge, tool = _objects()
    monkeypatch.setattr(
        "app.work_tasks.snapshots.visible_published_skills", lambda *args, **kwargs: [skill]
    )
    monkeypatch.setattr(
        "app.work_tasks.snapshots.visible_knowledge_base_versions",
        lambda *args, **kwargs: {"kb-carriers": knowledge},
    )
    monkeypatch.setattr(
        "app.work_tasks.snapshots.visible_tool_rows", lambda *args, **kwargs: [tool]
    )

    snapshot = build_execution_snapshot(
        Mock(),
        task=task,
        run=run,
        agent=agent,
        agent_release=release,
        service_identity=identity,
    )

    assert snapshot.sop_snapshots_json[0]["version"] == "2.3.1"
    assert snapshot.knowledge_snapshots_json[0]["knowledge_base_version_id"] == "kbver-7"
    assert snapshot.knowledge_snapshots_json[0]["version"] == "7.0.0"
    assert snapshot.tool_snapshots_json[0]["content_digest"].startswith("sha256:")
    assert snapshot.agent_snapshot_json["harness_max_actions"] == 12
    assert snapshot.agent_snapshot_json["release_id"] == release.id
    assert snapshot.agent_snapshot_json["release_version"] == 3
    assert snapshot.agent_snapshot_json["release_digest"] == release.snapshot_digest
    assert snapshot.service_identity_snapshot_json["application_name"] == "app-logistics"
    assert execution_snapshot_digest(snapshot) == snapshot.snapshot_digest
    serialized = json.dumps(snapshot.model_dump(mode="json"), sort_keys=True)
    assert "raw-client-id-must-not-be-snapshotted" not in serialized
    assert "must-be-hashed-not-copied" not in serialized
    assert "client_secret" not in serialized
    assert "access_token" not in serialized


def test_snapshot_rejects_cross_role_service_identity() -> None:
    agent, release, identity, task, run, *_ = _objects()
    identity.business_role = "designer"
    with pytest.raises(WorkTaskSnapshotError, match="岗位"):
        build_execution_snapshot(
            Mock(),
            task=task,
            run=run,
            agent=agent,
            agent_release=release,
            service_identity=identity,
        )
