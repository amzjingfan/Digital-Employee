from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import AgentServiceIdentity, Tenant, User
from app.tiktok import service as tiktok_service
from app.tiktok.service import bootstrap_tiktok_assets, verify_tiktok_m2m_identities
from app.work_tasks.m2m import ServiceIdentityError, ServiceTokenReceipt


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
        business_role="operations_supervisor",
        password_hash="disabled",
    )
    db.add(admin)
    db.commit()
    bootstrap_tiktok_assets(db, admin)
    return db


def _receipt(identity: AgentServiceIdentity) -> ServiceTokenReceipt:
    return ServiceTokenReceipt(
        subject=f"admin/{identity.application_name}",
        audience=(identity.client_id,),
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
        token_fingerprint="sha256:test",
    )


def test_m2m_verification_records_all_five_successes(monkeypatch) -> None:
    with _session() as db:
        monkeypatch.setattr(
            tiktok_service,
            "authenticate_service_identity",
            lambda identity, settings: _receipt(identity),
        )

        result = verify_tiktok_m2m_identities(db, db.get(User, "admin"))

        assert result.verified_count == 5
        assert result.failed_count == 0
        assert all(item.status == "verified" for item in result.items)
        identities = db.exec(
            select(AgentServiceIdentity).where(
                AgentServiceIdentity.tenant_id == "tenant_demo"
            )
        ).all()
        assert len(identities) == 5
        assert all(identity.last_verified_at is not None for identity in identities)
        assert all(identity.last_error_code is None for identity in identities)


def test_m2m_verification_records_failure_without_exposing_secret(monkeypatch) -> None:
    with _session() as db:
        def authenticate(identity, settings):
            if identity.agent_id.endswith("creator-match"):
                raise ServiceIdentityError(
                    "service_token_validation_failed",
                    "token validation failed",
                )
            return _receipt(identity)

        monkeypatch.setattr(tiktok_service, "authenticate_service_identity", authenticate)

        result = verify_tiktok_m2m_identities(db, db.get(User, "admin"))

        assert result.verified_count == 4
        assert result.failed_count == 1
        failed = next(item for item in result.items if item.status == "failed")
        assert failed.error_code == "service_token_validation_failed"
        assert "secret" not in failed.model_dump_json().lower()
        identity = db.exec(
            select(AgentServiceIdentity).where(
                AgentServiceIdentity.agent_id == "agent_tiktok-creator-match"
            )
        ).one()
        assert identity.last_error_code == "service_token_validation_failed"
