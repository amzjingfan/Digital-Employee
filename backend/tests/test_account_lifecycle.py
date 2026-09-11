from __future__ import annotations

import httpx
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select
from starlette.requests import Request

from app.accounts.casdoor import CasdoorManagementClient
from app.api.auth import (
    LoginRequest,
    TenantPreferencesRequest,
    UserForceLogoutRequest,
    UserInvitationAcceptRequest,
    UserInvitationCreateRequest,
    UserPreferencesRequest,
    UserStatusRequest,
    accept_user_invitation,
    force_logout_user,
    get_preferences,
    invite_user,
    login,
    set_user_status,
    update_preferences,
    update_tenant_preferences,
)
from app.api.oidc import _upsert_user_identity
from app.config import Settings
from app.db.models import AccountLifecycleEvent, Tenant, User, UserInvitation
from app.security.auth import create_access_token, get_current_user, hash_password


def test_local_invitation_is_one_time_and_stores_only_digest() -> None:
    with _test_session() as db:
        admin = _seed(db)
        created = invite_user(
            UserInvitationCreateRequest(
                tenant_id="tenant_demo",
                username="buyer",
                display_name="Buyer",
                business_role="procurement_specialist",
            ),
            admin,
            db,
        )
        row = db.get(UserInvitation, created.id)
        assert row is not None
        assert created.invite_token not in row.token_digest
        assert len(row.token_digest) == 64

        accepted = accept_user_invitation(
            UserInvitationAcceptRequest(
                tenant_id="tenant_demo",
                token=created.invite_token,
                password="strong-password",
            ),
            db,
        )
        assert accepted.user.username == "buyer"
        assert accepted.user.business_role == "procurement_specialist"
        assert db.get(UserInvitation, created.id).status == "accepted"

        try:
            accept_user_invitation(
                UserInvitationAcceptRequest(
                    tenant_id="tenant_demo",
                    token=created.invite_token,
                    password="strong-password",
                ),
                db,
            )
        except HTTPException as error:
            assert error.status_code == 409
        else:
            raise AssertionError("an invitation token must not be reusable")

        events = db.exec(
            select(AccountLifecycleEvent).order_by(AccountLifecycleEvent.occurred_at)
        ).all()
        assert [event.event_type for event in events] == [
            "user_invited",
            "invitation_accepted",
        ]


def test_suspension_revokes_existing_session_and_blocks_password_login() -> None:
    with _test_session() as db:
        admin = _seed(db)
        member = _member(db)
        old_token = create_access_token(member)

        updated = set_user_status(
            member.id,
            UserStatusRequest(
                tenant_id="tenant_demo", status="suspended", reason="offboarding"
            ),
            admin,
            db,
        )
        assert updated.status == "suspended"
        assert updated.session_version == 2

        try:
            get_current_user(_request_with_cookie(old_token), None, db)
        except HTTPException as error:
            assert error.status_code == 401
            assert error.detail == "Account is suspended"
        else:
            raise AssertionError("suspended session must be rejected")

        try:
            login(LoginRequest(tenant_id="tenant_demo", username="member", password="secret"), db)
        except HTTPException as error:
            assert error.status_code == 401
        else:
            raise AssertionError("suspended account must not log in")


def test_force_logout_invalidates_all_existing_staffdeck_tokens() -> None:
    with _test_session() as db:
        admin = _seed(db)
        member = _member(db)
        old_token = create_access_token(member)

        updated = force_logout_user(
            member.id,
            UserForceLogoutRequest(tenant_id="tenant_demo", reason="security review"),
            admin,
            db,
        )
        assert updated.session_version == 2
        try:
            get_current_user(_request_with_cookie(old_token), None, db)
        except HTTPException as error:
            assert error.status_code == 401
            assert error.detail == "Session has been revoked"
        else:
            raise AssertionError("revoked token must not authenticate")

        fresh = db.get(User, member.id)
        assert get_current_user(_request_with_cookie(create_access_token(fresh)), None, db).id == member.id


def test_tenant_admin_cannot_manage_another_tenant_account() -> None:
    with _test_session() as db:
        admin = _seed(db)
        db.add(Tenant(id="tenant_other", name="Other"))
        other = User(
            id="user_other",
            tenant_id="tenant_other",
            username="member",
            password_hash=hash_password("secret"),
        )
        db.add(other)
        db.commit()

        try:
            set_user_status(
                other.id,
                UserStatusRequest(
                    tenant_id="tenant_other", status="suspended", reason="attempted crossover"
                ),
                admin,
                db,
            )
        except HTTPException as error:
            assert error.status_code == 403
        else:
            raise AssertionError("tenant admin must not manage another tenant")


def test_suspended_oidc_identity_is_not_reactivated_by_new_claims() -> None:
    with _test_session() as db:
        _seed(db)
        user = User(
            id="oidc_user",
            tenant_id="tenant_demo",
            username="joe",
            source="oidc",
            authorization_source="oidc_groups",
            business_role="operations_supervisor",
            status="suspended",
            password_hash=hash_password("unusable-password"),
        )
        db.add(user)
        db.commit()

        try:
            _upsert_user_identity(
                db,
                tenant_id="tenant_demo",
                issuer="https://issuer.example",
                subject="joe-subject",
                username="joe",
                display_name="Joe",
                role="member",
                business_role="operations_supervisor",
                groups=["acme/operations"],
            )
        except HTTPException as error:
            assert error.status_code == 403
        else:
            raise AssertionError("OIDC callback must not reactivate a suspended local mapping")
        assert db.get(User, user.id).status == "suspended"


