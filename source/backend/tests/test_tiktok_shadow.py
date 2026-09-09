from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import Settings
from app.db.models import Tenant, User, WorkTask, WorkTaskEvent, WorkTaskEvidence, utc_now
from app.tiktok.schema import TikTokShadowEvaluationCreate
from app.tiktok.service import get_tiktok_production_readiness
from app.tiktok.shadow import (
    TikTokShadowError,
    get_shadow_quality,
    get_shadow_run,
    heartbeat_shadow_run,
    record_shadow_evaluation,
    record_shadow_observation,
    shadow_run_is_release_ready,
    start_shadow_run,
)


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    db = Session(engine)
    db.add(Tenant(id="tenant_demo", name="Demo"))
    admin = User(
        id="admin",
        tenant_id="tenant_demo",
        username="admin",
        role="admin",
        business_role="platform_admin",
        password_hash="disabled",
    )
    member = User(
        id="member",
        tenant_id="tenant_demo",
        username="member",
        role="member",
        business_role="tiktok_shop_operator",
        password_hash="disabled",
    )
    db.add(admin)
    db.add(member)
    db.commit()
    return db


def test_shadow_run_is_idempotent_and_observations_are_read_only() -> None:
    with _session() as db:
        admin = db.get(User, "admin")
        assert admin is not None
        first = start_shadow_run(db, admin)
        second = start_shadow_run(db, admin)
        assert first.id == second.id
        assert (first.ends_at - first.started_at) == timedelta(days=14)
        observed = record_shadow_observation(db, tenant_id="tenant_demo", error=True)
        assert observed is not None
        assert observed.observation_count == 1
        assert observed.error_count == 1
        assert observed.baseline_json["writes_enabled"] is False
        assert len(observed.baseline_json["observation_days_utc"]) == 1
        assert get_shadow_run(db, "tenant_demo").id == first.id


def test_shadow_run_requires_tenant_admin() -> None:
    with _session() as db:
        member = db.get(User, "member")
        assert member is not None
        with pytest.raises(TikTokShadowError):
            start_shadow_run(db, member)


def test_shadow_run_without_observations_expires_instead_of_passing() -> None:
    with _session() as db:
        admin = db.get(User, "admin")
        assert admin is not None
        run = start_shadow_run(db, admin)
        run.ends_at = run.started_at
        db.add(run)
        db.commit()
        expired = heartbeat_shadow_run(db, "tenant_demo")
        assert expired is not None
        assert expired.status == "expired"
        assert shadow_run_is_release_ready(expired) is False


def test_shadow_run_requires_fourteen_observation_days_and_final_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started_at = datetime(2026, 8, 1, 3, 0, tzinfo=UTC).replace(tzinfo=None)
    current = started_at
    monkeypatch.setattr("app.tiktok.shadow.utc_now", lambda: current)
    with _session() as db:
        admin = db.get(User, "admin")
        assert admin is not None
        run = start_shadow_run(db, admin)
        for day in range(14):
            current = started_at + timedelta(days=day)
            observed = record_shadow_observation(db, tenant_id="tenant_demo")
            assert observed is not None

        assert shadow_run_is_release_ready(run) is False
        current = started_at + timedelta(days=14)
        completed = heartbeat_shadow_run(db, "tenant_demo")

        assert completed is not None
        assert completed.status == "completed"
        assert completed.observation_count == 14
        assert len(completed.baseline_json["observation_days_utc"]) == 14
        assert shadow_run_is_release_ready(completed) is True


def test_shadow_worker_tenant_list_is_explicit_for_rls() -> None:
    settings = Settings(_env_file=None, tiktok_shadow_tenant_ids=" tenant_demo, tenant_two ")

    assert settings.tiktok_shadow_tenant_id_list == ["tenant_demo", "tenant_two"]


def _review_task(
    db: Session, *, index: int, sop_id: str, tenant_id: str = "tenant_demo"
) -> WorkTask:
    task = WorkTask(
        id=f"task-{tenant_id}-{index}",
        tenant_id=tenant_id,
        idempotency_key=f"shadow:{tenant_id}:{index}",
        source_type="tiktok_shadow_read",
        source_id=f"source-{index}",
        title=f"Shadow task {index}",
        owner_business_role="tiktok_content_specialist",
        assigned_by_user_id="admin",
        status="review",
        input_json={"sop_id": sop_id, "external_writes": False},
    )
    db.add(task)
    db.commit()
    return task


def _evaluation(task_id: str, *, verdict: str = "adopted", issue: str = "none"):
    return TikTokShadowEvaluationCreate(
        task_id=task_id,
        verdict=verdict,
        issue_category=issue,
        summary="脱敏人工对照结论",
    )


