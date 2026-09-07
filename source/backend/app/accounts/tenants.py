from __future__ import annotations

from typing import Protocol

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.accounts.casdoor import CasdoorPlatformClient, CasdoorSyncResult
from app.db.models import Tenant, TenantLifecycleEvent, utc_now


class OrganizationProvisioner(Protocol):
    def provision_organization(self, *, name: str, display_name: str) -> CasdoorSyncResult: ...


def provision_tenant(
    db: Session,
    *,
    tenant_id: str,
    name: str,
    casdoor_organization: str,
    default_locale: str,
    default_timezone: str,
    default_currency: str,
    actor_ref: str,
    provisioner: OrganizationProvisioner | None = None,
) -> Tenant:
    normalized_id = tenant_id.strip()[:120]
    normalized_name = name.strip()[:200]
    organization = casdoor_organization.strip()[:120]
    if not normalized_id or not normalized_name or not organization:
        raise HTTPException(status_code=400, detail="Tenant id, name and organization are required")
    existing = db.get(Tenant, normalized_id)
    if existing:
        if existing.casdoor_organization == organization:
            return existing
        raise HTTPException(status_code=409, detail="Tenant id already exists")
    organization_owner = db.exec(
        select(Tenant).where(Tenant.casdoor_organization == organization)
    ).first()
    if organization_owner:
        raise HTTPException(status_code=409, detail="Casdoor organization is already mapped")

    provisioner = provisioner or CasdoorPlatformClient()
    remote = provisioner.provision_organization(name=organization, display_name=normalized_name)
    if remote.status not in {"synced", "exists"}:
        _record_tenant_event(
            db,
            tenant_id=normalized_id,
            event_type="tenant_provisioning_failed",
            actor_ref=actor_ref,
            outcome="denied",
            reason=remote.reason,
            detail={"casdoor_organization": organization},
        )
        db.commit()
        raise HTTPException(status_code=502, detail="Casdoor organization provisioning failed")

    tenant = Tenant(
        id=normalized_id,
        name=normalized_name,
        status="active",
        casdoor_organization=organization,
        identity_sync_status="synced",
        default_locale=default_locale,
        default_timezone=default_timezone,
        default_currency=default_currency.upper(),
    )
    db.add(tenant)
    _record_tenant_event(
        db,
        tenant_id=normalized_id,
        event_type="tenant_provisioned",
        actor_ref=actor_ref,
        reason=remote.reason,
        detail={
            "casdoor_organization": organization,
            "default_locale": default_locale,
            "default_timezone": default_timezone,
            "default_currency": default_currency.upper(),
        },
    )
    try:
        db.commit()
        db.refresh(tenant)
    except IntegrityError as exc:
        db.rollback()
        _record_tenant_event(
            db,
            tenant_id=normalized_id,
            event_type="tenant_provisioning_failed",
            actor_ref=actor_ref,
            outcome="degraded",
            reason="database_create_failed_remote_org_may_exist",
            detail={"casdoor_organization": organization},
        )
        db.commit()
        raise HTTPException(status_code=409, detail="Tenant could not be created") from exc
    return tenant


def set_tenant_status(
    db: Session,
    *,
    tenant_id: str,
    status: str,
    reason: str,
    actor_ref: str,
) -> Tenant:
    if status not in {"active", "suspended"}:
        raise HTTPException(status_code=400, detail="Tenant status is invalid")
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    previous = tenant.status
    if previous == status:
        return tenant
    tenant.status = status
    tenant.identity_sync_status = "manual_required"
    tenant.updated_at = utc_now()
    db.add(tenant)
    _record_tenant_event(
        db,
        tenant_id=tenant.id,
        event_type="tenant_status_changed",
        actor_ref=actor_ref,
        reason=reason,
        detail={"from": previous, "to": status, "casdoor_sync": "manual_required"},
    )
    db.commit()
    db.refresh(tenant)
    return tenant


def _record_tenant_event(
    db: Session,
    *,
    tenant_id: str,
    event_type: str,
    actor_ref: str,
    outcome: str = "allowed",
    reason: str = "",
    detail: dict[str, object] | None = None,
) -> None:
    db.add(
        TenantLifecycleEvent(
            tenant_id=tenant_id,
            event_type=event_type,
            actor_ref=actor_ref[:200],
            outcome=outcome,
            reason=reason[:500],
            detail_json=detail or {},
        )
    )
