from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.advertising.schema import (
    AdvertisingActionRequest,
    AdvertisingEffectFollowUpRead,
    AdvertisingOverview,
    AdvertisingRecommendationCreate,
    AdvertisingRecommendationRead,
    AutomationUsageRead,
    ExecutionAutomationPolicyRead,
    ExecutionAutomationPolicyUpsert,
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