def test_shadow_evaluation_is_task_linked_append_only_and_idempotent() -> None:
    with _session() as db:
        admin = db.get(User, "admin")
        assert admin is not None
        run = start_shadow_run(db, admin)
        task = _review_task(db, index=1, sop_id="TT-SOP-002")

        created = record_shadow_evaluation(db, admin, _evaluation(task.id))
        repeated = record_shadow_evaluation(db, admin, _evaluation(task.id))

        assert repeated.recorded_at == created.recorded_at
        assert created.quality.reviewed_count == 1
        assert created.quality.adopted_count == 1
        assert created.quality.passed is False
        evidence = db.exec(
            select(WorkTaskEvidence).where(WorkTaskEvidence.task_id == task.id)
        ).all()
        events = db.exec(select(WorkTaskEvent).where(WorkTaskEvent.task_id == task.id)).all()
        assert len(evidence) == 1
        assert evidence[0].source_id == run.id
        assert evidence[0].summary == "脱敏人工对照结论"
        assert evidence[0].source_route.endswith("/none/TT-SOP-002")
        assert len(events) == 1
        assert events[0].actor_id == admin.id
        assert events[0].detail_json["sop_id"] == "TT-SOP-002"
        assert events[0].detail_json["external_writes"] is False

        task.input_json = {"sop_id": "TT-SOP-003", "external_writes": False}
        db.add(task)
        db.commit()
        assert get_shadow_quality(db, run).covered_sop_ids == ["TT-SOP-002"]

        with pytest.raises(TikTokShadowError, match="immutable"):
            record_shadow_evaluation(
                db,
                admin,
                TikTokShadowEvaluationCreate(
                    task_id=task.id,
                    verdict="rejected",
                    issue_category="other",
                    summary="不同结论不得覆盖",
                ),
            )


def test_shadow_evaluation_rejects_unsafe_or_unready_tasks() -> None:
    with _session() as db:
        admin = db.get(User, "admin")
        assert admin is not None
        start_shadow_run(db, admin)
        task = _review_task(db, index=1, sop_id="TT-SOP-002")
        task.input_json = {"sop_id": "TT-SOP-002", "external_writes": True}
        db.add(task)
        db.commit()

        with pytest.raises(TikTokShadowError, match="read-only"):
            record_shadow_evaluation(db, admin, _evaluation(task.id))
        with pytest.raises(TikTokShadowError, match="cannot be marked as adopted"):
            task.input_json = {"sop_id": "TT-SOP-002", "external_writes": False}
            db.add(task)
            db.commit()
            record_shadow_evaluation(
                db,
                admin,
                _evaluation(task.id, issue="false_claim"),
            )


@pytest.mark.parametrize(
    ("guardrail_issue", "expected_status"),
    [(None, "passed"), ("severe_miss", "blocked")],
)
def test_completed_shadow_readiness_requires_human_quality_evidence(
    guardrail_issue: str | None,
    expected_status: str,
) -> None:
    required_sops = [
        "TT-SOP-002",
        "TT-SOP-003",
        "TT-SOP-004",
        "TT-SOP-007",
        "TT-SOP-009",
    ]
    with _session() as db:
        admin = db.get(User, "admin")
        assert admin is not None
        run = start_shadow_run(db, admin)
        for index in range(30):
            task = _review_task(db, index=index, sop_id=required_sops[index % len(required_sops)])
            issue = guardrail_issue if index == 29 and guardrail_issue else "none"
            verdict = (
                "rejected"
                if issue != "none" or index > 20
                else "needs_revision"
                if index == 20
                else "adopted"
            )
            record_shadow_evaluation(
                db,
                admin,
                _evaluation(task.id, verdict=verdict, issue=issue),
            )

        quality = get_shadow_quality(db, run)
        assert quality.reviewed_count == 30
        assert quality.covered_sop_ids == required_sops
        assert quality.adoption_rate == 0.7
        assert quality.guardrail_issue_count == (1 if guardrail_issue else 0)
        assert quality.passed is (guardrail_issue is None)

        run.started_at = utc_now() - timedelta(days=14, minutes=1)
        run.ends_at = run.started_at + timedelta(days=14)
        baseline = dict(run.baseline_json or {})
        baseline["observation_days_utc"] = [
            (run.started_at + timedelta(days=day)).date().isoformat() for day in range(14)
        ]
        run.baseline_json = baseline
        run.observation_count = 14
        db.add(run)
        db.commit()
        assert heartbeat_shadow_run(db, "tenant_demo").status == "completed"

        readiness = get_tiktok_production_readiness(db, admin)
        shadow_gate = next(gate for gate in readiness.gates if gate.key == "shadow_run")
        assert shadow_gate.status == expected_status


def test_elapsed_shadow_window_without_reviewed_tasks_is_blocked() -> None:
    with _session() as db:
        admin = db.get(User, "admin")
        assert admin is not None
        run = start_shadow_run(db, admin)
        run.started_at = utc_now() - timedelta(days=14, minutes=1)
        run.ends_at = run.started_at + timedelta(days=14)
        run.observation_count = 14
        baseline = dict(run.baseline_json or {})
        baseline["observation_days_utc"] = [
            (run.started_at + timedelta(days=day)).date().isoformat() for day in range(14)
        ]
        run.baseline_json = baseline
        db.add(run)
        db.commit()
        assert heartbeat_shadow_run(db, "tenant_demo").status == "completed"

        readiness = get_tiktok_production_readiness(db, admin)
        shadow_gate = next(gate for gate in readiness.gates if gate.key == "shadow_run")
        assert shadow_gate.status == "blocked"
        assert "人工对照 0/30" in shadow_gate.detail
