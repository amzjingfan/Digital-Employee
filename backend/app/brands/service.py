from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.brands.schema import (
    BrandAccessEventRead,
    BrandCreate,
    BrandMembershipPut,
    BrandMembershipRead,
    BrandRead,
    BrandStoreRead,
    StoreAccessPut,
)
from app.db.models import (
    Brand,
    BrandAccessEvent,
    BrandMembership,
    BusinessResource,
    StoreAccess,
    User,
    utc_now_aware,
)
from app.security.auth import ensure_current_user_tenant
from app.security.permissions import is_admin_user

_ACCESS_RANK = {"viewer": 1, "operator": 2}


def create_brand(db: Session, *, request: BrandCreate, user: User) -> BrandRead:
    _require_tenant_admin(request.tenant_id, user)
    code = request.code.strip()
    name = request.name.strip()
    timezone = _validated_timezone(request.timezone)
    existing = db.exec(
        select(Brand).where(
            Brand.tenant_id == request.tenant_id,
            Brand.code == code,
        )
    ).first()
    if existing:
        if existing.name == name and existing.timezone == timezone:
            return _brand_read(existing, access_level="operator")
        raise HTTPException(status_code=409, detail="Brand code already exists")
    row = Brand(
        tenant_id=request.tenant_id,
        code=code,
        name=name,
        timezone=timezone,
        created_by_user_id=user.id,
    )
    db.add(row)
    try:
        db.flush()
        _record_event(
            db,
            brand=row,
            event_type="brand_created",
            actor=user,
            detail={"code": code, "timezone": timezone},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Brand code already exists") from exc
    db.refresh(row)
    return _brand_read(row, access_level="operator")


def list_brands(db: Session, *, tenant_id: str, user: User) -> list[BrandRead]:
    _ensure_tenant(tenant_id, user)
    if is_admin_user(user):
        rows = db.exec(
            select(Brand).where(Brand.tenant_id == tenant_id).order_by(Brand.name, Brand.id)
        ).all()
        return [_brand_read(row, access_level="operator") for row in rows]

    rows = db.exec(
        select(Brand, BrandMembership)
        .join(
            BrandMembership,
            (BrandMembership.tenant_id == Brand.tenant_id) & (BrandMembership.brand_id == Brand.id),
        )
        .where(
            Brand.tenant_id == tenant_id,
            Brand.status == "active",
            BrandMembership.tenant_id == tenant_id,
            BrandMembership.user_id == user.id,
            BrandMembership.status == "active",
        )
        .order_by(Brand.name, Brand.id)
    ).all()
    return [_brand_read(brand, access_level=membership.access_level) for brand, membership in rows]


def put_brand_membership(
    db: Session,
    *,
    brand_id: str,
    subject_user_id: str,
    request: BrandMembershipPut,
    user: User,
) -> BrandMembershipRead:
    _require_tenant_admin(request.tenant_id, user)
    brand = _brand(db, tenant_id=request.tenant_id, brand_id=brand_id)
    subject = db.exec(
        select(User).where(
            User.tenant_id == request.tenant_id,
            User.id == subject_user_id,
        )
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="User not found")
    if request.status == "active" and subject.status != "active":
        raise HTTPException(status_code=409, detail="Inactive user cannot receive brand access")

    row = db.exec(
        select(BrandMembership).where(
            BrandMembership.tenant_id == request.tenant_id,
            BrandMembership.brand_id == brand.id,
            BrandMembership.user_id == subject.id,
        )
    ).first()
    previous = None
    if row:
        previous = {"access_level": row.access_level, "status": row.status}
        if row.access_level == request.access_level and row.status == request.status:
            return _membership_read(row)
        row.access_level = request.access_level
        row.status = request.status
        row.updated_at = utc_now_aware()
    else:
        row = BrandMembership(
            tenant_id=request.tenant_id,
            brand_id=brand.id,
            user_id=subject.id,
            access_level=request.access_level,
            status=request.status,
            created_by_user_id=user.id,
        )
    db.add(row)
    _record_event(
        db,
        brand=brand,
        event_type="membership_changed",
        actor=user,
        subject_user_id=subject.id,
        detail={
            "previous": previous,
            "access_level": request.access_level,
            "status": request.status,
        },
    )
    _commit_assignment(db, conflict_detail="Brand membership already exists")
    db.refresh(row)
    return _membership_read(row)


def list_brand_memberships(
    db: Session,
    *,
    tenant_id: str,
    brand_id: str,
    user: User,
) -> list[BrandMembershipRead]:
    _require_tenant_admin(tenant_id, user)
    _brand(db, tenant_id=tenant_id, brand_id=brand_id)
    rows = db.exec(
        select(BrandMembership)
        .where(
            BrandMembership.tenant_id == tenant_id,
            BrandMembership.brand_id == brand_id,
        )
        .order_by(BrandMembership.user_id)
    ).all()
    return [_membership_read(row) for row in rows]


def put_store_access(
    db: Session,
    *,
    brand_id: str,
    resource_id: str,
    request: StoreAccessPut,
    user: User,
) -> BrandStoreRead:
    _require_tenant_admin(request.tenant_id, user)
    brand = _brand(db, tenant_id=request.tenant_id, brand_id=brand_id)
    resource = db.exec(
        select(BusinessResource).where(
            BusinessResource.tenant_id == request.tenant_id,
            BusinessResource.id == resource_id,
        )
    ).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Business resource not found")
    if resource.resource_type != "store":
        raise HTTPException(
            status_code=400, detail="Only store resources can be assigned to a brand"
        )
    if request.status == "active" and resource.status != "active":
        raise HTTPException(status_code=409, detail="Inactive store cannot receive brand access")

    row = db.exec(
        select(StoreAccess).where(
            StoreAccess.tenant_id == request.tenant_id,
            StoreAccess.resource_id == resource.id,
        )
    ).first()
    previous = None
    if row:
        if row.brand_id != brand.id:
            raise HTTPException(
                status_code=409, detail="Store is already assigned to another brand"
            )
        previous = {"status": row.status}
        if row.status == request.status:
            return _store_read(row, resource)
        row.status = request.status
        row.updated_at = utc_now_aware()
    else:
        row = StoreAccess(
            tenant_id=request.tenant_id,
            brand_id=brand.id,
            resource_id=resource.id,
            status=request.status,
            created_by_user_id=user.id,
        )
    db.add(row)
    _record_event(
        db,
        brand=brand,
        event_type="store_access_changed",
        actor=user,
        resource_id=resource.id,
        detail={"previous": previous, "status": request.status},
    )
    _commit_assignment(db, conflict_detail="Store access already exists")
    db.refresh(row)
    return _store_read(row, resource)


def list_brand_stores(
    db: Session,
    *,
    tenant_id: str,
    brand_id: str,
    user: User,
) -> list[BrandStoreRead]:
    require_brand_access(
        db,
        tenant_id=tenant_id,
        brand_id=brand_id,
        user=user,
        required_access="viewer",
    )
    rows = db.exec(
        select(StoreAccess, BusinessResource)
        .join(
            BusinessResource,
            (BusinessResource.tenant_id == StoreAccess.tenant_id)
            & (BusinessResource.id == StoreAccess.resource_id),
        )
        .where(
            StoreAccess.tenant_id == tenant_id,
            StoreAccess.brand_id == brand_id,
            StoreAccess.status == "active",
            BusinessResource.resource_type == "store",
            BusinessResource.status == "active",
        )
        .order_by(BusinessResource.name, BusinessResource.id)
    ).all()
    return [_store_read(access, resource) for access, resource in rows]


def require_brand_store_access(
    db: Session,
    *,
    tenant_id: str,
    brand_id: str,
    resource_id: str,
    user: User,
    required_access: str = "viewer",
) -> BusinessResource:
    require_brand_access(
        db,
        tenant_id=tenant_id,
        brand_id=brand_id,
        user=user,
        required_access=required_access,
    )
    resource = db.exec(
        select(BusinessResource)
        .join(
            StoreAccess,
            (StoreAccess.tenant_id == BusinessResource.tenant_id)
            & (StoreAccess.resource_id == BusinessResource.id),
        )
        .where(
            BusinessResource.tenant_id == tenant_id,
            BusinessResource.id == resource_id,
            BusinessResource.resource_type == "store",
            BusinessResource.status == "active",
            StoreAccess.tenant_id == tenant_id,
            StoreAccess.brand_id == brand_id,
            StoreAccess.status == "active",
        )
    ).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Store not found in brand scope")
    return resource


def require_brand_access(
    db: Session,
    *,
    tenant_id: str,
    brand_id: str,
    user: User,
    required_access: str = "viewer",
) -> Brand:
    _ensure_tenant(tenant_id, user)
    if required_access not in _ACCESS_RANK:
        raise ValueError("required_access must be viewer or operator")
    brand = _brand(db, tenant_id=tenant_id, brand_id=brand_id)
    if brand.status != "active":
        raise HTTPException(status_code=403, detail="Brand is not active")
    if is_admin_user(user):
        return brand
    membership = db.exec(
        select(BrandMembership).where(
            BrandMembership.tenant_id == tenant_id,
            BrandMembership.brand_id == brand_id,
            BrandMembership.user_id == user.id,
            BrandMembership.status == "active",
        )
    ).first()
    if not membership or _ACCESS_RANK[membership.access_level] < _ACCESS_RANK[required_access]:
        raise HTTPException(status_code=403, detail="Brand access denied")
    return brand


def list_brand_access_events(
    db: Session,
    *,
    tenant_id: str,
    brand_id: str,
    user: User,
) -> list[BrandAccessEventRead]:
    _require_tenant_admin(tenant_id, user)
    _brand(db, tenant_id=tenant_id, brand_id=brand_id)
    rows = db.exec(
        select(BrandAccessEvent)
        .where(
            BrandAccessEvent.tenant_id == tenant_id,
            BrandAccessEvent.brand_id == brand_id,
        )
        .order_by(BrandAccessEvent.occurred_at, BrandAccessEvent.id)
    ).all()
    return [_event_read(row) for row in rows]


def _brand(db: Session, *, tenant_id: str, brand_id: str) -> Brand:
    row = db.exec(select(Brand).where(Brand.tenant_id == tenant_id, Brand.id == brand_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Brand not found")
    return row


def _ensure_tenant(tenant_id: str, user: User) -> None:
    ensure_current_user_tenant(tenant_id, user)


def _require_tenant_admin(tenant_id: str, user: User) -> None:
    _ensure_tenant(tenant_id, user)
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Only administrator can manage brand access")


def _validated_timezone(value: str) -> str:
    normalized = value.strip()
    try:
        ZoneInfo(normalized)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Unknown brand timezone") from exc
    return normalized


def _record_event(
    db: Session,
    *,
    brand: Brand,
    event_type: str,
    actor: User,
    subject_user_id: str | None = None,
    resource_id: str | None = None,
    detail: dict[str, object] | None = None,
) -> None:
    db.add(
        BrandAccessEvent(
            tenant_id=brand.tenant_id,
            brand_id=brand.id,
            event_type=event_type,
            actor_user_id=actor.id,
            subject_user_id=subject_user_id,
            resource_id=resource_id,
            detail_json=detail or {},
        )
    )


def _commit_assignment(db: Session, *, conflict_detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=conflict_detail) from exc


def _brand_read(row: Brand, *, access_level: str) -> BrandRead:
    return BrandRead(
        id=row.id,
        tenant_id=row.tenant_id,
        code=row.code,
        name=row.name,
        timezone=row.timezone,
        status=row.status,
        revision=row.revision,
        access_level=access_level,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _membership_read(row: BrandMembership) -> BrandMembershipRead:
    return BrandMembershipRead(
        id=row.id,
        tenant_id=row.tenant_id,
        brand_id=row.brand_id,
        user_id=row.user_id,
        access_level=row.access_level,
        status=row.status,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _store_read(row: StoreAccess, resource: BusinessResource) -> BrandStoreRead:
    return BrandStoreRead(
        access_id=row.id,
        tenant_id=row.tenant_id,
        brand_id=row.brand_id,
        resource_id=row.resource_id,
        code=resource.code,
        name=resource.name,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _event_read(row: BrandAccessEvent) -> BrandAccessEventRead:
    return BrandAccessEventRead(
        id=row.id,
        tenant_id=row.tenant_id,
        brand_id=row.brand_id,
        event_type=row.event_type,
        actor_user_id=row.actor_user_id,
        subject_user_id=row.subject_user_id,
        resource_id=row.resource_id,
        detail=dict(row.detail_json or {}),
        occurred_at=row.occurred_at,
    )
