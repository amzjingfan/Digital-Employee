from __future__ import annotations

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import AgentProfile, Tenant, User, WorkTask
from app.tiktok import mock_replay


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


def test_execute_mock_replays_uses_source_filtered_sandbox_worker(monkeypatch) -> None:
    with _db() as db:
        admin = db.get(User, "admin")
        assert admin is not None
        mock_replay.persist_tiktok_mock_replay_tasks(db, admin)
        calls: list[dict[str, object]] = []

        def fake_cycle(**kwargs):
            calls.append(kwargs)
            return 5

        monkeypatch.setattr(mock_replay, "run_work_task_cycle", fake_cycle)
        result = mock_replay.execute_tiktok_mock_replays(
            db,
            admin,
            db_engine=db.get_bind(),
        )

        assert result["execution_mode"] == "sandbox"
        assert result["processed_count"] == 5
        assert len(result["items"]) == 5
        assert calls[0]["source_type"] == "tiktok_mock_sop_replay"
        assert calls[0]["settings"].work_task_execution_mode == "sandbox"
        assert len(db.exec(select(WorkTask)).all()) == 5
