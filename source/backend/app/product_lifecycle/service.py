from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from app.business_resources.schema import HighRiskActionCreate
from app.business_resources.service import create_action_request
from app.config import get_settings
from app.db.database import set_tenant_context
from app.db.models import (
    AfterSalesCase,
    AuthorizationDecision,
    BusinessResource,
    CommerceGovernanceEvent,
    CreativeAssetVersion,
    CreativeBrief,
    HighRiskActionRequest,
    ListingComplianceCheck,
    ListingRuleSet,
    ProcurementRecommendation,
    ProductLaunchGate,
    ProductQualityIssue,
    User,
    utc_now,
)
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
from app.security.authorization import authorize_business_resource
from app.security.permissions import is_admin_user
from app.work_tasks.service import create_linked_task

_RULE_ROLES = {"listing_compliance_specialist", "operations_supervisor"}
_DESIGN_ROLES = {"designer", "operations_supervisor"}
_PROCUREMENT_ROLES = {"procurement_specialist", "operations_supervisor"}
_LAUNCH_ROLES = {"listing_compliance_specialist", "operations_supervisor"}
_VIEW_ROLES = (
    _RULE_ROLES
    | _DESIGN_ROLES
    | _PROCUREMENT_ROLES
    | {
        "advertising_inspection_specialist",
        "after_sales_specialist",
    }
)
_MANAGER_ROLES = {"operations_supervisor"}
_RULE_KEYS = {
    "banned_terms",
    "restricted_terms",
    "required_certifications",
    "required_labels",
    "intellectual_property_terms",
    "optimization_terms",
    "max_title_chars",
    "required_content_fields",
}
_CONTENT_KEYS = {
    "title",
    "bullets",
    "description",
    "a_plus",
    "attributes",
    "keywords",
    "image_text",
    "video_script",
    "declared_facts",
    "translations",
}
_FACT_KEYS = {
    "material",
    "dimensions",
    "size",
    "color",
    "country_of_origin",
    "model",
    "certifications",
    "package_quantity",
}
_ASSET_CHECKS = {
    "dimensions",
    "clarity",
    "text_safe_area",
    "logo",
    "brand_colors",
    "factual_consistency",
    "copyright",
}


def create_listing_rule_set(
    db: Session, *, request: ListingRuleSetCreate, user: User
) -> ListingRuleSetRead:
    _require_tenant(request.tenant_id, user)
    _require_role(user, _RULE_ROLES)
    set_tenant_context(db, request.tenant_id)
    rules = _bounded_object(request.rules, allowed_keys=_RULE_KEYS, max_bytes=32 * 1024)
    _validate_rule_shape(rules)
    sources = [source.model_dump(mode="json") for source in request.source_references]
    if request.expires_at and request.expires_at <= request.effective_at:
        raise HTTPException(status_code=422, detail="Rule expiry must be after effective time")
    scope = {
        "platform": request.platform.strip(),
        "marketplace": request.marketplace.strip().upper(),
        "category": request.category.strip(),
        "version": request.version.strip(),
        "rules": rules,
        "sources": sources,
        "effective_at": request.effective_at.isoformat(),
        "expires_at": request.expires_at.isoformat() if request.expires_at else None,
    }
    row = ListingRuleSet(
        tenant_id=request.tenant_id,
        platform=scope["platform"],
        marketplace=scope["marketplace"],
        category=scope["category"],
        version=scope["version"],
        rules_json=rules,
        content_digest=_digest(scope),
        source_references_json=sources,
        effective_at=_naive_utc(request.effective_at),
        expires_at=_naive_utc(request.expires_at) if request.expires_at else None,
        created_by_user_id=user.id,
    )
    db.add(row)
    try:
        db.flush()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Rule version already exists") from exc
    _event(db, "listing_rule_set", row.id, "draft_created", user, {"digest": row.content_digest})
    db.commit()
    db.refresh(row)
    return _rule_read(row)


def publish_listing_rule_set(
    db: Session, *, rule_set_id: str, request: ListingRuleSetPublish, user: User
) -> ListingRuleSetRead:
    _require_tenant(request.tenant_id, user)
    _require_manager(user)
    set_tenant_context(db, request.tenant_id)
    row = _one(db, ListingRuleSet, request.tenant_id, rule_set_id, "Rule set")
    if row.status != "draft":
        raise HTTPException(status_code=409, detail="Only a draft rule set can be published")
    if row.content_digest != request.expected_digest:
        raise HTTPException(status_code=409, detail="Rule content changed before review")
    now = utc_now()
    row.status = "published"
    row.reviewed_by_user_id = user.id
    row.reviewed_at = now
    db.add(row)
    _event(
        db,
        "listing_rule_set",
        row.id,
        "published",
        user,
        {"digest": row.content_digest, "review_note": request.review_note},
    )
    db.commit()
    db.refresh(row)
    return _rule_read(row)


def list_listing_rule_sets(db: Session, *, tenant_id: str, user: User) -> list[ListingRuleSetRead]:
    _require_tenant(tenant_id, user)
    _require_role(user, _VIEW_ROLES)
    set_tenant_context(db, tenant_id)
    rows = db.exec(
        select(ListingRuleSet)
        .where(ListingRuleSet.tenant_id == tenant_id)
        .order_by(ListingRuleSet.created_at.desc())
    ).all()
    return [_rule_read(row) for row in rows]


