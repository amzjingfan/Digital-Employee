from __future__ import annotations

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import AgentProfile, Tenant, User, WorkTask, WorkTaskEvidence
from app.tiktok.mock_replay import persist_tiktok_mock_replay_tasks


def _db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    db = Session(engine)
    db.add(Tenant(id="tenant_demo", name="Demo"))
    db.add(
        User(
            id="admin",
            tenant_id="tenant_demo",
            username="admin",
            role="admin",
            business_role="operations_supervisor",
            password_hash="disabled",
        )
    )
    for agent_id, name, business_role in (
        ("agent_tiktok-content-script", "TikTok 内容", "tiktok_content_specialist"),
        ("agent_ops", "运营主管", "operations_supervisor"),
        ("agent_ads", "广告巡检", "advertising_inspection_specialist"),
        ("agent_tiktok-creator-match", "TikTok 商达", "tiktok_tap_manager"),
        ("agent_tiktok-live-planner", "TikTok 直播", "tiktok_live_operator"),
    ):
        db.add(
            AgentProfile(
                id=agent_id,
                tenant_id="tenant_demo",
                name=name,
                metadata_json={"business_role": business_role},
            )
        )
    db.commit()
    return db


def test_persisted_mock_replays_are_idempotent_task_center_items() -> None:
    with _db() as db:
        admin = db.get(User, "admin")
        assert admin is not None

        first = persist_tiktok_mock_replay_tasks(db, admin)
        second = persist_tiktok_mock_replay_tasks(db, admin)
        tasks = db.exec(select(WorkTask).where(WorkTask.tenant_id == "tenant_demo")).all()
        evidence = db.exec(
            select(WorkTaskEvidence).where(WorkTaskEvidence.tenant_id == "tenant_demo")
        ).all()

        assert first["persisted"] is True
        assert first["persisted_task_count"] == 5
        assert second["persisted_task_count"] == 0
        assert len(tasks) == 5
        assert len(evidence) == 5
        assert {task.status for task in tasks} == {"pending"}
        assert {task.source_type for task in tasks} == {"tiktok_mock_sop_replay"}
        assert {task.assignee_agent_id for task in tasks} == {
            "agent_tiktok-content-script",
            "agent_ops",
            "agent_ads",
            "agent_tiktok-creator-match",
            "agent_tiktok-live-planner",
        }
        assert all(task.input_json["external_writes"] is False for task in tasks)
