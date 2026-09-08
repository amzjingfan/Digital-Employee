from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import Settings
from app.db.models import (
    BusinessResource,
    ConnectorSyncState,
    ExternalAuthorization,
    Tenant,
    User,
    utc_now,
)
from app.tiktok.connector import read_tiktok_resource


def _session() -> Session:
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
            business_role="platform_admin",
            password_hash="disabled",
        )
    )
    db.commit()
    return db


def _resource(db: Session, *, resource_type: str, resource_id: str) -> BusinessResource:
    row = BusinessResource(
        id=resource_id,
        tenant_id="tenant_demo",
        resource_type=resource_type,
        code=resource_id,
        name=resource_id,
        created_by_user_id="admin",
        metadata_json={"platform": "tiktok", "market": "US"},
    )
    db.add(row)
    db.commit()
    return row


def _authorization(
    db: Session,
    *,
    authorization_type: str,
    resource_id: str,
    scope: str,
    expires_at: datetime | None = None,
    flow: str = "mock",
) -> ExternalAuthorization:
    row = ExternalAuthorization(
        tenant_id="tenant_demo",
        provider="tiktok",
        authorization_type=authorization_type,
        subject_id=f"{authorization_type}-subject",
        resource_id=resource_id,
        scopes_json=[scope],
        credential_ref="secret://tiktok/tenant/ref",
        token_fingerprint="sha256:redacted",
        expires_at=expires_at,
        metadata_json={"authorization_flow": flow, "official_scopes": [scope]},
    )
    db.add(row)
    db.commit()
    return row


def _assert_no_successful_sync(db: Session) -> None:
    assert db.exec(select(ConnectorSyncState)).all() == []


def test_read_connector_rejects_expired_active_authorization_before_sync() -> None:
    with _session() as db:
        resource = _resource(db, resource_type="store", resource_id="shop-expired")
        _authorization(
            db,
            authorization_type="seller",
            resource_id=resource.id,
            scope="shop.read",
            expires_at=utc_now() - timedelta(seconds=1),
        )

        with pytest.raises(HTTPException) as error:
            read_tiktok_resource(
                db,
                user=db.get(User, "admin"),
                authorization_type="seller",
                resource_id=resource.id,
            )

        assert error.value.status_code == 409
        assert error.value.detail == "tiktok_authorization_expired"
        _assert_no_successful_sync(db)


def test_read_connector_rejects_authorization_type_asset_mismatch_before_sync() -> None:
    with _session() as db:
        resource = _resource(db, resource_type="ad_account", resource_id="ads-wrong-type")
        _authorization(
            db,
            authorization_type="seller",
            resource_id=resource.id,
            scope="shop.read",
        )

        with pytest.raises(HTTPException) as error:
            read_tiktok_resource(
                db,
                user=db.get(User, "admin"),
                authorization_type="seller",
                resource_id=resource.id,
            )

        assert error.value.status_code == 403
        assert error.value.detail == "tiktok_authorization_type_mismatch"
        _assert_no_successful_sync(db)


def test_read_connector_rejects_non_tiktok_asset_before_authorization_lookup() -> None:
    with _session() as db:
        resource = _resource(db, resource_type="ad_account", resource_id="amazon-ads")
        resource.metadata_json = {**resource.metadata_json, "platform": "amazon"}
        db.add(resource)
        db.commit()
        _authorization(
            db,
            authorization_type="ads",
            resource_id=resource.id,
            scope="ads.read",
        )

        with pytest.raises(HTTPException) as error:
            read_tiktok_resource(
                db,
                user=db.get(User, "admin"),
                authorization_type="ads",
                resource_id=resource.id,
            )

        assert error.value.status_code == 404
        assert error.value.detail == "TikTok resource not found"
        _assert_no_successful_sync(db)


