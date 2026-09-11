from __future__ import annotations

import hmac
from functools import lru_cache
from typing import Annotated, Generator, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, create_engine, select

from app.accounts.tenants import provision_tenant, set_tenant_status
from app.config import get_settings
from app.db.database_path import normalize_database_url
from app.db.models import Tenant, TenantLifecycleEvent

router = APIRouter(
    prefix="/api/platform/tenants",
    tags=["platform:tenants"],
)


class TenantProvisionRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    casdoor_organization: str = Field(min_length=1, max_length=120)
    default_locale: Literal["zh-CN", "en"] = "en"
    default_timezone: str = Field(default="UTC", min_length=1, max_length=80)
    default_currency: str = Field(default="USD", min_length=3, max_length=3)


class TenantStatusRequest(BaseModel):
    status: Literal["active", "suspended"]
    reason: str = Field(min_length=1, max_length=500)


class TenantRead(BaseModel):
    id: str
    name: str
    status: str
    casdoor_organization: str | None
    identity_sync_status: str
    default_locale: str
    default_timezone: str
    default_currency: str
    created_at: str
    updated_at: str


class TenantLifecycleEventRead(BaseModel):
    id: str
    tenant_id: str
    event_type: str
    actor_ref: str
    outcome: str
    reason: str
    detail: dict[str, object]
    occurred_at: str


def require_platform_key(
    x_staffdeck_platform_key: Annotated[str | None, Header()] = None,
) -> str:
    settings = get_settings()
    if not settings.platform_admin_api_enabled:
        raise HTTPException(status_code=404, detail="Platform control plane is disabled")
    expected = settings.platform_admin_api_key
    supplied = x_staffdeck_platform_key or ""
    if len(expected) < 32 or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid platform credential")
    return "platform_api"


def get_platform_session() -> Generator[Session, None, None]:
    settings = get_settings()
    if not settings.platform_database_url:
        raise HTTPException(status_code=503, detail="Platform database is not configured")
    engine = _platform_engine(settings.platform_database_url)
    with Session(engine) as session:
        yield session


@router.post("", response_model=TenantRead)
def create_platform_tenant(
    request: TenantProvisionRequest,
    actor_ref: Annotated[str, Depends(require_platform_key)],
    db: Annotated[Session, Depends(get_platform_session)],
) -> TenantRead:
    tenant = provision_tenant(
        db,
        tenant_id=request.tenant_id,
        name=request.name,
        casdoor_organization=request.casdoor_organization,
        default_locale=request.default_locale,
        default_timezone=request.default_timezone,
        default_currency=request.default_currency,
        actor_ref=actor_ref,
    )
    return _tenant_read(tenant)


@router.get("", response_model=list[TenantRead])
def list_platform_tenants(
    _actor_ref: Annotated[str, Depends(require_platform_key)],
    db: Annotated[Session, Depends(get_platform_session)],
) -> list[TenantRead]:
    return [_tenant_read(row) for row in db.exec(select(Tenant).order_by(Tenant.created_at)).all()]


@router.post("/{tenant_id}/status", response_model=TenantRead)
def update_platform_tenant_status(
    tenant_id: str,
    request: TenantStatusRequest,
    actor_ref: Annotated[str, Depends(require_platform_key)],
    db: Annotated[Session, Depends(get_platform_session)],
) -> TenantRead:
    return _tenant_read(
        set_tenant_status(
            db,
            tenant_id=tenant_id,
            status=request.status,
            reason=request.reason,
            actor_ref=actor_ref,
        )
    )


@router.get("/lifecycle-events", response_model=list[TenantLifecycleEventRead])
def list_tenant_lifecycle_events(
    _actor_ref: Annotated[str, Depends(require_platform_key)],
    db: Annotated[Session, Depends(get_platform_session)],
) -> list[TenantLifecycleEventRead]:
    rows = db.exec(
        select(TenantLifecycleEvent).order_by(TenantLifecycleEvent.occurred_at.desc()).limit(500)
    ).all()
    return [
        TenantLifecycleEventRead(
            id=row.id,
            tenant_id=row.tenant_id,
            event_type=row.event_type,
            actor_ref=row.actor_ref,
            outcome=row.outcome,
            reason=row.reason,
            detail=dict(row.detail_json or {}),
            occurred_at=row.occurred_at.isoformat(),
        )
        for row in rows
    ]


@lru_cache(maxsize=2)
def _platform_engine(database_url: str):
    return create_engine(normalize_database_url(database_url), pool_pre_ping=True)


def _tenant_read(row: Tenant) -> TenantRead:
    return TenantRead(
        id=row.id,
        name=row.name,
        status=row.status,
        casdoor_organization=row.casdoor_organization,
        identity_sync_status=row.identity_sync_status,
        default_locale=row.default_locale,
        default_timezone=row.default_timezone,
        default_currency=row.default_currency,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )
