from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.agents.releases import AgentReleaseError
from app.config import Settings
from app.db.models import (
    AgentProfile,
    AgentRelease,
    AgentServiceIdentity,
    ChatSession,
    Tenant,
    User,
    WorkTask,
    WorkTaskEvent,
    WorkTaskExecutionSnapshot,
    WorkTaskRun,
    utc_now,
)
from app.work_tasks.m2m import ServiceTokenReceipt
from app.work_tasks.schema import WorkTaskCreate, WorkTaskTransition
from app.work_tasks.service import create_task, get_task, transition_task
from app.work_tasks.worker import WorkTaskOutcome, _claim_one, _record_outcome, run_work_task_cycle


def _engine():
    result = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(result)
    return result


def _settings() -> Settings:
    return Settings(
        work_task_execution_enabled=True,
        work_task_execution_mode="sandbox",
        work_task_execution_tenant_ids="tenant_demo",
        work_task_execution_batch_size=4,
        work_task_execution_lease_seconds=60,
    )


def _seed(db: Session) -> tuple[User, User, AgentProfile]:
    manager = User(
        tenant_id="tenant_demo",
        username="manager",
        role="member",
        business_role="operations_supervisor",
        password_hash="unused",
    )
    specialist = User(
        tenant_id="tenant_demo",
        username="logistics",
        role="member",
        business_role="logistics_exception_specialist",
        password_hash="unused",
    )
    agent = AgentProfile(
        tenant_id="tenant_demo",
        name="物流异常专员",
        status="active",
        metadata_json={"business_role": "logistics_exception_specialist"},
    )
    db.add(Tenant(id="tenant_demo", name="Demo"))
    db.add(manager)
    db.add(specialist)
    db.add(agent)
    db.commit()
    db.refresh(manager)
    db.refresh(specialist)
    db.refresh(agent)
    release = AgentRelease(
        tenant_id="tenant_demo",
        agent_id=agent.id,
        version=1,
        snapshot_json={},
        snapshot_digest="sha256:test-agent-release",
        created_by_user_id=manager.id,
        release_reason="Worker test release",
    )
    db.add(release)
    db.flush()
    agent.release_state = "published"
    agent.published_release_id = release.id
    agent.published_release_version = release.version
    db.add(agent)
    db.add(
        AgentServiceIdentity(
            tenant_id="tenant_demo",
            agent_id=agent.id,
            business_role="logistics_exception_specialist",
            issuer="http://localhost:18000",
            token_endpoint="http://localhost:18000/api/login/oauth/access_token",
            jwks_uri="http://localhost:18000/.well-known/jwks",
            application_owner="admin",
            application_name="app-staffdeck-agent-logistics-exception",
            client_id="test-logistics-client",
            client_id_fingerprint="sha256:test-client",
            credential_ref="test:logistics",
        )
    )
    db.commit()
    return manager, specialist, agent


@pytest.fixture(autouse=True)
def _mock_m2m_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.work_tasks.worker.authenticate_service_identity",
        lambda identity, settings: ServiceTokenReceipt(
            subject=f"service:{identity.application_name}",
            audience=(identity.client_id,),
            expires_at=utc_now() + timedelta(minutes=15),
            token_fingerprint="sha256:test-token",
        ),
    )
    monkeypatch.setattr(
        "app.work_tasks.worker.verify_agent_release_for_execution",
        lambda db, agent: db.exec(
            select(AgentRelease).where(
                AgentRelease.tenant_id == agent.tenant_id,
                AgentRelease.agent_id == agent.id,
                AgentRelease.id == agent.published_release_id,
            )
        ).one(),
    )


def _create(db: Session, manager: User, key: str = "worker-task-001") -> str:
    task = create_task(
        db,
        request=WorkTaskCreate(
            tenant_id="tenant_demo",
            idempotency_key=key,
            title="核对超时物流轨迹并提出处理建议",
            owner_business_role="logistics_exception_specialist",
            priority="high",
        ),
        user=manager,
    )
    return task.id


def test_sandbox_worker_claims_task_creates_session_and_submits_review() -> None:
    db_engine = _engine()
    with Session(db_engine) as db:
        manager, _, agent = _seed(db)
        task_id = _create(db, manager)

    assert run_work_task_cycle(db_engine=db_engine, settings=_settings()) == 1

    with Session(db_engine) as db:
        task = db.get(WorkTask, task_id)
        run = db.exec(select(WorkTaskRun).where(WorkTaskRun.task_id == task_id)).one()
        snapshot = db.exec(
            select(WorkTaskExecutionSnapshot).where(WorkTaskExecutionSnapshot.run_id == run.id)
        ).one()
        session = db.get(ChatSession, run.session_id)
        events = db.exec(select(WorkTaskEvent).where(WorkTaskEvent.task_id == task_id)).all()
        assert task is not None
        assert task.status == "review"
        assert task.control_mode == "agent"
        assert task.attempt_count == 1
        assert task.latest_session_id == run.session_id
        assert run.status == "succeeded"
        assert run.agent_id == agent.id
        assert run.execution_snapshot_id == snapshot.id
        assert run.snapshot_digest == snapshot.snapshot_digest
        assert run.service_identity_id == snapshot.service_identity_id
        assert session is not None and session.channel == "work_task"
        assert [event.event_type for event in events][-2:] == ["agent_claimed", "agent_submitted_review"]


