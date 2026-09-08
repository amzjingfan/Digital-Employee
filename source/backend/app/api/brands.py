from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.brands.schema import (
    BrandAccessEventRead,
    BrandCreate,
    BrandMembershipPut,
    BrandMembershipRead,
    BrandRead,
    BrandStoreRead,
    StoreAccessPut,
)
from app.brands.service import (
    create_brand,
    list_brand_access_events,
    list_brand_memberships,
    list_brand_stores,
    list_brands,
    put_brand_membership,
    put_store_access,
)
from app.db import get_session
from app.db.models import User
from app.security.auth import get_current_user

router = APIRouter(prefix="/api/enterprise/brands", tags=["enterprise:brands"])


@router.get("", response_model=list[BrandRead])
def get_brands(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> list[BrandRead]:
    return list_brands(db, tenant_id=tenant_id, user=current_user)


@router.post("", response_model=BrandRead)
def post_brand(
    request: BrandCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> BrandRead:
    return create_brand(db, request=request, user=current_user)


@router.get("/{brand_id}/members", response_model=list[BrandMembershipRead])
def get_brand_memberships(
    brand_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> list[BrandMembershipRead]:
    return list_brand_memberships(
        db,
        tenant_id=tenant_id,
        brand_id=brand_id,
        user=current_user,
    )


@router.put("/{brand_id}/members/{subject_user_id}", response_model=BrandMembershipRead)
def put_brand_member(
    brand_id: str,
    subject_user_id: str,
    request: BrandMembershipPut,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> BrandMembershipRead:
    return put_brand_membership(
        db,
        brand_id=brand_id,
        subject_user_id=subject_user_id,
        request=request,
        user=current_user,
    )


@router.get("/{brand_id}/stores", response_model=list[BrandStoreRead])
def get_brand_stores(
    brand_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> list[BrandStoreRead]:
    return list_brand_stores(
        db,
        tenant_id=tenant_id,
        brand_id=brand_id,
        user=current_user,
    )


@router.put("/{brand_id}/stores/{resource_id}", response_model=BrandStoreRead)
def put_brand_store(
    brand_id: str,
    resource_id: str,
    request: StoreAccessPut,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> BrandStoreRead:
    return put_store_access(
        db,
        brand_id=brand_id,
        resource_id=resource_id,
        request=request,
        user=current_user,
    )


@router.get("/{brand_id}/access-events", response_model=list[BrandAccessEventRead])
def get_brand_access_events(
    brand_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> list[BrandAccessEventRead]:
    return list_brand_access_events(
        db,
        tenant_id=tenant_id,
        brand_id=brand_id,
        user=current_user,
    )
