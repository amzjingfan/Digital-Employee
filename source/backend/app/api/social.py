from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlmodel import Session

from app.db import get_session
from app.db.models import User
from app.security.auth import get_current_user
from app.social.schema import (
    SocialAudienceCreate,
    SocialAudienceFilters,
    SocialAudienceRead,
    SocialCreatorCreate,
    SocialCreatorEvidenceInput,
    SocialCreatorEvidenceRead,
    SocialCreatorRead,
    SocialPlatform,
)
from app.social.service import (
    add_creator_evidence,
    create_creator,
    freeze_audience,
    get_audience,
    list_creators,
)

router = APIRouter(prefix="/api/v1/social", tags=["social"])
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=160)]


@router.post("/creators", response_model=SocialCreatorRead, status_code=status.HTTP_201_CREATED)
def post_creator(
    payload: SocialCreatorCreate,
    http_request: Request,
    idempotency_key: IdempotencyHeader,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> SocialCreatorRead:
    return create_creator(
        db,
        user=current_user,
        request=payload,
        idempotency_key=idempotency_key,
        request_id=_request_id(http_request),
    )


@router.post(
    "/creators/{creator_id}/identities/{identity_id}/evidence",
    response_model=SocialCreatorEvidenceRead,
    status_code=status.HTTP_201_CREATED,
)
def post_creator_evidence(
    creator_id: str,
    identity_id: str,
    payload: SocialCreatorEvidenceInput,
    http_request: Request,
    idempotency_key: IdempotencyHeader,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> SocialCreatorEvidenceRead:
    return add_creator_evidence(
        db,
        user=current_user,
        creator_id=creator_id,
        identity_id=identity_id,
        request=payload,
        idempotency_key=idempotency_key,
        request_id=_request_id(http_request),
    )


@router.get("/creators", response_model=list[SocialCreatorRead])
def get_creators(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    platform: Annotated[SocialPlatform | None, Query()] = None,
    country_code: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    language_code: Annotated[str | None, Query(min_length=2, max_length=16)] = None,
    category: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    min_followers: Annotated[int | None, Query(ge=0)] = None,
    max_followers: Annotated[int | None, Query(ge=0)] = None,
    min_engagement_rate_bps: Annotated[int | None, Query(ge=0, le=10_000)] = None,
    audience_country_code: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    max_estimated_cost_minor: Annotated[int | None, Query(ge=0)] = None,
    currency: Annotated[str | None, Query(min_length=3, max_length=3)] = None,
    min_quality_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    require_contactable: Annotated[bool, Query()] = False,
    include_stale: Annotated[bool, Query()] = True,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[SocialCreatorRead]:
    try:
        filters = SocialAudienceFilters(
            platform=platform,
            country_code=country_code,
            language_code=language_code,
            category=category,
            min_followers=min_followers,
            max_followers=max_followers,
            min_engagement_rate_bps=min_engagement_rate_bps,
            audience_country_code=audience_country_code,
            max_estimated_cost_minor=max_estimated_cost_minor,
            currency=currency,
            min_quality_score=min_quality_score,
            require_contactable=require_contactable,
            include_stale=include_stale,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.errors(include_context=False),
        ) from exc
    return list_creators(db, user=current_user, filters=filters, offset=offset, limit=limit)


@router.post("/audiences", response_model=SocialAudienceRead, status_code=status.HTTP_201_CREATED)
def post_audience(
    payload: SocialAudienceCreate,
    http_request: Request,
    idempotency_key: IdempotencyHeader,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> SocialAudienceRead:
    return freeze_audience(
        db,
        user=current_user,
        request=payload,
        idempotency_key=idempotency_key,
        request_id=_request_id(http_request),
    )


@router.get("/audiences/{audience_id}", response_model=SocialAudienceRead)
def get_frozen_audience(
    audience_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> SocialAudienceRead:
    return get_audience(db, user=current_user, audience_id=audience_id)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or "request-unavailable")