def test_failed_password_attempts_lock_known_account(monkeypatch) -> None:
    with _test_session() as db:
        _seed(db)
        member = _member(db)
        settings = Settings(
            _env_file=None,
            auth_failed_login_limit=2,
            auth_failed_login_lock_seconds=60,
        )
        monkeypatch.setattr("app.api.auth.get_settings", lambda: settings)
        for _ in range(2):
            try:
                login(
                    LoginRequest(
                        tenant_id="tenant_demo", username=member.username, password="wrong"
                    ),
                    db,
                )
            except HTTPException as error:
                assert error.status_code == 401
        db.refresh(member)
        assert member.locked_until is not None


def test_casdoor_status_sync_uses_client_credentials_and_partial_update() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/api/login/oauth/access_token"):
            assert request.method == "POST"
            assert b'"client_secret":"management-secret"' in request.content
            return httpx.Response(200, json={"access_token": "short-lived-token"})
        assert request.url.path.endswith("/api/update-user")
        assert request.url.params["columns"] == "isForbidden"
        assert request.headers["authorization"] == "Bearer short-lived-token"
        assert b'"owner":"acme"' in request.content
        assert b'"isForbidden":true' in request.content
        return httpx.Response(200, json={"status": "ok", "msg": ""})

    settings = Settings(
        _env_file=None,
        casdoor_management_enabled=True,
        casdoor_management_endpoint="https://identity.example",
        casdoor_management_client_id="management-client",
        casdoor_management_client_secret="management-secret",
    )
    result = CasdoorManagementClient(
        settings,
        transport=httpx.MockTransport(handler),
    ).sync_user_forbidden(organization="acme", username="joe", forbidden=True)
    assert result.status == "synced"
    assert len(requests) == 2


def test_casdoor_status_sync_is_explicitly_disabled_by_default() -> None:
    result = CasdoorManagementClient(Settings(_env_file=None)).sync_user_forbidden(
        organization="acme", username="joe", forbidden=True
    )
    assert result.status == "not_configured"
    assert result.reason == "casdoor_management_disabled"


def test_casdoor_management_pull_reconciles_groups_and_forbidden_state() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/api/login/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "short-lived-token"})
        assert request.url.path.endswith("/api/get-users")
        assert request.url.params["owner"] == "acme"
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "data": [
                    {
                        "name": "joe",
                        "displayName": "Joe",
                        "groups": ["joukir/tiktok-shop"],
                        "isForbidden": True,
                    }
                ],
            },
        )

    settings = Settings(
        _env_file=None,
        casdoor_management_enabled=True,
        casdoor_management_endpoint="https://identity.example",
        casdoor_management_client_id="management-client",
        casdoor_management_client_secret="management-secret",
        oidc_group_role_mapping_json='{"joukir/tiktok-shop":"tiktok_shop_operator"}',
    )
    with _test_session() as db:
        from app.tiktok.service import bootstrap_tiktok_organization

        admin = _seed(db)
        bootstrap_tiktok_organization(db, admin)
        joe = User(
            id="joe",
            tenant_id="tenant_demo",
            username="joe",
            role="member",
            business_role="member",
            authorization_source="oidc",
            source="oidc",
            password_hash="disabled",
        )
        db.add(joe)
        db.commit()
        result = CasdoorManagementClient(
            settings,
            transport=httpx.MockTransport(handler),
        ).sync_organization_users(db, organization="acme", tenant_id="tenant_demo")
        db.refresh(joe)

        assert result.status == "synced"
        assert result.scanned_count == 1
        assert result.changed_count == 1
        assert joe.business_role == "tiktok_shop_operator"
        assert joe.status == "suspended"
        assert len(requests) == 2


def test_user_preference_overrides_tenant_default_and_is_persisted() -> None:
    with _test_session() as db:
        admin = _seed(db)
        tenant_defaults = update_tenant_preferences(
            TenantPreferencesRequest(
                tenant_id="tenant_demo",
                default_locale="en",
                default_timezone="UTC",
                default_currency="usd",
            ),
            admin,
            db,
        )
        assert tenant_defaults.tenant_default_locale == "en"
        assert tenant_defaults.tenant_default_currency == "USD"
        assert tenant_defaults.effective_locale == "en"

        personal = update_preferences(
            UserPreferencesRequest(locale="zh-CN", timezone="Asia/Shanghai"),
            admin,
            db,
        )
        assert personal.user_locale == "zh-CN"
        assert personal.effective_locale == "zh-CN"
        assert personal.effective_timezone == "Asia/Shanghai"
        assert get_preferences(admin, db).effective_locale == "zh-CN"


def _seed(db: Session) -> User:
    db.add(Tenant(id="tenant_demo", name="Demo"))
    admin = User(
        id="admin",
        tenant_id="tenant_demo",
        username="admin",
        role="admin",
        business_role="platform_admin",
        password_hash=hash_password("admin"),
    )
    db.add(admin)
    db.commit()
    return admin


def _member(db: Session) -> User:
    member = User(
        id="member",
        tenant_id="tenant_demo",
        username="member",
        password_hash=hash_password("secret"),
    )
    db.add(member)
    db.commit()
    return member


def _request_with_cookie(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/me",
            "headers": [(b"cookie", f"staffdeck_session={token}".encode("ascii"))],
        }
    )


def _test_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)
