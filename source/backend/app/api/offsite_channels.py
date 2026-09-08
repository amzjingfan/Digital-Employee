from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlmodel import Session

from app.db import get_session
from app.db.models import User
from app.offsite.schema import (
    OffsiteChannelAssetCreate,
    OffsiteChannelAssetRead,
    OffsiteChannelEvidenceCreate,
    OffsiteChannelReview,
)
from app.offsite.service import (
    add_channel_evidence,
    create_channel_asset,
    get_channel_asset,
    list_channel_assets,
    review_channel_asset,
)
from app.security.auth import get_current_user

router = APIRouter(prefix="/api/v1/offsite", tags=["enterprise:offsite-channels"])


@router.get("/channels", response_model=list[OffsiteChannelAssetRead])
def get_channels(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
    brand_key: Annotated[str | None, Query()] = None,
    asset_type: Annotated[str | None, Query()] = None,
    lifecycle_status: Annotated[str | None, Query()] = None,
) -> list[OffsiteChannelAssetRead]:
    return list_channel_assets(
        db,
        tenant_id=tenant_id,
        user=current_user,
        brand_key=brand_key,
        asset_type=asset_type,
        lifecycle_status=lifecycle_status,
    )


@router.post("/channels", response_model=OffsiteChannelAssetRead)
def post_channel(
    request: OffsiteChannelAssetCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> OffsiteChannelAssetRead:
    return create_channel_asset(
        db,
        request=request,
        idempotency_key=idempotency_key,
        user=current_user,
    )


@router.get("/channels/{asset_id}", response_model=OffsiteChannelAssetRead)
def get_channel(
    asset_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> OffsiteChannelAssetRead:
    return get_channel_asset(db, tenant_id=tenant_id, asset_id=asset_id, user=current_user)


@router.post("/channels/{asset_id}/evidence", response_model=OffsiteChannelAssetRead)
def post_channel_evidence(
    asset_id: str,
    request: OffsiteChannelEvidenceCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> OffsiteChannelAssetRead:
    return add_channel_evidence(
        db,
        asset_id=asset_id,
        request=request,
        idempotency_key=idempotency_key,
        user=current_user,
    )


@router.post("/channels/{asset_id}/review", response_model=OffsiteChannelAssetRead)
def post_channel_review(
    asset_id: str,
    request: OffsiteChannelReview,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> OffsiteChannelAssetRead:
    return review_channel_asset(db, asset_id=asset_id, request=request, user=current_user)