def run_listing_compliance_check(
    db: Session, *, request: ListingComplianceRun, user: User
) -> ListingComplianceCheckRead:
    _require_tenant(request.tenant_id, user)
    _require_role(user, _RULE_ROLES)
    set_tenant_context(db, request.tenant_id)
    existing = db.exec(
        select(ListingComplianceCheck).where(
            ListingComplianceCheck.tenant_id == request.tenant_id,
            ListingComplianceCheck.check_key == request.check_key.strip(),
        )
    ).first()
    if existing:
        return _check_read(existing)
    store = _authorized_resource(
        db,
        tenant_id=request.tenant_id,
        resource_id=request.store_resource_id,
        resource_type="store",
        user=user,
        action="READ",
    )
    rule_set = _one(db, ListingRuleSet, request.tenant_id, request.rule_set_id, "Rule set")
    if rule_set.status != "published":
        raise HTTPException(status_code=409, detail="A published rule version is required")
    sku_facts = _bounded_object(request.sku_facts, allowed_keys=_FACT_KEYS, max_bytes=16 * 1024)
    content = _bounded_object(request.content, allowed_keys=_CONTENT_KEYS, max_bytes=64 * 1024)
    _validate_content_shape(content)
    findings = _evaluate_listing(
        db,
        rule_set=rule_set,
        product_key=request.product_key,
        sku_facts=sku_facts,
        content=content,
        asset_version_ids=request.asset_version_ids,
    )
    gate_status = _finding_gate(findings)
    snapshot = {
        "store_resource_id": store.id,
        "product_key": request.product_key,
        "sku": request.sku,
        "language": request.language,
        "rule_set_id": rule_set.id,
        "rule_digest": rule_set.content_digest,
        "sku_fact_version": request.sku_fact_version,
        "sku_facts": sku_facts,
        "content": content,
        "asset_version_ids": sorted(set(request.asset_version_ids)),
    }
    row = ListingComplianceCheck(
        tenant_id=request.tenant_id,
        check_key=request.check_key.strip(),
        store_resource_id=store.id,
        product_key=request.product_key.strip(),
        sku=request.sku.strip(),
        language=request.language.strip(),
        rule_set_id=rule_set.id,
        rule_version=rule_set.version,
        rule_digest=rule_set.content_digest,
        sku_fact_version=request.sku_fact_version.strip(),
        sku_facts_json=sku_facts,
        content_json=content,
        asset_version_ids_json=sorted(set(request.asset_version_ids)),
        findings_json=findings,
        gate_status=gate_status,
        input_digest=_digest(snapshot),
        task_id="pending",
        created_by_user_id=user.id,
    )
    task, _ = create_linked_task(
        db,
        tenant_id=row.tenant_id,
        idempotency_key=f"listing-check:{row.check_key}",
        source_type="listing_compliance_check",
        source_id=row.id,
        title=f"Listing 合规检查 · {row.sku}",
        description=(
            f"{rule_set.platform}/{rule_set.marketplace}/"
            f"{rule_set.category} 规则 {rule_set.version}"
        ),
        owner_business_role="listing_compliance_specialist",
        assigned_by_user_id=user.id,
        assigned_by_business_role=user.business_role,
        priority="high" if gate_status == "block" else "normal",
        risk_level="high" if gate_status == "block" else "medium",
        scope={"store_resource_id": store.id, "store_code": store.code},
        input_data={"check_id": row.id, "input_digest": row.input_digest},
    )
    row.task_id = task.id
    db.add(row)
    db.flush()
    _event(
        db,
        "listing_compliance_check",
        row.id,
        "completed",
        user,
        {
            "gate_status": gate_status,
            "finding_count": len(findings),
            "rule_digest": row.rule_digest,
            "input_digest": row.input_digest,
        },
    )
    db.commit()
    db.refresh(row)
    return _check_read(row)


def list_listing_checks(
    db: Session, *, tenant_id: str, user: User
) -> list[ListingComplianceCheckRead]:
    _require_tenant(tenant_id, user)
    _require_role(user, _VIEW_ROLES)
    set_tenant_context(db, tenant_id)
    rows = db.exec(
        select(ListingComplianceCheck)
        .where(ListingComplianceCheck.tenant_id == tenant_id)
        .order_by(ListingComplianceCheck.created_at.desc())
        .limit(300)
    ).all()
    return [_check_read(row) for row in rows]


def create_creative_brief(
    db: Session, *, request: CreativeBriefCreate, user: User
) -> CreativeBriefRead:
    _require_tenant(request.tenant_id, user)
    _require_role(user, _DESIGN_ROLES)
    set_tenant_context(db, request.tenant_id)
    existing = db.exec(
        select(CreativeBrief).where(
            CreativeBrief.tenant_id == request.tenant_id,
            CreativeBrief.brief_key == request.brief_key.strip(),
        )
    ).first()
    if existing:
        return _brief_read(existing)
    store = _authorized_resource(
        db,
        tenant_id=request.tenant_id,
        resource_id=request.store_resource_id,
        resource_type="store",
        user=user,
        action="REQUEST",
    )
    dimensions = _bounded_object(request.dimensions, max_bytes=8 * 1024)
    constraints = _bounded_object(request.constraints, max_bytes=16 * 1024)
    row = CreativeBrief(
        tenant_id=request.tenant_id,
        brief_key=request.brief_key.strip(),
        store_resource_id=store.id,
        product_key=request.product_key.strip(),
        language=request.language.strip(),
        dimensions_json=dimensions,
        selling_points_json=_clean_strings(request.selling_points),
        scenes_json=_clean_strings(request.scenes),
        required_assets_json=_clean_strings(request.required_assets),
        constraints_json=constraints,
        task_id="pending",
        due_at=_naive_utc(request.due_at) if request.due_at else None,
        created_by_user_id=user.id,
    )
    task, _ = create_linked_task(
        db,
        tenant_id=row.tenant_id,
        idempotency_key=f"creative-brief:{row.brief_key}",
        source_type="creative_brief",
        source_id=row.id,
        title=f"创意 Brief · {row.product_key}",
        description="、".join(row.required_assets_json),
        owner_business_role="designer",
        assigned_by_user_id=user.id,
        assigned_by_business_role=user.business_role,
        priority="normal",
        risk_level="medium",
        due_at=row.due_at,
        scope={"store_resource_id": store.id, "store_code": store.code},
        input_data={"brief_id": row.id, "required_assets": row.required_assets_json},
    )
    row.task_id = task.id
    db.add(row)
    db.flush()
    _event(db, "creative_brief", row.id, "created", user, {"task_id": task.id})
    db.commit()
    db.refresh(row)
    return _brief_read(row)


def list_creative_briefs(db: Session, *, tenant_id: str, user: User) -> list[CreativeBriefRead]:
    _require_tenant(tenant_id, user)
    _require_role(user, _VIEW_ROLES)
    set_tenant_context(db, tenant_id)
    rows = db.exec(
        select(CreativeBrief)
        .where(CreativeBrief.tenant_id == tenant_id)
        .order_by(CreativeBrief.created_at.desc())
        .limit(300)
    ).all()
    return [_brief_read(row) for row in rows]


