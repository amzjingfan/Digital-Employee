from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.config import Settings
from app.db.models import Tenant, User
from app.tiktok.shadow import (
    TikTokShadowError,
    get_shadow_run,
    heartbeat_shadow_run,
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
