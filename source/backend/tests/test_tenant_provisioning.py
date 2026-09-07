from __future__ import annotations

import httpx
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.accounts.casdoor import CasdoorPlatformClient, CasdoorSyncResult
from app.accounts.tenants import provision_tenant, set_tenant_status
from app.api import platform_tenants
from app.config import Settings
from app.db.models import Tenant, TenantLifecycleEvent, User
from app.security.auth import create_access_token, get_current_user, hash_password


class _Provisioner:
    def __init__(self, result: CasdoorSyncResult) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def provision_organization(self, *, name: str, display_name: str) -> CasdoorSyncResult:
        self.calls.append((name, display_name))
        return self.result


def test_tenant_is_created_only_after_casdoor_organization_succeeds() -> None:
    with _test_session() as db:
        provisioner = _Provisioner(CasdoorSyncResult("synced", "created"))
        tenant = provision_tenant(
            db,
            tenant_id="tenant_acme",
            name="Acme Commerce",
            casdoor_organization="acme",
            default_locale="en",
            default_timezone="America/Los_Angeles",
            default_currency="usd",
            actor_ref="platform-test",
            provisioner=provisioner,
        )
        assert tenant.status == "active"
        assert tenant.identity_sync_status == "synced"
        assert tenant.default_currency == "USD"
        assert provisioner.calls == [("acme", "Acme Commerce")]
        assert db.exec(select(TenantLifecycleEvent)).one().event_type == "tenant_provisioned"

        same = provision_tenant(
            db,
            tenant_id="tenant_acme",
            name="Acme Commerce",
            casdoor_organization="acme",
            default_locale="en",
            default_timezone="UTC",
            default_currency="USD",
            actor_ref="platform-test",
            provisioner=provisioner,
        )
        assert same.id == tenant.id
        assert len(provisioner.calls) == 1


def test_failed_casdoor_provisioning_does_not_create_platform_tenant() -> None:
    with _test_session() as db:
        provisioner = _Provisioner(CasdoorSyncResult("failed", "permission_denied"))
        try:
            provision_tenant(
                db,
                tenant_id="tenant_failed",
                name="Failed Tenant",
                casdoor_organization="failed",
                default_locale="en",
                default_timezone="UTC",
                default_currency="USD",
                actor_ref="platform-test",
                provisioner=provisioner,
            )
        except HTTPException as error:
            assert error.status_code == 502
        else:
            raise AssertionError("platform tenant must not exist after Casdoor failure")
        assert db.get(Tenant, "tenant_failed") is None
        event = db.exec(select(TenantLifecycleEvent)).one()
        assert event.outcome == "denied"
        assert event.reason == "permission_denied"


def test_tenant_suspension_blocks_existing_user_session() -> None:
    with _test_session() as db:
        tenant = Tenant(id="tenant_demo", name="Demo")
        user = User(
            id="user_demo",
            tenant_id=tenant.id,
            username="demo",
            password_hash=hash_password("secret"),
        )
        db.add(tenant)
        db.add(user)
        db.commit()
        token = create_access_token(user)

        set_tenant_status(
            db,
            tenant_id=tenant.id,
            status="suspended",
            reason="contract ended",
            actor_ref="platform-test",
        )
        try:
            get_current_user(_request_with_cookie(token), None, db)
        except HTTPException as error:
            assert error.status_code == 401
            assert error.detail == "Tenant is not active"
        else:
            raise AssertionError("suspended tenant session must be rejected")


def test_platform_api_key_is_disabled_and_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        platform_tenants,
        "get_settings",
        lambda: Settings(_env_file=None, platform_admin_api_enabled=False),
    )
    try:
        platform_tenants.require_platform_key("x" * 32)
    except HTTPException as error:
        assert error.status_code == 404
    else:
        raise AssertionError("disabled platform API must not authenticate")

    monkeypatch.setattr(
        platform_tenants,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            platform_admin_api_enabled=True,
            platform_admin_api_key="correct-key-that-is-at-least-32-bytes",
        ),
    )
    try:
        platform_tenants.require_platform_key("wrong-key-that-is-at-least-32-byte")
    except HTTPException as error:
        assert error.status_code == 401
    else:
        raise AssertionError("wrong platform API key must not authenticate")


def test_casdoor_platform_client_reconciles_existing_organization() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/api/login/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "platform-token"})
        if request.url.path.endswith("/api/get-organization"):
            assert request.headers["authorization"] == "Bearer platform-token"
            return httpx.Response(200, json={"status": "ok", "data": {"name": "acme"}})
        raise AssertionError("existing organization must not be added again")

    settings = Settings(
        _env_file=None,
        casdoor_platform_endpoint="https://identity.example",
        casdoor_platform_client_id="platform-client",
        casdoor_platform_client_secret="platform-secret",
    )
    result = CasdoorPlatformClient(
        settings,
        transport=httpx.MockTransport(handler),
    ).provision_organization(name="acme", display_name="Acme")
    assert result.status == "exists"
    assert calls == [
        "/api/login/oauth/access_token",
        "/api/get-organization",
    ]


def _test_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _request_with_cookie(token: str):
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/me",
            "headers": [(b"cookie", f"staffdeck_session={token}".encode("ascii"))],
        }
    )
