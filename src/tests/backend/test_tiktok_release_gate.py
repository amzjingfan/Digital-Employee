from __future__ import annotations

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db.models import Tenant, User
from app.tiktok.service import (
    bootstrap_tiktok_assets,
    get_tiktok_agent_release_preflight,
    publish_tiktok_agent_releases,
)


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
    db.commit()
    return db


def test_tiktok_release_preflight_is_complete_and_publish_is_explicit() -> None:
    with _db() as db:
        admin = db.get(User, "admin")
        assert admin is not None
        bootstrap_tiktok_assets(db, admin)

        preflight = get_tiktok_agent_release_preflight(db, admin)
        assert preflight.ready is True
        assert len(preflight.items) == 5
        assert all(item.ready for item in preflight.items)
        assert all(item.snapshot_digest.startswith("sha256:") for item in preflight.items)

        result = publish_tiktok_agent_releases(db, admin, "APPROVAL-TT-001")
        assert result.published_count == 5
        assert result.approval_reference == "APPROVAL-TT-001"
        assert all(row["version"] == 1 for row in result.releases)

        # Re-running the same baseline is idempotent and does not create version 2.
        repeated = publish_tiktok_agent_releases(db, admin, "APPROVAL-TT-002")
        assert repeated.published_count == 5
        assert all(row["version"] == 1 for row in repeated.releases)