def create_creative_asset_version(
    db: Session, *, request: CreativeAssetVersionCreate, user: User
) -> CreativeAssetVersionRead:
    _require_tenant(request.tenant_id, user)
    _require_role(user, _DESIGN_ROLES)
    set_tenant_context(db, request.tenant_id)
    brief = _one(db, CreativeBrief, request.tenant_id, request.brief_id, "Creative brief")
    parent = None
    if request.parent_version_id:
        parent = _one(
            db,
            CreativeAssetVersion,
            request.tenant_id,
            request.parent_version_id,
            "Parent asset version",
        )
        if parent.asset_key != request.asset_key or parent.brief_id != brief.id:
            raise HTTPException(status_code=422, detail="Parent asset belongs to another lineage")
    latest = db.exec(
        select(CreativeAssetVersion)
        .where(
            CreativeAssetVersion.tenant_id == request.tenant_id,
            CreativeAssetVersion.asset_key == request.asset_key.strip(),
        )
        .order_by(CreativeAssetVersion.version.desc())
    ).first()
    if latest and not parent:
        raise HTTPException(status_code=409, detail="A new asset version must identify its parent")
    if parent and latest and parent.id != latest.id:
        raise HTTPException(
            status_code=409, detail="Asset version must branch from the latest version"
        )
    provenance = _bounded_object(request.provenance, max_bytes=16 * 1024)
    if not provenance.get("source") or not provenance.get("license"):
        raise HTTPException(status_code=422, detail="Asset provenance requires source and license")
    parameters = _bounded_object(request.generation_parameters, max_bytes=16 * 1024)
    checks = _bounded_object(request.checks, allowed_keys=_ASSET_CHECKS, max_bytes=16 * 1024)
    missing_checks = sorted(_ASSET_CHECKS - set(checks))
    failed_checks = sorted(key for key, value in checks.items() if not _check_passed(value))
    status = "draft" if missing_checks or failed_checks else "pending_review"
    required_human = (
        request.asset_type in {"main_image", "brand_story", "packaging"}
        or request.contains_sensitive_claims
    )
    row = CreativeAssetVersion(
        tenant_id=request.tenant_id,
        asset_key=request.asset_key.strip(),
        version=(latest.version + 1) if latest else 1,
        brief_id=brief.id,
        parent_version_id=parent.id if parent else None,
        store_resource_id=brief.store_resource_id,
        product_key=brief.product_key,
        asset_type=request.asset_type,
        file_reference=request.file_reference.strip(),
        file_digest=request.file_digest.strip().lower(),
        provenance_json=provenance,
        generation_parameters_json=parameters,
        checks_json={
            **checks,
            "missing_checks": missing_checks,
            "failed_checks": failed_checks,
            "contains_sensitive_claims": request.contains_sensitive_claims,
        },
        required_human_approval=required_human,
        status=status,
        creator_user_id=user.id,
    )
    db.add(row)
    db.flush()
    brief.status = "in_progress"
    brief.updated_at = utc_now()
    db.add(brief)
    _event(
        db,
        "creative_asset_version",
        row.id,
        "version_created",
        user,
        {
            "version": row.version,
            "parent_version_id": row.parent_version_id,
            "file_digest": row.file_digest,
            "status": row.status,
            "failed_checks": failed_checks,
        },
    )
    db.commit()
    db.refresh(row)
    return _asset_read(row)


def review_creative_asset_version(
    db: Session, *, asset_version_id: str, request: CreativeAssetReview, user: User
) -> CreativeAssetVersionRead:
    _require_tenant(request.tenant_id, user)
    _require_manager(user)
    set_tenant_context(db, request.tenant_id)
    row = _one(db, CreativeAssetVersion, request.tenant_id, asset_version_id, "Asset version")
    if row.status not in {"pending_review", "draft"}:
        raise HTTPException(status_code=409, detail="Asset version already has a final review")
    failures = list(row.checks_json.get("missing_checks", [])) + list(
        row.checks_json.get("failed_checks", [])
    )
    if request.decision == "approved" and failures:
        raise HTTPException(
            status_code=409, detail="Failed asset checks must be corrected in a new version"
        )
    row.status = request.decision
    row.reviewed_by_user_id = user.id
    row.review_note = request.note.strip()
    row.reviewed_at = utc_now()
    db.add(row)
    _event(
        db,
        "creative_asset_version",
        row.id,
        f"review_{request.decision}",
        user,
        {"file_digest": row.file_digest, "note": request.note},
    )
    db.commit()
    db.refresh(row)
    return _asset_read(row)


def list_creative_assets(
    db: Session, *, tenant_id: str, user: User
) -> list[CreativeAssetVersionRead]:
    _require_tenant(tenant_id, user)
    _require_role(user, _VIEW_ROLES)
    set_tenant_context(db, tenant_id)
    rows = db.exec(
        select(CreativeAssetVersion)
        .where(CreativeAssetVersion.tenant_id == tenant_id)
        .order_by(CreativeAssetVersion.created_at.desc())
        .limit(500)
    ).all()
    return [_asset_read(row) for row in rows]