@pytest.mark.parametrize(
    ("authorization_type", "resource_type", "scope"),
    [
        ("seller", "store", "shop.read"),
        ("creator", "creator_account", "creator.read"),
        ("partner", "partner_account", "partner.read"),
        ("ads", "ad_account", "ads.read"),
        ("social", "social_account", "social.read"),
        ("social", "live_room", "social.read"),
    ],
)
def test_mock_read_connector_accepts_only_compatible_authorization_asset_pairs(
    authorization_type: str,
    resource_type: str,
    scope: str,
) -> None:
    with _session() as db:
        resource = _resource(
            db,
            resource_type=resource_type,
            resource_id=f"{authorization_type}-{resource_type}",
        )
        _authorization(
            db,
            authorization_type=authorization_type,
            resource_id=resource.id,
            scope=scope,
            expires_at=utc_now() + timedelta(hours=1),
        )

        result = read_tiktok_resource(
            db,
            user=db.get(User, "admin"),
            authorization_type=authorization_type,
            resource_id=resource.id,
        )

        assert result.source == "mock"
        assert result.resource_id == resource.id
        assert result.data["read_only"] is True
        assert len(db.exec(select(ConnectorSyncState)).all()) == 1


@pytest.mark.parametrize("mode", ["live", "replay"])
def test_mock_read_connector_requires_mock_mode(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    monkeypatch.setattr(
        "app.tiktok.connector.get_settings",
        lambda: Settings(_env_file=None, tiktok_connector_mode=mode),
    )
    with _session() as db:
        resource = _resource(db, resource_type="store", resource_id=f"shop-{mode}")
        _authorization(
            db,
            authorization_type="seller",
            resource_id=resource.id,
            scope="shop.read",
            expires_at=utc_now() + timedelta(hours=1),
        )

        with pytest.raises(HTTPException) as error:
            read_tiktok_resource(
                db,
                user=db.get(User, "admin"),
                authorization_type="seller",
                resource_id=resource.id,
            )

        assert error.value.status_code == 503
        assert error.value.detail == "tiktok_connector_unavailable"
        _assert_no_successful_sync(db)


def test_official_seller_read_requires_live_mode_before_constructing_external_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.tiktok.connector.get_settings",
        lambda: Settings(_env_file=None, tiktok_connector_mode="mock"),
    )

    def unexpected_client():
        raise AssertionError("official connector must not construct a client in mock mode")

    monkeypatch.setattr("app.tiktok.connector.TikTokOfficialClient", unexpected_client)
    with _session() as db:
        resource = _resource(db, resource_type="store", resource_id="seller-official-mock-mode")
        _authorization(
            db,
            authorization_type="seller",
            resource_id=resource.id,
            scope="shop.read",
            expires_at=utc_now() + timedelta(hours=1),
            flow="official",
        )

        with pytest.raises(HTTPException) as error:
            read_tiktok_resource(
                db,
                user=db.get(User, "admin"),
                authorization_type="seller",
                resource_id=resource.id,
            )

        assert error.value.status_code == 503
        assert error.value.detail == "tiktok_connector_unavailable"
        _assert_no_successful_sync(db)


def test_official_non_seller_read_fails_before_constructing_external_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_client():
        raise AssertionError("unsupported official connector must not construct a client")

    monkeypatch.setattr("app.tiktok.connector.TikTokOfficialClient", unexpected_client)
    with _session() as db:
        resource = _resource(
            db,
            resource_type="creator_account",
            resource_id="creator-official",
        )
        _authorization(
            db,
            authorization_type="creator",
            resource_id=resource.id,
            scope="creator.read",
            expires_at=utc_now() + timedelta(hours=1),
            flow="official",
        )

        with pytest.raises(HTTPException) as error:
            read_tiktok_resource(
                db,
                user=db.get(User, "admin"),
                authorization_type="creator",
                resource_id=resource.id,
            )

        assert error.value.status_code == 503
        assert error.value.detail == "tiktok_connector_unavailable"
        _assert_no_successful_sync(db)
