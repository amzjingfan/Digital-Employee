from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.accounts.casdoor import CasdoorMembershipSyncResult
from app.api import identity_roles
from app.config import Settings
from app.db.models import User


def _admin() -> User:
    return User(
        id="admin",
        tenant_id="tenant_demo",
        username="admin",
        display_name="Admin",
        role="admin",
        business_role="tenant_admin",
        password_hash="disabled",
    )


def test_manual_management_reconcile_is_tenant_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        _env_file=None,
        casdoor_management_enabled=True,
        casdoor_management_endpoint="http://casdoor",
        casdoor_management_client_id="management-client",
        casdoor_management_client_secret="management-secret",
        casdoor_management_sync_interval_seconds=900,
    )
    calls: list[set[str] | None] = []

    monkeypatch.setattr(identity_roles, "get_settings", lambda: settings)
    monkeypatch.setattr(
        identity_roles,
        "mapped_organizations",
        lambda _: {"九头蛇": "tenant_demo", "other": "tenant_other"},
    )
    monkeypatch.setattr(
        identity_roles,
        "reconcile_once",
        lambda **kwargs: (
            calls.append(kwargs["tenant_ids"])
            or [CasdoorMembershipSyncResult("synced", "casdoor_users_reconciled", 5, 1)]
        ),
    )

    result = identity_roles.reconcile_management_memberships(_admin())

    assert calls == [{"tenant_demo"}]
    assert result == {
        "status": "synced",
        "reason": "casdoor_users_reconciled",
        "scanned_count": 5,
        "changed_count": 1,
        "sync_interval_seconds": 900,
    }


def test_manual_management_reconcile_rejects_non_admin() -> None:
    member = _admin()
    member.role = "member"

    with pytest.raises(HTTPException) as error:
        identity_roles.reconcile_management_memberships(member)

    assert error.value.status_code == 403