def create_procurement_recommendation(
    db: Session, *, request: ProcurementRecommendationCreate, user: User
) -> ProcurementRecommendationRead:
    _require_tenant(request.tenant_id, user)
    _require_role(user, _PROCUREMENT_ROLES)
    set_tenant_context(db, request.tenant_id)
    existing = db.exec(
        select(ProcurementRecommendation).where(
            ProcurementRecommendation.tenant_id == request.tenant_id,
            ProcurementRecommendation.recommendation_key == request.recommendation_key.strip(),
        )
    ).first()
    if existing:
        return _procurement_read(existing)
    supplier = _authorized_resource(
        db,
        tenant_id=request.tenant_id,
        resource_id=request.supplier_resource_id,
        resource_type="supplier",
        user=user,
        action="READ",
    )
    if request.store_resource_id:
        _authorized_resource(
            db,
            tenant_id=request.tenant_id,
            resource_id=request.store_resource_id,
            resource_type="store",
            user=user,
            action="READ",
        )
    gross_demand = math.ceil(
        request.forecast_daily_sales * request.planning_horizon_days
        + request.promotion_units
        + request.advertising_lift_units
    )
    net_need = max(
        0,
        gross_demand + request.safety_stock_units - request.available_units - request.inbound_units,
    )
    quantity = math.ceil(net_need / request.moq) * request.moq if net_need else 0
    unit_landed = request.quote_unit_cost + request.freight_unit_cost + request.duty_unit_cost
    landed_cost = round(quantity * unit_landed, 2)
    quote_age_days = max(0, (utc_now() - _naive_utc(request.quote_observed_at)).days)
    reasons: list[str] = []
    if request.lead_time_days >= request.planning_horizon_days:
        reasons.append("lead_time_exceeds_planning_horizon")
    if quote_age_days > 30:
        reasons.append("supplier_quote_is_stale")
    if request.qc_failure_rate > 0.05:
        reasons.append("qc_failure_rate_above_5_percent")
    if landed_cost > request.cash_budget:
        reasons.append("estimated_cost_exceeds_cash_budget")
    if request.available_units < math.ceil(request.forecast_daily_sales * request.lead_time_days):
        reasons.append("stockout_before_replenishment_arrival")
    risk = (
        "high"
        if any("cash_budget" in item or "stockout" in item for item in reasons)
        else ("medium" if reasons else "low")
    )
    snapshot = request.model_dump(mode="json")
    formula = (
        "ceil_to_MOQ(max(0, forecast_daily_sales*planning_horizon_days "
        "+ promotion_units + advertising_lift_units + safety_stock_units "
        "- available_units - inbound_units))"
    )
    row = ProcurementRecommendation(
        tenant_id=request.tenant_id,
        recommendation_key=request.recommendation_key.strip(),
        supplier_resource_id=supplier.id,
        store_resource_id=request.store_resource_id,
        product_key=request.product_key.strip(),
        sku=request.sku.strip(),
        input_snapshot_json=snapshot,
        formula=formula,
        recommended_quantity=quantity,
        estimated_landed_cost=landed_cost,
        lead_time_days=request.lead_time_days,
        risk_level=risk,
        risk_reasons_json=reasons,
        task_id="pending",
        created_by_user_id=user.id,
    )
    task, _ = create_linked_task(
        db,
        tenant_id=row.tenant_id,
        idempotency_key=f"procurement-recommendation:{row.recommendation_key}",
        source_type="procurement_recommendation",
        source_id=row.id,
        title=f"采购建议 · {row.sku} · {quantity} 件",
        description=(
            f"预计落地成本 {landed_cost:.2f} {request.currency.upper()}；仅供审核，不创建采购单。"
        ),
        owner_business_role="procurement_specialist",
        assigned_by_user_id=user.id,
        assigned_by_business_role=user.business_role,
        priority="high" if risk == "high" else "normal",
        risk_level=risk,
        scope={
            "supplier_resource_id": supplier.id,
            "store_resource_id": request.store_resource_id,
        },
        input_data={"recommendation_id": row.id, "formula": formula},
    )
    row.task_id = task.id
    db.add(row)
    db.flush()
    _event(
        db,
        "procurement_recommendation",
        row.id,
        "calculated",
        user,
        {
            "recommended_quantity": quantity,
            "estimated_landed_cost": landed_cost,
            "risk_reasons": reasons,
            "purchase_order_created": False,
        },
    )
    db.commit()
    db.refresh(row)
    return _procurement_read(row)


def review_procurement_recommendation(
    db: Session,
    *,
    recommendation_id: str,
    request: ProcurementRecommendationReview,
    user: User,
) -> ProcurementRecommendationRead:
    _require_tenant(request.tenant_id, user)
    _require_manager(user)
    set_tenant_context(db, request.tenant_id)
    row = _one(
        db,
        ProcurementRecommendation,
        request.tenant_id,
        recommendation_id,
        "Procurement recommendation",
    )
    if row.status != "draft":
        raise HTTPException(status_code=409, detail="Recommendation already has a final review")
    row.status = request.decision
    row.reviewed_by_user_id = user.id
    row.review_note = request.note.strip()
    row.reviewed_at = utc_now()
    db.add(row)
    _event(
        db,
        "procurement_recommendation",
        row.id,
        f"review_{row.status}",
        user,
        {"note": request.note, "purchase_order_created": False},
    )
    db.commit()
    db.refresh(row)
    return _procurement_read(row)


def list_procurement_recommendations(
    db: Session, *, tenant_id: str, user: User
) -> list[ProcurementRecommendationRead]:
    _require_tenant(tenant_id, user)
    _require_role(user, _VIEW_ROLES)
    set_tenant_context(db, tenant_id)
    rows = db.exec(
        select(ProcurementRecommendation)
        .where(ProcurementRecommendation.tenant_id == tenant_id)
        .order_by(ProcurementRecommendation.created_at.desc())
        .limit(300)
    ).all()
    return [_procurement_read(row) for row in rows]


def evaluate_product_launch_gate(
    db: Session, *, request: ProductLaunchGateCreate, user: User
) -> ProductLaunchGateRead:
    _require_tenant(request.tenant_id, user)
    _require_role(user, _LAUNCH_ROLES)
    set_tenant_context(db, request.tenant_id)
    existing = db.exec(
        select(ProductLaunchGate).where(
            ProductLaunchGate.tenant_id == request.tenant_id,
            ProductLaunchGate.launch_key == request.launch_key.strip(),
        )
    ).first()
    if existing:
        return _launch_read(db, existing)
    store = _authorized_resource(
        db,
        tenant_id=request.tenant_id,
        resource_id=request.store_resource_id,
        resource_type="store",
        user=user,
        action="REQUEST",
    )
    _authorized_resource(
        db,
        tenant_id=request.tenant_id,
        resource_id=request.supplier_resource_id,
        resource_type="supplier",
        user=user,
        action="READ",
    )
    facts = _launch_evidence(db, request)
    blockers = facts["blockers"]
    snapshot = facts["snapshot"]
    status = "blocked" if blockers else "ready"
    row = ProductLaunchGate(
        tenant_id=request.tenant_id,
        launch_key=request.launch_key.strip(),
        store_resource_id=store.id,
        supplier_resource_id=request.supplier_resource_id,
        product_key=request.product_key.strip(),
        sku=request.sku.strip(),
        sku_fact_version=request.sku_fact_version.strip(),
        bom_version=request.bom_version.strip(),
        packaging_version=request.packaging_version.strip(),
        certification_ids_json=sorted(set(request.certification_ids)),
        supplier_lead_time_confirmed=request.supplier_lead_time_confirmed,
        listing_check_id=request.listing_check_id,
        asset_version_ids_json=sorted(set(request.asset_version_ids)),
        procurement_recommendation_id=request.procurement_recommendation_id,
        blockers_json=blockers,
        evidence_digest=_digest(snapshot),
        status=status,
        task_id="pending",
        created_by_user_id=user.id,
    )
    task, _ = create_linked_task(
        db,
        tenant_id=row.tenant_id,
        idempotency_key=f"product-launch-gate:{row.launch_key}",
        source_type="product_launch_gate",
        source_id=row.id,
        title=f"新品发布门禁 · {row.sku}",
        description=(
            "存在阻断项，请修复后创建新的门禁评估。"
            if blockers
            else "证据齐备，可提交人工发布审批。"
        ),
        owner_business_role="operations_supervisor",
        assigned_by_user_id=user.id,
        assigned_by_business_role=user.business_role,
        priority="high" if blockers else "normal",
        risk_level="high" if blockers else "medium",
        scope={"store_resource_id": store.id, "supplier_resource_id": request.supplier_resource_id},
        input_data={
            "launch_gate_id": row.id,
            "evidence_digest": row.evidence_digest,
            "supplier_lead_time_confirmed": request.supplier_lead_time_confirmed,
        },
    )
    row.task_id = task.id
    db.add(row)
    db.flush()
    _event(
        db,
        "product_launch_gate",
        row.id,
        "evaluated",
        user,
        {"status": status, "blockers": blockers, "evidence_digest": row.evidence_digest},
    )
    db.commit()
    db.refresh(row)
    return _launch_read(db, row)