def test_sandbox_mock_replay_records_sop_knowledge_tool_and_follow_up_trace() -> None:
    db_engine = _engine()
    with Session(db_engine) as db:
        manager, _, _ = _seed(db)
        task_id = _create(db, manager, "worker-task-mock-replay")
        task = db.get(WorkTask, task_id)
        assert task is not None
        task.input_json = {
            "execution_mode": "mock_replay",
            "sop_id": "TT-SOP-004",
            "knowledge_refs": ["ads_metric_dictionary_demo_v1"],
            "tool_name": "tiktok.mock.ads.read",
            "external_writes": False,
        }
        db.add(task)
        db.commit()

    assert run_work_task_cycle(db_engine=db_engine, settings=_settings()) == 1

    with Session(db_engine) as db:
        run = db.exec(select(WorkTaskRun).where(WorkTaskRun.task_id == task_id)).one()
        trace = run.trace_json
        assert trace["execution_mode"] == "mock_replay"
        assert trace["sop_id"] == "TT-SOP-004"
        assert [step["type"] for step in trace["steps"]] == [
            "knowledge_retrieval",
            "tool_call",
            "evidence_attached",
            "human_follow_up",
        ]
        assert trace["steps"][1]["external_write"] is False


def test_human_takeover_fences_late_agent_outcome_and_can_return_task() -> None:
    db_engine = _engine()
    settings = _settings()
    with Session(db_engine) as db:
        manager, specialist, _ = _seed(db)
        task_id = _create(db, manager, "worker-task-takeover")
        specialist_id = specialist.id

    claim = _claim_one(db_engine, "tenant_demo", settings)
    assert claim is not None
    with Session(db_engine) as db:
        specialist = db.get(User, specialist_id)
        assert specialist is not None
        current = get_task(db, tenant_id="tenant_demo", task_id=task_id, user=specialist)
        taken = transition_task(
            db,
            task_id=task_id,
            request=WorkTaskTransition(
                tenant_id="tenant_demo",
                action="takeover",
                expected_version=current.version,
                note="需要人工核对承运商回执",
            ),
            user=specialist,
        )
        assert taken.control_mode == "human"

    _record_outcome(
        db_engine,
        claim,
        WorkTaskOutcome(disposition="succeeded", summary="不应覆盖人工结果"),
    )
    with Session(db_engine) as db:
        specialist = db.get(User, specialist_id)
        assert specialist is not None
        task = get_task(db, tenant_id="tenant_demo", task_id=task_id, user=specialist)
        assert task.control_mode == "human"
        assert task.status == "in_progress"
        assert task.result_summary is None
        assert task.runs[0].status == "stale"
        returned = transition_task(
            db,
            task_id=task_id,
            request=WorkTaskTransition(
                tenant_id="tenant_demo",
                action="return_to_agent",
                expected_version=task.version,
            ),
            user=specialist,
        )
        assert returned.status == "pending"
        assert returned.control_mode == "agent"
        assert returned.cancel_requested is False


def test_expired_lease_is_recovered_before_next_attempt() -> None:
    db_engine = _engine()
    settings = _settings()
    with Session(db_engine) as db:
        manager, _, _ = _seed(db)
        task_id = _create(db, manager, "worker-task-recovery")

    first = _claim_one(db_engine, "tenant_demo", settings)
    assert first is not None
    with Session(db_engine) as db:
        task = db.get(WorkTask, task_id)
        assert task is not None
        task.lease_expires_at = utc_now() - timedelta(seconds=1)
        db.add(task)
        db.commit()

    assert run_work_task_cycle(db_engine=db_engine, settings=settings) == 1
    with Session(db_engine) as db:
        task = db.get(WorkTask, task_id)
        runs = db.exec(
            select(WorkTaskRun).where(WorkTaskRun.task_id == task_id).order_by(WorkTaskRun.attempt_no)
        ).all()
        assert task is not None and task.status == "review"
        assert task.attempt_count == 2
        assert [run.status for run in runs] == ["stale", "succeeded"]


def test_worker_fails_closed_when_agent_has_no_valid_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_engine = _engine()
    with Session(db_engine) as db:
        manager, _, _ = _seed(db)
        task_id = _create(db, manager, "worker-task-unpublished-agent")

    def reject_release(*_args, **_kwargs):
        raise AgentReleaseError("Digital employee has unpublished changes")

    monkeypatch.setattr(
        "app.work_tasks.worker.verify_agent_release_for_execution",
        reject_release,
    )
    assert _claim_one(db_engine, "tenant_demo", _settings()) is None

    with Session(db_engine) as db:
        task = db.get(WorkTask, task_id)
        events = db.exec(select(WorkTaskEvent).where(WorkTaskEvent.task_id == task_id)).all()
        assert task is not None
        assert task.status == "failed"
        assert task.last_error_code == "agent_release_unavailable"
        assert events[-1].event_type == "agent_release_unavailable"
