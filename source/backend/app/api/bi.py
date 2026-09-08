from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.bi.schema import (
    BiDailyCommerceFactRead,
    BiDailyMetricRead,
    BiIngestionBatchCreate,
    BiIngestionBatchRead,
)
from app.bi.service import get_batch, ingest_batch, list_daily_metrics, list_facts
from app.db import get_session
from app.db.models import User
from app.security.auth import get_current_user

router = APIRouter(prefix="/api/enterprise/bi", tags=["enterprise:bi"])


@router.post("/ingestion-batches", response_model=BiIngestionBatchRead)
def post_ingestion_batch(
    request: BiIngestionBatchCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> BiIngestionBatchRead:
    return ingest_batch(db, request=request, user=current_user)


@router.get("/ingestion-batches/{batch_id}", response_model=BiIngestionBatchRead)
def get_ingestion_batch(
    batch_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query(min_length=1, max_length=128)],
) -> BiIngestionBatchRead:
    return get_batch(db, tenant_id=tenant_id, batch_id=batch_id, user=current_user)


@router.get("/metrics/daily", response_model=list[BiDailyMetricRead])
def get_daily_metrics(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query(min_length=1, max_length=128)],
    start_date: Annotated[date, Query()],
    end_date: Annotated[date, Query()],
    metric_code: Annotated[str | None, Query(max_length=80)] = None,
    brand_id: Annotated[str | None, Query(max_length=128)] = None,
    store_id: Annotated[str | None, Query(max_length=128)] = None,
    platform: Annotated[str | None, Query(max_length=80)] = None,
    entity_type: Annotated[str | None, Query(max_length=32)] = None,
) -> list[BiDailyMetricRead]:
    return list_daily_metrics(
        db,
        tenant_id=tenant_id,
        user=current_user,
        start_date=start_date,
        end_date=end_date,
        metric_code=metric_code,
        brand_id=brand_id,
        store_id=store_id,
        platform=platform,
        entity_type=entity_type,
    )


@router.get("/facts", response_model=list[BiDailyCommerceFactRead])
def get_facts(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query(min_length=1, max_length=128)],
    batch_id: Annotated[str | None, Query(max_length=128)] = None,
    business_date: Annotated[date | None, Query()] = None,
    store_id: Annotated[str | None, Query(max_length=128)] = None,
    current_only: Annotated[bool, Query()] = True,
) -> list[BiDailyCommerceFactRead]:
    return list_facts(
        db,
        tenant_id=tenant_id,
        user=current_user,
        batch_id=batch_id,
        business_date=business_date,
        store_id=store_id,
        current_only=current_only,
    )
