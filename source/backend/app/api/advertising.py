from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile
from sqlmodel import Session

from app.advertising.pdca_service import (
    create_pdca_search_term_run,
    list_pdca_search_term_runs,
)
from app.advertising.schema import (
    AdvertisingActionRequest,
    AdvertisingEffectFollowUpRead,
    AdvertisingOverview,
    AdvertisingRecommendationCreate,
    AdvertisingRecommendationRead,
    AutomationUsageRead,
    ExecutionAutomationPolicyRead,
    ExecutionAutomationPolicyUpsert,
    PdcaSearchTermRunRead,
)
from app.advertising.service import (
    advertising_overview,
    create_advertising_recommendation,
    list_advertising_effect_followups,
    list_advertising_recommendations,
    list_automation_usage,
    list_execution_automation_policies,
    request_advertising_action,
    upsert_execution_automation_policy,
)
from app.config import get_settings
from app.db import get_session
from app.db.models import User
from app.security.auth import get_current_user

router = APIRouter(
    prefix="/api/enterprise/work-tasks/advertising",
    tags=["enterprise:advertising-governance"],
)


@router.get("/overview", response_model=AdvertisingOverview)
def get_overview(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> AdvertisingOverview:
    return advertising_overview(db, tenant_id=tenant_id, user=current_user)


@router.get("/recommendations", response_model=list[AdvertisingRecommendationRead])
def get_recommendations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> list[AdvertisingRecommendationRead]:
    return list_advertising_recommendations(db, tenant_id=tenant_id, user=current_user)


@router.post("/recommendations", response_model=AdvertisingRecommendationRead)
def post_recommendation(
    request: AdvertisingRecommendationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> AdvertisingRecommendationRead:
    return create_advertising_recommendation(db, request=request, user=current_user)


@router.post(
    "/recommendations/{recommendation_id}/request-action",
    response_model=AdvertisingRecommendationRead,
)
def post_recommendation_action(
    recommendation_id: str,
    request: AdvertisingActionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> AdvertisingRecommendationRead:
    return request_advertising_action(
        db,
        recommendation_id=recommendation_id,
        request=request,
        user=current_user,
    )


@router.get("/effect-follow-ups", response_model=list[AdvertisingEffectFollowUpRead])
def get_effect_followups(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> list[AdvertisingEffectFollowUpRead]:
    return list_advertising_effect_followups(db, tenant_id=tenant_id, user=current_user)


@router.get("/automation-policies", response_model=list[ExecutionAutomationPolicyRead])
def get_automation_policies(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> list[ExecutionAutomationPolicyRead]:
    return list_execution_automation_policies(db, tenant_id=tenant_id, user=current_user)


@router.put("/automation-policies", response_model=ExecutionAutomationPolicyRead)
def put_automation_policy(
    request: ExecutionAutomationPolicyUpsert,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> ExecutionAutomationPolicyRead:
    return upsert_execution_automation_policy(db, request=request, user=current_user)


@router.get("/automation-usage", response_model=list[AutomationUsageRead])
def get_automation_usage(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> list[AutomationUsageRead]:
    return list_automation_usage(db, tenant_id=tenant_id, user=current_user)


@router.post("/pdca/search-term-runs", response_model=PdcaSearchTermRunRead)
async def post_pdca_search_term_run(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    tenant_id: Annotated[str, Query(min_length=1, max_length=128)],
    ad_account_resource_id: Annotated[str, Query(min_length=1, max_length=128)],
    target_acos: Annotated[Decimal, Query(gt=0, le=1)] = Decimal("0.30"),
    currency: Annotated[str, Query(min_length=3, max_length=3)] = "USD",
    store_resource_id: Annotated[str | None, Query(max_length=128)] = None,
    file: UploadFile = File(...),  # noqa: B008 - FastAPI binds multipart input.
) -> PdcaSearchTermRunRead:
    max_bytes = get_settings().pdca_upload_max_bytes
    data = await file.read(max_bytes + 1)
    return create_pdca_search_term_run(
        db,
        tenant_id=tenant_id,
        ad_account_resource_id=ad_account_resource_id,
        store_resource_id=store_resource_id,
        idempotency_key=idempotency_key,
        filename=file.filename or "search-terms.csv",
        content_type=file.content_type,
        data=data,
        target_acos=target_acos,
        currency=currency,
        user=current_user,
    )


@router.get("/pdca/search-term-runs", response_model=list[PdcaSearchTermRunRead])
def get_pdca_search_term_runs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query(min_length=1, max_length=128)],
) -> list[PdcaSearchTermRunRead]:
    return list_pdca_search_term_runs(db, tenant_id=tenant_id, user=current_user)
