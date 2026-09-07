from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db import get_session
from app.db.models import User
from app.product_lifecycle.schema import (
    CreativeAssetReview,
    CreativeAssetVersionCreate,
    CreativeAssetVersionRead,
    CreativeBriefCreate,
    CreativeBriefRead,
    ListingComplianceCheckRead,
    ListingComplianceRun,
    ListingRuleSetCreate,
    ListingRuleSetPublish,
    ListingRuleSetRead,
    ProcurementRecommendationCreate,
    ProcurementRecommendationRead,
    ProcurementRecommendationReview,
    ProductLaunchGateCreate,
    ProductLaunchGateRead,
    ProductLaunchSubmit,
    ProductLifecycleOverview,
    ProductQualityIssueRead,
)
from app.product_lifecycle.service import (
    create_creative_asset_version,
    create_creative_brief,
    create_listing_rule_set,
    create_procurement_recommendation,
    evaluate_product_launch_gate,
    list_creative_assets,
    list_creative_briefs,
    list_listing_checks,
    list_listing_rule_sets,
    list_procurement_recommendations,
    list_product_launch_gates,
    list_product_quality_issues,
    product_lifecycle_overview,
    publish_listing_rule_set,
    review_creative_asset_version,
    review_procurement_recommendation,
    run_listing_compliance_check,
    submit_product_launch,
)
from app.security.auth import get_current_user

router = APIRouter(
    prefix="/api/enterprise/work-tasks/product-lifecycle",
    tags=["enterprise:product-lifecycle"],
)


@router.get("/overview", response_model=ProductLifecycleOverview)
def get_overview(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> ProductLifecycleOverview:
    return product_lifecycle_overview(db, tenant_id=tenant_id, user=current_user)


@router.get("/listing-rules", response_model=list[ListingRuleSetRead])
def get_listing_rules(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> list[ListingRuleSetRead]:
    return list_listing_rule_sets(db, tenant_id=tenant_id, user=current_user)


@router.post("/listing-rules", response_model=ListingRuleSetRead)
def post_listing_rule(
    request: ListingRuleSetCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> ListingRuleSetRead:
    return create_listing_rule_set(db, request=request, user=current_user)


@router.post("/listing-rules/{rule_set_id}/publish", response_model=ListingRuleSetRead)
def post_listing_rule_publish(
    rule_set_id: str,
    request: ListingRuleSetPublish,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> ListingRuleSetRead:
    return publish_listing_rule_set(db, rule_set_id=rule_set_id, request=request, user=current_user)


@router.get("/listing-checks", response_model=list[ListingComplianceCheckRead])
def get_listing_checks(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> list[ListingComplianceCheckRead]:
    return list_listing_checks(db, tenant_id=tenant_id, user=current_user)


@router.post("/listing-checks", response_model=ListingComplianceCheckRead)
def post_listing_check(
    request: ListingComplianceRun,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> ListingComplianceCheckRead:
    return run_listing_compliance_check(db, request=request, user=current_user)


@router.get("/creative-briefs", response_model=list[CreativeBriefRead])
def get_creative_briefs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> list[CreativeBriefRead]:
    return list_creative_briefs(db, tenant_id=tenant_id, user=current_user)


@router.post("/creative-briefs", response_model=CreativeBriefRead)
def post_creative_brief(
    request: CreativeBriefCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> CreativeBriefRead:
    return create_creative_brief(db, request=request, user=current_user)


@router.get("/creative-assets", response_model=list[CreativeAssetVersionRead])
def get_creative_assets(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> list[CreativeAssetVersionRead]:
    return list_creative_assets(db, tenant_id=tenant_id, user=current_user)


@router.post("/creative-assets", response_model=CreativeAssetVersionRead)
def post_creative_asset(
    request: CreativeAssetVersionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> CreativeAssetVersionRead:
    return create_creative_asset_version(db, request=request, user=current_user)


@router.post("/creative-assets/{asset_version_id}/review", response_model=CreativeAssetVersionRead)
def post_creative_asset_review(
    asset_version_id: str,
    request: CreativeAssetReview,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> CreativeAssetVersionRead:
    return review_creative_asset_version(
        db, asset_version_id=asset_version_id, request=request, user=current_user
    )


@router.get("/procurement-recommendations", response_model=list[ProcurementRecommendationRead])
def get_procurement_recommendations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> list[ProcurementRecommendationRead]:
    return list_procurement_recommendations(db, tenant_id=tenant_id, user=current_user)


@router.post("/procurement-recommendations", response_model=ProcurementRecommendationRead)
def post_procurement_recommendation(
    request: ProcurementRecommendationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> ProcurementRecommendationRead:
    return create_procurement_recommendation(db, request=request, user=current_user)


@router.post(
    "/procurement-recommendations/{recommendation_id}/review",
    response_model=ProcurementRecommendationRead,
)
def post_procurement_recommendation_review(
    recommendation_id: str,
    request: ProcurementRecommendationReview,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> ProcurementRecommendationRead:
    return review_procurement_recommendation(
        db,
        recommendation_id=recommendation_id,
        request=request,
        user=current_user,
    )


@router.get("/launch-gates", response_model=list[ProductLaunchGateRead])
def get_launch_gates(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> list[ProductLaunchGateRead]:
    return list_product_launch_gates(db, tenant_id=tenant_id, user=current_user)


@router.post("/launch-gates", response_model=ProductLaunchGateRead)
def post_launch_gate(
    request: ProductLaunchGateCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> ProductLaunchGateRead:
    return evaluate_product_launch_gate(db, request=request, user=current_user)


@router.post("/launch-gates/{launch_gate_id}/submit", response_model=ProductLaunchGateRead)
def post_launch_submit(
    launch_gate_id: str,
    request: ProductLaunchSubmit,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> ProductLaunchGateRead:
    return submit_product_launch(
        db, launch_gate_id=launch_gate_id, request=request, user=current_user
    )


@router.get("/quality-issues", response_model=list[ProductQualityIssueRead])
def get_quality_issues(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> list[ProductQualityIssueRead]:
    return list_product_quality_issues(db, tenant_id=tenant_id, user=current_user)
