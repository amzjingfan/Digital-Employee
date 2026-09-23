from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.config import Settings
from app.db.models import (
    BusinessResource,
    BusinessResourceScope,
    ExternalAuthorization,
    Tenant,
    TikTokShadowRun,
    User,
)
from app.tiktok.service import (
    bootstrap_tiktok_assets,
    bootstrap_tiktok_organization,
    get_tiktok_overview,
    get_tiktok_production_readiness,
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
    db.commit()
    return db


def _user(user_id: str, role: str, *, account_role: str = "member") -> User:
    return User(
        id=user_id,
        tenant_id="tenant_demo",
        username=user_id,
        role=account_role,
        business_role=role,
        password_hash="disabled",
    )


def test_tiktok_organization_bootstrap_is_idempotent_and_admin_only() -> None:
    with _session() as db:
        admin = _user("admin", "member", account_role="admin")
        member = _user("member", "tiktok_shop_operator")
        db.add(admin)
        db.add(member)
        db.commit()

        first = bootstrap_tiktok_organization(db, admin)
        second = bootstrap_tiktok_organization(db, admin)

        assert first.root.code == "tiktok"
        assert len(first.departments) == 6
        assert first.created_count == 7
        assert second.created_count == 0
        assert [item.id for item in first.departments] == [item.id for item in second.departments]

        with pytest.raises(HTTPException) as error:
            bootstrap_tiktok_organization(db, member)
        assert error.value.status_code == 403


def test_tiktok_overview_filters_store_scope_and_tiktok_tasks() -> None:
    with _session() as db:
        admin = _user("admin", "member", account_role="admin")
        operator = _user("operator", "tiktok_shop_operator")
        db.add(admin)
        db.add(operator)
        db.commit()
        bootstrap_tiktok_organization(db, admin)

        visible = BusinessResource(
            id="store_tiktok_us",
            tenant_id="tenant_demo",
            resource_type="store",
            code="TT-US",
            name="TikTok Shop US",
            created_by_user_id=admin.id,
            metadata_json={"platform": "tiktok", "market": "US"},
        )
        hidden = BusinessResource(
            id="store_amazon_us",
            tenant_id="tenant_demo",
            resource_type="store",
            code="AMZ-US",
            name="Amazon US",
            created_by_user_id=admin.id,
            metadata_json={"platform": "amazon", "market": "US"},
        )
        db.add(visible)
        db.add(hidden)
        db.add(
            BusinessResourceScope(
                tenant_id="tenant_demo",
                resource_id=visible.id,
                business_role=operator.business_role,
                access_level="operator",
            )
        )
        db.commit()

        overview = get_tiktok_overview(db, operator)

        assert [resource.id for resource in overview.resources] == [visible.id]
        assert overview.task_counts == {"pending": 0, "in_progress": 0, "review": 0, "completed": 0}
        assert {role.key for role in overview.roles} == {
            "tiktok_bd_specialist",
            "tiktok_content_specialist",
            "tiktok_shop_operator",
            "tiktok_media_buyer",
            "tiktok_tap_manager",
            "tiktok_live_operator",
        }


def test_tiktok_production_readiness_does_not_count_mock_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        casdoor_management_enabled=True,
        casdoor_management_endpoint="http://casdoor",
        casdoor_management_client_id="management-client",
        casdoor_management_client_secret="management-secret",
    )
    monkeypatch.setattr("app.tiktok.service.get_settings", lambda: settings)

    with _session() as db:
        admin = _user("admin", "tenant_admin", account_role="admin")
        db.add(admin)
        db.commit()
        bootstrap_tiktok_organization(db, admin)
        bootstrap_tiktok_assets(db, admin)
        db.add(
            ExternalAuthorization(
                tenant_id="tenant_demo",
                provider="tiktok",
                authorization_type="seller",
                subject_id="mock-seller",
                status="active",
                metadata_json={"authorization_flow": "mock"},
            )
        )
        db.commit()

        readiness = get_tiktok_production_readiness(db, admin)

    gates = {gate.key: gate for gate in readiness.gates}
    assert readiness.ready is False
    assert gates["casdoor_management"].status == "passed"
    assert gates["tiktok_official_authorization"].status == "blocked"
    assert "官方 App" in gates["tiktok_official_authorization"].detail
    assert gates["runtime_security_config"].status == "blocked"
    assert gates["identity_mfa"].status == "blocked"
    assert gates["transport_tls"].status == "blocked"
    assert gates["credential_rotation"].status == "blocked"
    assert gates["postgres_restore"].status == "blocked"
    assert gates["business_signoff"].status == "blocked"
    assert gates["security_signoff"].status == "blocked"
    assert gates["product_signoff"].status == "blocked"
    assert gates["agent_releases"].status == "waiting"
    assert gates["shadow_run"].status == "waiting"
    assert gates["external_writes"].status == "passed"
    assert "34 条冻结路由" in gates["external_writes"].detail
    assert "15 个 TikTok Python 文件" in gates["external_writes"].detail


