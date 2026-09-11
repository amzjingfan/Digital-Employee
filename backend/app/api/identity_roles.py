from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.accounts.casdoor_sync import mapped_organizations, reconcile_once
from app.config import get_settings
from app.db import get_session
from app.db.models import User
from app.security.auth import get_current_user
from app.security.business_roles import (
    BUSINESS_ROLES,
    GroupRoleMappingError,
    business_role_label,
    parse_group_role_mapping,
)
from app.security.permissions import is_admin_user

router = APIRouter(
    prefix="/api/enterprise/identity-role-mappings",
    tags=["enterprise:identity-roles"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
def get_identity_role_mappings(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    if not is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Only administrators can view identity roles")
    settings = get_settings()
    try:
        configured_mapping = parse_group_role_mapping(settings.oidc_group_role_mapping_json)
    except GroupRoleMappingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    users = db.exec(
        select(User)
        .where(User.tenant_id == current_user.tenant_id, User.source.in_(["web", "oidc"]))
        .order_by(User.username)
    ).all()
    return {
        "group_claim": settings.oidc_group_claim,
        "require_mapped_group": settings.oidc_require_mapped_group,
        "casdoor_management": {
            "enabled": settings.casdoor_management_enabled,
            "configured": bool(
                settings.casdoor_management_endpoint.strip()
                and settings.casdoor_management_client_id.strip()
                and settings.casdoor_management_client_secret
            ),
            "sync_interval_seconds": settings.casdoor_management_sync_interval_seconds,
        },
        "roles": [
            {
                "key": definition.key,
                "label": definition.label,
                "casdoor_groups": sorted(
                    group for group, role in configured_mapping.items() if role == definition.key
                ),
                "description": definition.description,
            }
            for definition in BUSINESS_ROLES
        ],
        "accounts": [
            {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "account_role": user.role,
                "business_role": user.business_role,
                "business_role_label": business_role_label(user.business_role),
                "authorization_source": user.authorization_source,
                "identity_groups": list(user.identity_groups_json or []),
                "role_synced_at": user.role_synced_at.isoformat() if user.role_synced_at else None,
            }
            for user in users
        ],
    }


@router.post("/reconcile-management")
def reconcile_management_memberships(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    """Run a tenant-scoped, read-from-Casdoor membership reconciliation."""

    if not is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Only administrators can reconcile identity roles")
    settings = get_settings()
    if not settings.casdoor_management_enabled:
        raise HTTPException(status_code=503, detail="Casdoor Management Client is disabled")
    if current_user.tenant_id not in mapped_organizations(settings).values():
        raise HTTPException(status_code=409, detail="Current tenant has no Casdoor organization mapping")

    result = reconcile_once(settings=settings, tenant_ids={current_user.tenant_id})
    if not result:
        raise HTTPException(status_code=503, detail="Casdoor membership reconciliation returned no result")
    latest = result[0]
    return {
        "status": latest.status,
        "reason": latest.reason,
        "scanned_count": latest.scanned_count,
        "changed_count": latest.changed_count,
        "sync_interval_seconds": settings.casdoor_management_sync_interval_seconds,
    }
