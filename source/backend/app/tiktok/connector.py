from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db.models import (
    BusinessResource,
    BusinessResourceScope,
    ConnectorSyncState,
    ExternalAuthorization,
    User,
    utc_now,
)
from app.security.permissions import is_admin_user
from app.tiktok.official import TikTokOfficialClient, TikTokOfficialError

REQUIRED_SCOPE_BY_AUTHORIZATION = {
    "seller": "shop.read",
    "creator": "creator.read",
    "partner": "partner.read",
    "ads": "ads.read",
    "social": "social.read",
}
TIKTOK_RESOURCE_TYPES = {
    "store",
    "ad_account",
    "creator_account",
    "partner_account",
    "social_account",
    "live_room",
}
RESOURCE_TYPES_BY_AUTHORIZATION = {
    "seller": frozenset({"store"}),
    "creator": frozenset({"creator_account"}),
    "partner": frozenset({"partner_account"}),
    "ads": frozenset({"ad_account"}),
    "social": frozenset({"social_account", "live_room"}),
}
OFFICIAL_READ_AUTHORIZATION_TYPES = frozenset({"seller"})


class TikTokConnectorRead(BaseModel):
    source: str = "mock"
    authorization_id: str
    resource_id: str
    fetched_at: datetime
    stale: bool = False
    data: dict[str, str | int | bool | None] = Field(default_factory=dict)


def _ensure_resource_scope(db: Session, user: User, resource: BusinessResource) -> str:
    if resource.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="TikTok resource not found")
    if is_admin_user(user) or user.business_role == "operations_supervisor":
        return "operator"
    access = db.exec(
        select(BusinessResourceScope.access_level).where(
            BusinessResourceScope.tenant_id == user.tenant_id,
            BusinessResourceScope.resource_id == resource.id,
            BusinessResourceScope.business_role == user.business_role,
        )
    ).first()
    if not access:
        raise HTTPException(status_code=403, detail="TikTok resource scope denied")
    return str(access)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _ensure_authorization_asset_type(
    authorization_type: str,
    resource: BusinessResource,
) -> None:
    allowed_resource_types = RESOURCE_TYPES_BY_AUTHORIZATION[authorization_type]
    if resource.resource_type not in allowed_resource_types:
        raise HTTPException(status_code=403, detail="tiktok_authorization_type_mismatch")


def read_tiktok_resource(
    db: Session,
    *,
    user: User,
    authorization_type: str,
    resource_id: str,
    required_scope: str | None = None,
) -> TikTokConnectorRead:
    expected_scope = REQUIRED_SCOPE_BY_AUTHORIZATION.get(authorization_type)
    if not expected_scope:
        raise HTTPException(status_code=422, detail="Unsupported TikTok authorization type")
    resource = db.get(BusinessResource, resource_id)
    resource_metadata = resource.metadata_json if resource else {}
    is_tiktok_asset = (
        resource
        and resource.resource_type in TIKTOK_RESOURCE_TYPES
        and resource_metadata.get("platform") == "tiktok"
    )
    if not resource or resource.status != "active" or not is_tiktok_asset:
        raise HTTPException(status_code=404, detail="TikTok resource not found")
    _ensure_resource_scope(db, user, resource)
    _ensure_authorization_asset_type(authorization_type, resource)
    requested_scope = (required_scope or expected_scope).strip()
    if requested_scope != expected_scope:
        raise HTTPException(status_code=403, detail="TikTok connector scope is not approved")
    authorization = db.exec(
        select(ExternalAuthorization).where(
            ExternalAuthorization.tenant_id == user.tenant_id,
            ExternalAuthorization.provider == "tiktok",
            ExternalAuthorization.authorization_type == authorization_type,
            ExternalAuthorization.resource_id == resource_id,
            ExternalAuthorization.status == "active",
        )
    ).first()
    if not authorization:
        raise HTTPException(status_code=409, detail="TikTok authorization is not active")
    now = utc_now()
    if authorization.expires_at is not None and _utc_naive(authorization.expires_at) <= now:
        raise HTTPException(status_code=409, detail="tiktok_authorization_expired")
    if requested_scope not in set(authorization.scopes_json or []):
        official_scopes = set(authorization.metadata_json.get("official_scopes", []))
        if not (
            authorization.metadata_json.get("authorization_flow") == "official"
            and {"seller.shop.info", "shop.read"}.intersection(official_scopes or set(authorization.scopes_json or []))
        ):
            raise HTTPException(status_code=403, detail="TikTok authorization scope is insufficient")

    if authorization.metadata_json.get("authorization_flow") == "official":
        if authorization_type not in OFFICIAL_READ_AUTHORIZATION_TYPES:
            raise HTTPException(status_code=503, detail="tiktok_connector_unavailable")
        try:
            permissions = TikTokOfficialClient().get_seller_permissions(
                str(authorization.credential_ref or "")
            )
        except TikTokOfficialError as exc:
            raise HTTPException(status_code=502, detail=exc.code) from exc
        connector_type = "tiktok.official.seller"
        data = {
            "resource_code": resource.code,
            "resource_name": resource.name,
            "resource_type": resource.resource_type,
            "market": str((resource.metadata_json or {}).get("market") or ""),
            "status": resource.status,
            "read_only": True,
            "official_api": "seller/202309/permissions",
            "permission_count": len(permissions.get("permissions", []))
            if isinstance(permissions.get("permissions"), list)
            else 0,
        }
    else:
        connector_type = f"tiktok.mock.{authorization_type}"
        data = {
            "resource_code": resource.code,
            "resource_name": resource.name,
            "resource_type": resource.resource_type,
            "market": str((resource.metadata_json or {}).get("market") or ""),
            "status": resource.status,
            "read_only": True,
        }
    sync = db.exec(
        select(ConnectorSyncState).where(
            ConnectorSyncState.tenant_id == user.tenant_id,
            ConnectorSyncState.connector_type == connector_type,
            ConnectorSyncState.resource_id == resource_id,
        )
    ).first()
    if sync is None:
        sync = ConnectorSyncState(
            tenant_id=user.tenant_id,
            connector_type=connector_type,
            resource_id=resource_id,
        )
    sync.status = "succeeded"
    sync.watermark_at = now
    sync.revision += 1
    sync.updated_at = now
    db.add(sync)
    db.commit()
    return TikTokConnectorRead(
        authorization_id=authorization.id,
        resource_id=resource.id,
        fetched_at=now,
        source="official" if authorization.metadata_json.get("authorization_flow") == "official" else "mock",
        data=data,
    )