def submit_product_launch(
    db: Session, *, launch_gate_id: str, request: ProductLaunchSubmit, user: User
) -> ProductLaunchGateRead:
    _require_tenant(request.tenant_id, user)
    _require_role(user, _LAUNCH_ROLES)
    set_tenant_context(db, request.tenant_id)
    row = _one(db, ProductLaunchGate, request.tenant_id, launch_gate_id, "Launch gate")
    if row.version != request.expected_version:
        raise HTTPException(status_code=409, detail="Launch gate changed; reload before submitting")
    if row.status != "ready":
        raise HTTPException(status_code=409, detail="Only a ready launch gate can be submitted")
    current_blockers = _revalidate_launch(db, row)
    if current_blockers:
        row.status = "blocked"
        row.blockers_json = current_blockers
        row.version += 1
        row.updated_at = utc_now()
        db.add(row)
        _event(
            db,
            "product_launch_gate",
            row.id,
            "evidence_invalidated",
            user,
            {"blockers": current_blockers},
        )
        db.commit()
        raise HTTPException(status_code=409, detail="Launch evidence changed and is now blocked")
    approval = create_action_request(
        db,
        request=HighRiskActionCreate(
            tenant_id=row.tenant_id,
            resource_id=row.store_resource_id,
            action_type="publish_listing",
            summary=request.summary,
            payload={
                "listing_id": request.listing_id,
                "marketplace": request.marketplace.upper(),
                "product_type": request.product_type,
                "attributes": request.attributes,
                "launch_gate_id": row.id,
                "launch_evidence_digest": row.evidence_digest,
                "listing_check_id": row.listing_check_id,
                "asset_version_ids": row.asset_version_ids_json,
                "sku_fact_version": row.sku_fact_version,
            },
        ),
        user=user,
        commit=False,
    )
    row.status = "waiting_approval"
    row.approval_request_id = approval.id
    row.version += 1
    row.updated_at = utc_now()
    db.add(row)
    _event(
        db,
        "product_launch_gate",
        row.id,
        "publish_approval_requested",
        user,
        {"approval_request_id": approval.id, "evidence_digest": row.evidence_digest},
    )
    db.commit()
    db.refresh(row)
    return _launch_read(db, row)


def list_product_launch_gates(
    db: Session, *, tenant_id: str, user: User
) -> list[ProductLaunchGateRead]:
    _require_tenant(tenant_id, user)
    _require_role(user, _VIEW_ROLES)
    set_tenant_context(db, tenant_id)
    rows = db.exec(
        select(ProductLaunchGate)
        .where(ProductLaunchGate.tenant_id == tenant_id)
        .order_by(ProductLaunchGate.created_at.desc())
        .limit(300)
    ).all()
    return [_launch_read(db, row) for row in rows]


def record_quality_issue_from_after_sales(
    db: Session,
    *,
    case: AfterSalesCase,
    root_cause: str,
    task_ids: list[str],
    user: User,
) -> ProductQualityIssue | None:
    """Persist the multi-role quality loop in the caller's transaction."""

    if case.category not in {"damaged", "wrong_item"}:
        return None
    existing = db.exec(
        select(ProductQualityIssue).where(
            ProductQualityIssue.tenant_id == case.tenant_id,
            ProductQualityIssue.source_case_id == case.id,
        )
    ).first()
    if existing:
        return existing
    sku_codes = case.order_snapshot_json.get("sku_codes", [])
    product_key = str(sku_codes[0]) if isinstance(sku_codes, list) and sku_codes else "unknown"
    row = ProductQualityIssue(
        tenant_id=case.tenant_id,
        source_case_id=case.id,
        store_resource_id=case.store_resource_id,
        product_key=product_key,
        category=case.category,
        root_cause=root_cause.strip(),
        task_ids_json=list(task_ids),
        created_by_user_id=user.id,
    )
    db.add(row)
    db.flush()
    _event(
        db,
        "product_quality_issue",
        row.id,
        "created_from_after_sales",
        user,
        {"source_case_id": case.id, "task_ids": task_ids},
    )
    return row


def list_product_quality_issues(
    db: Session, *, tenant_id: str, user: User
) -> list[ProductQualityIssueRead]:
    _require_tenant(tenant_id, user)
    _require_role(user, _VIEW_ROLES)
    set_tenant_context(db, tenant_id)
    rows = db.exec(
        select(ProductQualityIssue)
        .where(ProductQualityIssue.tenant_id == tenant_id)
        .order_by(ProductQualityIssue.created_at.desc())
        .limit(300)
    ).all()
    return [_quality_read(row) for row in rows]


def product_lifecycle_overview(
    db: Session, *, tenant_id: str, user: User
) -> ProductLifecycleOverview:
    _require_tenant(tenant_id, user)
    _require_role(user, _VIEW_ROLES)
    set_tenant_context(db, tenant_id)
    rules = db.exec(select(ListingRuleSet).where(ListingRuleSet.tenant_id == tenant_id)).all()
    checks = db.exec(
        select(ListingComplianceCheck).where(ListingComplianceCheck.tenant_id == tenant_id)
    ).all()
    assets = db.exec(
        select(CreativeAssetVersion).where(CreativeAssetVersion.tenant_id == tenant_id)
    ).all()
    recommendations = db.exec(
        select(ProcurementRecommendation).where(ProcurementRecommendation.tenant_id == tenant_id)
    ).all()
    launches = db.exec(
        select(ProductLaunchGate).where(ProductLaunchGate.tenant_id == tenant_id)
    ).all()
    quality = db.exec(
        select(ProductQualityIssue).where(ProductQualityIssue.tenant_id == tenant_id)
    ).all()
    return ProductLifecycleOverview(
        published_rule_sets=sum(item.status == "published" for item in rules),
        blocked_listing_checks=sum(item.gate_status == "block" for item in checks),
        creative_assets_waiting_review=sum(item.status == "pending_review" for item in assets),
        procurement_recommendations_waiting_review=sum(
            item.status == "draft" for item in recommendations
        ),
        launch_gates_blocked=sum(item.status == "blocked" for item in launches),
        launch_gates_waiting_approval=sum(item.status == "waiting_approval" for item in launches),
        open_quality_issues=sum(item.status != "resolved" for item in quality),
    )