def test_tiktok_production_readiness_blocks_when_live_write_audit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.tiktok.service.verify_tiktok_live_write_disabled",
        lambda: {
            "ok": False,
            "route_count": 22,
            "skill_count": 12,
            "issues": ["unreviewed_tiktok_route:POST /ads/budget"],
        },
    )

    with _session() as db:
        admin = _user("admin", "tenant_admin", account_role="admin")
        db.add(admin)
        db.commit()
        readiness = get_tiktok_production_readiness(db, admin)

    gates = {gate.key: gate for gate in readiness.gates}
    assert readiness.ready is False
    assert gates["external_writes"].status == "blocked"
    assert "unreviewed_tiktok_route:POST /ads/budget" in gates["external_writes"].detail


def test_tiktok_production_readiness_blocks_non_live_connector_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        casdoor_management_enabled=True,
        casdoor_management_endpoint="http://casdoor",
        casdoor_management_client_id="management-client",
        casdoor_management_client_secret="management-secret",
        tiktok_official_enabled=True,
        tiktok_connector_mode="mock",
        tiktok_app_key="app-key",
        tiktok_app_secret="app-secret",
        tiktok_service_id="service-id",
        tiktok_redirect_uri="http://localhost/callback",
        tiktok_token_store_file="/var/run/tiktok/tokens.json",
    )
    monkeypatch.setattr("app.tiktok.service.get_settings", lambda: settings)
    with _session() as db:
        admin = _user("admin", "tenant_admin", account_role="admin")
        db.add(admin)
        db.add(
            ExternalAuthorization(
                tenant_id="tenant_demo",
                provider="tiktok",
                authorization_type="seller",
                subject_id="official-seller",
                status="active",
                metadata_json={"authorization_flow": "official"},
            )
        )
        db.commit()
        readiness = get_tiktok_production_readiness(db, admin)

    gates = {gate.key: gate for gate in readiness.gates}
    assert readiness.ready is False
    assert gates["tiktok_connector_mode"].status == "blocked"
    assert "live" in gates["tiktok_connector_mode"].detail
    assert gates["tiktok_official_authorization"].status == "passed"


def test_tiktok_production_readiness_rejects_empty_completed_shadow_run() -> None:
    started_at = datetime(2026, 8, 1, 3, 0, tzinfo=UTC).replace(tzinfo=None)
    with _session() as db:
        admin = _user("admin", "tenant_admin", account_role="admin")
        db.add(admin)
        db.add(
            TikTokShadowRun(
                tenant_id="tenant_demo",
                status="completed",
                started_at=started_at,
                ends_at=started_at + timedelta(days=14),
                last_heartbeat_at=started_at + timedelta(days=14),
                started_by_user_id=admin.id,
                baseline_json={"mode": "read_only", "writes_enabled": False},
            )
        )
        db.commit()

        readiness = get_tiktok_production_readiness(db, admin)

    gate = {item.key: item for item in readiness.gates}["shadow_run"]
    assert gate.status == "blocked"
    assert "shadow_observation_count_below_14" in gate.detail
    assert "shadow_observation_days_below_14" in gate.detail
