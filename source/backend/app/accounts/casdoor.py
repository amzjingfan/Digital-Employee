from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.db.models import User, utc_now
from app.security.business_roles import (
    GroupRoleMappingError,
    normalized_group_claim,
    parse_group_role_mapping,
    resolve_business_role,
)

logger = logging.getLogger(__name__)


class CasdoorManagementError(RuntimeError):
    pass


@dataclass(frozen=True)
class CasdoorSyncResult:
    status: str
    reason: str


@dataclass(frozen=True)
class CasdoorMembershipSyncResult:
    status: str
    reason: str
    scanned_count: int = 0
    changed_count: int = 0


class CasdoorManagementClient:
    """Narrow Casdoor management adapter for tenant-local account state.

    The client intentionally exposes only the reviewed partial user update used
    by StaffDeck. It never logs or persists the client secret or access token.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.transport = transport

    def sync_user_forbidden(
        self, *, organization: str | None, username: str, forbidden: bool
    ) -> CasdoorSyncResult:
        if not self.settings.casdoor_management_enabled:
            return CasdoorSyncResult("not_configured", "casdoor_management_disabled")
        endpoint = self.settings.casdoor_management_endpoint.rstrip("/")
        client_id = self.settings.casdoor_management_client_id.strip()
        client_secret = self.settings.casdoor_management_client_secret
        if not endpoint or not client_id or not client_secret or not organization:
            return CasdoorSyncResult("failed", "casdoor_management_incomplete")
        try:
            with httpx.Client(
                timeout=self.settings.casdoor_management_timeout_seconds,
                transport=self.transport,
            ) as client:
                token_response = client.post(
                    f"{endpoint}/api/login/oauth/access_token",
                    json={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                    headers={"Accept": "application/json"},
                )
                token_response.raise_for_status()
                token_payload = token_response.json()
                access_token = (
                    str(token_payload.get("access_token") or "")
                    if isinstance(token_payload, dict)
                    else ""
                )
                if not access_token:
                    raise CasdoorManagementError("casdoor_token_missing")
                update_response = client.post(
                    f"{endpoint}/api/update-user",
                    params={"columns": "isForbidden"},
                    json={
                        "owner": organization,
                        "name": username,
                        "isForbidden": forbidden,
                    },
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                        "Accept-Language": "en",
                    },
                )
                update_response.raise_for_status()
                payload = update_response.json()
                if not isinstance(payload, dict) or payload.get("status") != "ok":
                    raise CasdoorManagementError("casdoor_update_rejected")
        except (httpx.HTTPError, ValueError, CasdoorManagementError) as exc:
            logger.warning("Casdoor user status synchronization failed: %s", type(exc).__name__)
            return CasdoorSyncResult("failed", str(exc)[:200])
        return CasdoorSyncResult("synced", "casdoor_user_updated")

    def sync_organization_users(
        self,
        db: Session,
        *,
        organization: str,
        tenant_id: str,
    ) -> CasdoorMembershipSyncResult:
        """Pull Casdoor users and reconcile OIDC role/status state locally.

        Casdoor is authoritative for OIDC users. Missing users are not revoked
        from Joukir in this pull because a partial or paginated response must
        never be interpreted as a complete directory.
        """

        if not self.settings.casdoor_management_enabled:
            return CasdoorMembershipSyncResult("not_configured", "casdoor_management_disabled")
        endpoint = self.settings.casdoor_management_endpoint.rstrip("/")
        client_id = self.settings.casdoor_management_client_id.strip()
        client_secret = self.settings.casdoor_management_client_secret
        if not endpoint or not client_id or not client_secret or not organization.strip():
            return CasdoorMembershipSyncResult("failed", "casdoor_management_incomplete")
        try:
            mapping = parse_group_role_mapping(self.settings.oidc_group_role_mapping_json)
            with httpx.Client(
                timeout=self.settings.casdoor_management_timeout_seconds,
                transport=self.transport,
            ) as client:
                access_token = self._access_token(client, endpoint, client_id, client_secret)
                response = client.get(
                    f"{endpoint}/api/get-users",
                    params={"owner": organization.strip()},
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                        "Accept-Language": "en",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                remote_users = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(remote_users, list):
                    raise CasdoorManagementError("casdoor_users_payload_invalid")
        except (httpx.HTTPError, ValueError, CasdoorManagementError, GroupRoleMappingError) as exc:
            logger.warning("Casdoor membership reconciliation failed: %s", type(exc).__name__)
            return CasdoorMembershipSyncResult("failed", str(exc)[:200])

        remote_by_name = {
            str(row.get("name") or "").strip(): row
            for row in remote_users
            if isinstance(row, dict) and str(row.get("name") or "").strip()
        }
        local_users = db.exec(
            select(User).where(
                User.tenant_id == tenant_id,
                (User.source == "oidc") | (User.authorization_source == "oidc"),
            )
        ).all()
        changed_count = 0
        for user in local_users:
            remote = remote_by_name.get(user.username)
            if remote is None:
                continue
            raw_groups = remote.get("groups")
            if not isinstance(raw_groups, list):
                raw_groups = remote.get("roles") if isinstance(remote.get("roles"), list) else []
            try:
                groups = normalized_group_claim(raw_groups)
                business_role = resolve_business_role(
                    groups=groups,
                    mapping=mapping,
                    require_mapped_group=self.settings.oidc_require_mapped_group,
                )
            except GroupRoleMappingError:
                user.identity_sync_status = "error"
                user.updated_at = utc_now()
                db.add(user)
                continue
            desired_status = "suspended" if remote.get("isForbidden") is True else "active"
            display_name = str(remote.get("displayName") or user.display_name or user.username)[:80]
            changed = (
                user.business_role != business_role
                or user.status != desired_status
                or user.identity_groups_json != groups
                or user.display_name != display_name
                or user.identity_sync_status != "synced"
            )
            user.business_role = business_role
            user.status = desired_status
            user.display_name = display_name
            user.identity_groups_json = groups
            user.role_synced_at = utc_now()
            user.identity_sync_status = "synced"
            user.updated_at = utc_now()
            db.add(user)
            if business_role.startswith("tiktok_"):
                from app.tiktok.service import reconcile_casdoor_membership

                reconcile_casdoor_membership(db, user, source="casdoor_management")
            if changed:
                from app.accounts.lifecycle import record_account_event

                record_account_event(
                    db,
                    tenant_id=tenant_id,
                    event_type="casdoor_membership_reconciled",
                    actor_user_id=None,
                    subject_user_id=user.id,
                    subject_ref=user.username,
                    detail={
                        "organization": organization[:160],
                        "business_role": business_role,
                        "status": desired_status,
                        "group_count": len(groups),
                    },
                )
                changed_count += 1
        db.commit()
        return CasdoorMembershipSyncResult("synced", "casdoor_users_reconciled", len(remote_by_name), changed_count)

    @staticmethod
    def _access_token(
        client: httpx.Client,
        endpoint: str,
        client_id: str,
        client_secret: str,
    ) -> str:
        token_response = client.post(
            f"{endpoint}/api/login/oauth/access_token",
            json={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        payload = token_response.json()
        access_token = str(payload.get("access_token") or "") if isinstance(payload, dict) else ""
        if not access_token:
            raise CasdoorManagementError("casdoor_token_missing")
        return access_token


class CasdoorPlatformClient:
    """Global Casdoor adapter used only by the isolated platform control plane."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.transport = transport

    def provision_organization(self, *, name: str, display_name: str) -> CasdoorSyncResult:
        endpoint = self.settings.casdoor_platform_endpoint.rstrip("/")
        client_id = self.settings.casdoor_platform_client_id.strip()
        client_secret = self.settings.casdoor_platform_client_secret
        if not endpoint or not client_id or not client_secret:
            return CasdoorSyncResult("failed", "casdoor_platform_credentials_incomplete")
        try:
            with httpx.Client(
                timeout=self.settings.casdoor_management_timeout_seconds,
                transport=self.transport,
            ) as client:
                token_response = client.post(
                    f"{endpoint}/api/login/oauth/access_token",
                    json={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                    headers={"Accept": "application/json"},
                )
                token_response.raise_for_status()
                token_payload = token_response.json()
                access_token = (
                    str(token_payload.get("access_token") or "")
                    if isinstance(token_payload, dict)
                    else ""
                )
                if not access_token:
                    raise CasdoorManagementError("casdoor_token_missing")
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "Accept-Language": "en",
                }
                existing_response = client.get(
                    f"{endpoint}/api/get-organization",
                    params={"id": name},
                    headers=headers,
                )
                existing_response.raise_for_status()
                existing_payload = existing_response.json()
                if (
                    isinstance(existing_payload, dict)
                    and existing_payload.get("status") == "ok"
                    and existing_payload.get("data")
                ):
                    return CasdoorSyncResult("exists", "casdoor_organization_exists")
                add_response = client.post(
                    f"{endpoint}/api/add-organization",
                    json={"name": name, "displayName": display_name},
                    headers=headers,
                )
                add_response.raise_for_status()
                payload = add_response.json()
                if not isinstance(payload, dict) or payload.get("status") != "ok":
                    raise CasdoorManagementError("casdoor_organization_rejected")
        except (httpx.HTTPError, ValueError, CasdoorManagementError) as exc:
            logger.warning("Casdoor organization provisioning failed: %s", type(exc).__name__)
            return CasdoorSyncResult("failed", str(exc)[:200])
        return CasdoorSyncResult("synced", "casdoor_organization_created")