def _evaluate_listing(
    db: Session,
    *,
    rule_set: ListingRuleSet,
    product_key: str,
    sku_facts: dict[str, Any],
    content: dict[str, Any],
    asset_version_ids: list[str],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def add(location: str, risk: str, rule: str, evidence: str, suggestion: str, gate: str) -> None:
        findings.append(
            {
                "location": location,
                "risk": risk,
                "rule": rule,
                "evidence": evidence[:500],
                "suggestion": suggestion[:500],
                "gate": gate,
            }
        )

    now = utc_now()
    if rule_set.effective_at > now or (rule_set.expires_at and rule_set.expires_at <= now):
        add(
            "rule_version",
            "critical",
            "rule_version_current",
            rule_set.version,
            "Select a currently effective reviewed rule version.",
            "block",
        )
    searchable = _flatten_content(content)
    lower = searchable.casefold()
    for term in _as_strings(rule_set.rules_json.get("banned_terms")):
        if term.casefold() in lower:
            add(
                "content",
                "critical",
                "banned_term",
                term,
                f"Remove prohibited term: {term}",
                "block",
            )
    certifications = {item.casefold() for item in _as_strings(sku_facts.get("certifications"))}
    for cert in _as_strings(rule_set.rules_json.get("required_certifications")):
        if cert.casefold() not in certifications:
            add(
                "sku_facts.certifications",
                "critical",
                "required_certification",
                cert,
                f"Attach reviewed certification evidence for {cert}.",
                "block",
            )
    for item in rule_set.rules_json.get("restricted_terms", []) or []:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        required_cert = str(item.get("required_certification") or "").strip()
        if term and term.casefold() in lower and required_cert.casefold() not in certifications:
            add(
                "content",
                "high",
                "restricted_claim",
                term,
                f"Remove the claim or provide certification {required_cert}.",
                str(item.get("gate") or "block"),
            )
    for term in _as_strings(rule_set.rules_json.get("intellectual_property_terms")):
        if term.casefold() in lower:
            add(
                "content",
                "high",
                "intellectual_property_review",
                term,
                "Obtain documented authorization or replace the protected reference.",
                "block",
            )
    required_fields = _as_strings(rule_set.rules_json.get("required_content_fields")) or [
        "title",
        "bullets",
        "description",
    ]
    for field in required_fields:
        if not content.get(field):
            add(
                field,
                "high",
                "required_content",
                "missing",
                f"Provide {field} before final review.",
                "block",
            )
    max_title = int(rule_set.rules_json.get("max_title_chars") or 0)
    title = str(content.get("title") or "")
    if max_title and len(title) > max_title:
        add(
            "title",
            "medium",
            "title_length",
            str(len(title)),
            f"Reduce title to at most {max_title} characters.",
            "warn",
        )
    for label in _as_strings(rule_set.rules_json.get("required_labels")):
        if label.casefold() not in lower:
            add(
                "content",
                "high",
                "required_label",
                label,
                f"Add mandatory label text: {label}",
                "block",
            )
    declared = content.get("declared_facts") or {}
    if isinstance(declared, dict):
        _compare_facts(add, "declared_facts", sku_facts, declared)
    translations = content.get("translations") or {}
    if isinstance(translations, dict):
        for locale, translated in translations.items():
            if isinstance(translated, dict):
                facts = translated.get("declared_facts") or {}
                if isinstance(facts, dict):
                    _compare_facts(add, f"translations.{locale}.declared_facts", sku_facts, facts)
    for term in _as_strings(rule_set.rules_json.get("optimization_terms")):
        if term.casefold() not in lower:
            add(
                "keywords",
                "low",
                "optimization_opportunity",
                term,
                f"Consider adding relevant term: {term}",
                "warn",
            )
    for asset_id in sorted(set(asset_version_ids)):
        asset = db.exec(
            select(CreativeAssetVersion).where(
                CreativeAssetVersion.tenant_id == rule_set.tenant_id,
                CreativeAssetVersion.id == asset_id,
            )
        ).first()
        if not asset or asset.product_key != product_key or asset.status != "approved":
            add(
                "asset_version_ids",
                "high",
                "approved_asset_required",
                asset_id,
                "Use an approved asset version from the same product.",
                "block",
            )
    return findings


def _compare_facts(add, location: str, expected: dict[str, Any], actual: dict[str, Any]) -> None:
    for key in sorted(_FACT_KEYS & set(actual) & set(expected)):
        if _canonical(actual[key]) != _canonical(expected[key]):
            add(
                f"{location}.{key}",
                "critical",
                "sku_fact_consistency",
                str(actual[key]),
                f"Align with approved SKU fact: {expected[key]}",
                "block",
            )


def _finding_gate(findings: list[dict[str, Any]]) -> str:
    if any(item["gate"] == "block" for item in findings):
        return "block"
    if findings:
        return "warn"
    return "pass"


def _launch_evidence(db: Session, request: ProductLaunchGateCreate) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []

    def block(code: str, detail: str) -> None:
        blockers.append({"code": code, "detail": detail})

    check = _one(
        db, ListingComplianceCheck, request.tenant_id, request.listing_check_id, "Listing check"
    )
    if check.product_key != request.product_key or check.sku != request.sku:
        block("listing_product_mismatch", "Listing check belongs to another product or SKU")
    if check.gate_status == "block":
        block("listing_blocked", "Listing compliance check contains blocking findings")
    if check.sku_fact_version != request.sku_fact_version:
        block("sku_fact_version_mismatch", "Launch SKU facts differ from listing review")
    rule = _one(db, ListingRuleSet, request.tenant_id, check.rule_set_id, "Rule set")
    now = utc_now()
    if rule.status != "published" or rule.content_digest != check.rule_digest:
        block("rule_version_changed", "Listing rule evidence is no longer published or unchanged")
    if rule.effective_at > now or (rule.expires_at and rule.expires_at <= now):
        block("rule_version_stale", "Listing rule version is not currently effective")
    required_certs = {
        item.casefold() for item in _as_strings(rule.rules_json.get("required_certifications"))
    }
    supplied_certs = {item.casefold() for item in request.certification_ids}
    for missing in sorted(required_certs - supplied_certs):
        block("certification_missing", missing)
    asset_digests: list[str] = []
    for asset_id in sorted(set(request.asset_version_ids)):
        asset = db.exec(
            select(CreativeAssetVersion).where(
                CreativeAssetVersion.tenant_id == request.tenant_id,
                CreativeAssetVersion.id == asset_id,
            )
        ).first()
        if not asset or asset.product_key != request.product_key:
            block("asset_product_mismatch", asset_id)
        elif asset.status != "approved":
            block("asset_not_approved", asset_id)
        else:
            asset_digests.append(asset.file_digest)
    recommendation = _one(
        db,
        ProcurementRecommendation,
        request.tenant_id,
        request.procurement_recommendation_id,
        "Procurement recommendation",
    )
    if (
        recommendation.product_key != request.product_key
        or recommendation.supplier_resource_id != request.supplier_resource_id
    ):
        block(
            "procurement_scope_mismatch",
            "Procurement recommendation belongs to another product or supplier",
        )
    if recommendation.status != "reviewed":
        block("procurement_not_reviewed", "Procurement recommendation requires supervisor review")
    if not request.supplier_lead_time_confirmed:
        block("supplier_lead_time_unavailable", "Supplier lead time is not confirmed")
    snapshot = {
        "listing_check_id": check.id,
        "listing_input_digest": check.input_digest,
        "rule_digest": check.rule_digest,
        "sku_fact_version": request.sku_fact_version,
        "bom_version": request.bom_version,
        "packaging_version": request.packaging_version,
        "certification_ids": sorted(set(request.certification_ids)),
        "asset_version_ids": sorted(set(request.asset_version_ids)),
        "asset_digests": sorted(asset_digests),
        "procurement_recommendation_id": recommendation.id,
        "procurement_status": recommendation.status,
        "supplier_lead_time_confirmed": request.supplier_lead_time_confirmed,
        "blockers": blockers,
    }
    return {"blockers": blockers, "snapshot": snapshot}


def _revalidate_launch(db: Session, row: ProductLaunchGate) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    check = _one(db, ListingComplianceCheck, row.tenant_id, row.listing_check_id, "Listing check")
    rule = _one(db, ListingRuleSet, row.tenant_id, check.rule_set_id, "Rule set")
    now = utc_now()
    if check.gate_status == "block" or check.sku_fact_version != row.sku_fact_version:
        blockers.append({"code": "listing_evidence_invalid", "detail": check.id})
    if (
        rule.status != "published"
        or rule.content_digest != check.rule_digest
        or rule.effective_at > now
        or (rule.expires_at and rule.expires_at <= now)
    ):
        blockers.append({"code": "rule_version_stale", "detail": rule.id})
    for asset_id in row.asset_version_ids_json:
        asset = db.exec(
            select(CreativeAssetVersion).where(
                CreativeAssetVersion.tenant_id == row.tenant_id,
                CreativeAssetVersion.id == asset_id,
                CreativeAssetVersion.status == "approved",
                CreativeAssetVersion.product_key == row.product_key,
            )
        ).first()
        if not asset:
            blockers.append({"code": "asset_not_approved", "detail": asset_id})
    recommendation = _one(
        db,
        ProcurementRecommendation,
        row.tenant_id,
        row.procurement_recommendation_id,
        "Procurement recommendation",
    )
    if recommendation.status != "reviewed":
        blockers.append({"code": "procurement_not_reviewed", "detail": recommendation.id})
    return blockers


def _authorized_resource(
    db: Session,
    *,
    tenant_id: str,
    resource_id: str,
    resource_type: str,
    user: User,
    action: str,
) -> BusinessResource:
    row = db.exec(
        select(BusinessResource).where(
            BusinessResource.tenant_id == tenant_id,
            BusinessResource.id == resource_id,
            BusinessResource.resource_type == resource_type,
            BusinessResource.status == "active",
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Business resource not found")
    result = authorize_business_resource(
        get_settings(), db=db, user=user, resource=row, action=action
    )
    db.add(
        AuthorizationDecision(
            tenant_id=tenant_id,
            subject_id=user.id,
            subject_type="human",
            role=result.role,
            department_id=user.business_role or result.role,
            store_id=row.code if row.resource_type == "store" else "",
            resource_type=row.resource_type,
            object=f"business_resource:{row.id}",
            action=action,
            effect="allow" if result.allowed else "deny",
            reason=result.reason,
            policy_version=result.policy_version,
            request_id=f"product_lifecycle_{uuid4().hex}",
        )
    )
    db.flush()
    if not result.allowed:
        db.commit()
        raise HTTPException(status_code=404, detail="Business resource not found")
    return row


def _event(
    db: Session,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    user: User,
    detail: dict[str, Any],
) -> None:
    db.add(
        CommerceGovernanceEvent(
            tenant_id=user.tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            actor_id=user.id,
            actor_business_role=user.business_role,
            detail_json=detail,
        )
    )


def _one(db: Session, model, tenant_id: str, item_id: str, label: str):
    row = db.exec(select(model).where(model.tenant_id == tenant_id, model.id == item_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return row


def _rule_read(row: ListingRuleSet) -> ListingRuleSetRead:
    return ListingRuleSetRead(
        id=row.id,
        tenant_id=row.tenant_id,
        platform=row.platform,
        marketplace=row.marketplace,
        category=row.category,
        version=row.version,
        status=row.status,
        rules=row.rules_json,
        content_digest=row.content_digest,
        source_references=row.source_references_json,
        effective_at=row.effective_at,
        expires_at=row.expires_at,
        created_by_user_id=row.created_by_user_id,
        reviewed_by_user_id=row.reviewed_by_user_id,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
    )


def _check_read(row: ListingComplianceCheck) -> ListingComplianceCheckRead:
    return ListingComplianceCheckRead(
        id=row.id,
        tenant_id=row.tenant_id,
        check_key=row.check_key,
        store_resource_id=row.store_resource_id,
        product_key=row.product_key,
        sku=row.sku,
        language=row.language,
        rule_set_id=row.rule_set_id,
        rule_version=row.rule_version,
        rule_digest=row.rule_digest,
        sku_fact_version=row.sku_fact_version,
        sku_facts=row.sku_facts_json,
        content=row.content_json,
        asset_version_ids=row.asset_version_ids_json,
        findings=row.findings_json,
        gate_status=row.gate_status,
        input_digest=row.input_digest,
        task_id=row.task_id,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


def _brief_read(row: CreativeBrief) -> CreativeBriefRead:
    return CreativeBriefRead(
        id=row.id,
        tenant_id=row.tenant_id,
        brief_key=row.brief_key,
        store_resource_id=row.store_resource_id,
        product_key=row.product_key,
        language=row.language,
        dimensions=row.dimensions_json,
        selling_points=row.selling_points_json,
        scenes=row.scenes_json,
        required_assets=row.required_assets_json,
        constraints=row.constraints_json,
        status=row.status,
        task_id=row.task_id,
        due_at=row.due_at,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _asset_read(row: CreativeAssetVersion) -> CreativeAssetVersionRead:
    return CreativeAssetVersionRead(
        id=row.id,
        tenant_id=row.tenant_id,
        asset_key=row.asset_key,
        version=row.version,
        brief_id=row.brief_id,
        parent_version_id=row.parent_version_id,
        store_resource_id=row.store_resource_id,
        product_key=row.product_key,
        asset_type=row.asset_type,
        file_reference=row.file_reference,
        file_digest=row.file_digest,
        provenance=row.provenance_json,
        generation_parameters=row.generation_parameters_json,
        checks=row.checks_json,
        required_human_approval=row.required_human_approval,
        status=row.status,
        creator_user_id=row.creator_user_id,
        reviewed_by_user_id=row.reviewed_by_user_id,
        review_note=row.review_note,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
    )


def _procurement_read(row: ProcurementRecommendation) -> ProcurementRecommendationRead:
    return ProcurementRecommendationRead(
        id=row.id,
        tenant_id=row.tenant_id,
        recommendation_key=row.recommendation_key,
        supplier_resource_id=row.supplier_resource_id,
        store_resource_id=row.store_resource_id,
        product_key=row.product_key,
        sku=row.sku,
        input_snapshot=row.input_snapshot_json,
        formula=row.formula,
        recommended_quantity=row.recommended_quantity,
        estimated_landed_cost=row.estimated_landed_cost,
        lead_time_days=row.lead_time_days,
        risk_level=row.risk_level,
        risk_reasons=row.risk_reasons_json,
        status=row.status,
        task_id=row.task_id,
        created_by_user_id=row.created_by_user_id,
        reviewed_by_user_id=row.reviewed_by_user_id,
        review_note=row.review_note,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
    )


def _launch_read(db: Session, row: ProductLaunchGate) -> ProductLaunchGateRead:
    approval = (
        db.get(HighRiskActionRequest, row.approval_request_id) if row.approval_request_id else None
    )
    status = row.status
    if approval and approval.status in {"approved", "rejected"}:
        status = approval.status
    return ProductLaunchGateRead(
        id=row.id,
        tenant_id=row.tenant_id,
        launch_key=row.launch_key,
        store_resource_id=row.store_resource_id,
        supplier_resource_id=row.supplier_resource_id,
        product_key=row.product_key,
        sku=row.sku,
        sku_fact_version=row.sku_fact_version,
        bom_version=row.bom_version,
        packaging_version=row.packaging_version,
        certification_ids=row.certification_ids_json,
        supplier_lead_time_confirmed=row.supplier_lead_time_confirmed,
        listing_check_id=row.listing_check_id,
        asset_version_ids=row.asset_version_ids_json,
        procurement_recommendation_id=row.procurement_recommendation_id,
        blockers=row.blockers_json,
        evidence_digest=row.evidence_digest,
        status=status,
        approval_request_id=row.approval_request_id,
        approval_status=approval.status if approval else None,
        task_id=row.task_id,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _quality_read(row: ProductQualityIssue) -> ProductQualityIssueRead:
    return ProductQualityIssueRead(
        id=row.id,
        tenant_id=row.tenant_id,
        source_case_id=row.source_case_id,
        store_resource_id=row.store_resource_id,
        product_key=row.product_key,
        category=row.category,
        root_cause=row.root_cause,
        task_ids=row.task_ids_json,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _validate_rule_shape(rules: dict[str, Any]) -> None:
    for key in (
        "banned_terms",
        "required_certifications",
        "required_labels",
        "intellectual_property_terms",
        "optimization_terms",
        "required_content_fields",
    ):
        if key in rules and not isinstance(rules[key], list):
            raise HTTPException(status_code=422, detail=f"{key} must be an array")
    if "restricted_terms" in rules and not isinstance(rules["restricted_terms"], list):
        raise HTTPException(status_code=422, detail="restricted_terms must be an array")
    if "max_title_chars" in rules:
        try:
            value = int(rules["max_title_chars"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail="max_title_chars must be an integer"
            ) from exc
        if not 1 <= value <= 1000:
            raise HTTPException(status_code=422, detail="max_title_chars is outside the safe range")


def _validate_content_shape(content: dict[str, Any]) -> None:
    for key in ("bullets", "keywords", "image_text"):
        if key in content and not isinstance(content[key], list):
            raise HTTPException(status_code=422, detail=f"{key} must be an array")
    for key in ("declared_facts", "translations", "attributes"):
        if key in content and not isinstance(content[key], dict):
            raise HTTPException(status_code=422, detail=f"{key} must be an object")


def _bounded_object(
    value: dict[str, Any],
    *,
    allowed_keys: set[str] | None = None,
    max_bytes: int,
) -> dict[str, Any]:
    if allowed_keys is not None:
        unknown = sorted(set(value) - allowed_keys)
        if unknown:
            raise HTTPException(status_code=422, detail=f"Unsupported fields: {', '.join(unknown)}")
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Payload must be valid JSON") from exc
    if len(encoded) > max_bytes:
        raise HTTPException(status_code=413, detail="Payload is too large")
    return json.loads(encoded.decode("utf-8"))


def _clean_strings(values: Iterable[str]) -> list[str]:
    result = [str(value).strip() for value in values if str(value).strip()]
    if not result:
        raise HTTPException(status_code=422, detail="At least one non-empty value is required")
    return list(dict.fromkeys(result))


def _flatten_content(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_content(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_content(item) for item in value)
    return str(value)


def _as_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _check_passed(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return value.get("passed") is True
    return False


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).casefold()


def _digest(value: Any) -> str:
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _require_tenant(tenant_id: str, user: User) -> None:
    if tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access is forbidden")


def _require_role(user: User, roles: set[str]) -> None:
    if not is_admin_user(user) and user.business_role not in roles:
        raise HTTPException(status_code=403, detail="Business role is not permitted")


def _require_manager(user: User) -> None:
    _require_role(user, _MANAGER_ROLES)
