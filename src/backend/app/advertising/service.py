from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

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
from app.business_resources.schema import HighRiskActionCreate
from app.business_resources.service import create_action_request
from app.config import get_settings
from app.db.database import set_tenant_context
from app.db.models import (
    AdvertisingEffectFollowUp,
    AdvertisingRecommendation,
    AuthorizationDecision,
    AutomationUsageLedger,
    BusinessActionExecution,
    BusinessResource,
    CommerceGovernanceEvent,
    ExecutionAutomationPolicy,
    HighRiskActionRequest,
    User,
    utc_now,
)
from app.security.authorization import authorize_business_resource
from app.security.permissions import is_admin_user
from app.work_tasks.service import create_linked_task

_AD_ROLES = {"advertising_inspection_specialist", "operations_supervisor"}
_VIEW_ROLES = _AD_ROLES | {
    "listing_compliance_specialist",
    "designer",
    "procurement_specialist",
}
_MANAGER_ROLES = {"operations_supervisor"}
_AD_ACTIONS = {
    "change_daily_budget",
    "change_ad_bid",
    "update_negative_keywords",
    "change_campaign_status",
}
_RISK_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def authorize_advertising_scope(
    db: Session,
    *,
    tenant_id: str,
    user: User,
    ad_account_resource_id: str | None = None,
    store_resource_id: str | None = None,
) -> None:
    """Validate the shared tenant, role, ad-account and store read boundary."""

    _require_tenant(tenant_id, user)
    _require_role(user, _AD_ROLES)
    set_tenant_context(db, tenant_id)
    if ad_account_resource_id:
        _authorized_resource(
            db,
            tenant_id=tenant_id,
            resource_id=ad_account_resource_id,
            resource_type="ad_account",
            user=user,
            action="READ",
        )
    if store_resource_id:
        _authorized_resource(
            db,
            tenant_id=tenant_id,
            resource_id=store_resource_id,
            resource_type="store",
            user=user,
            action="READ",
        )


def create_advertising_recommendation(
    db: Session, *, request: AdvertisingRecommendationCreate, user: User
) -> AdvertisingRecommendationRead:
    _require_tenant(request.tenant_id, user)
    _require_role(user, _AD_ROLES)
    set_tenant_context(db, request.tenant_id)
    existing = db.exec(
        select(AdvertisingRecommendation).where(
            AdvertisingRecommendation.tenant_id == request.tenant_id,
            AdvertisingRecommendation.recommendation_key == request.recommendation_key.strip(),
        )
    ).first()
    if existing:
        return _recommendation_read(db, existing)
    account = _authorized_resource(
        db,
        tenant_id=request.tenant_id,
        resource_id=request.ad_account_resource_id,
        resource_type="ad_account",
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
    metrics = _metrics(request)
    constraints = {
        "price": request.price,
        "profit_per_order": request.profit_per_order,
        "available_units": request.available_units,
        "inbound_units": request.inbound_units,
        "forecast_daily_sales": request.forecast_daily_sales,
        "reserve_stock_units": request.reserve_stock_units,
        "minimum_days_of_cover": request.minimum_days_of_cover,
        "promotion_active": request.promotion_active,
        "promotion_margin": request.promotion_margin,
        "minimum_promotion_margin": request.minimum_promotion_margin,
    }
    findings: list[dict] = []
    blockers: list[str] = []
    if request.profit_per_order <= 0:
        blockers.append("non_positive_unit_profit")
    if request.available_units <= request.reserve_stock_units:
        blockers.append("inventory_at_or_below_reserve")
    if metrics["days_of_cover"] < request.minimum_days_of_cover:
        blockers.append("inventory_cover_below_minimum")
    if request.promotion_active and (
        request.promotion_margin is None
        or request.promotion_margin < request.minimum_promotion_margin
    ):
        blockers.append("promotion_margin_constraint")
    for code in blockers:
        findings.append(
            {
                "type": "constraint",
                "code": code,
                "severity": "high",
                "gate": "block",
                "evidence": constraints,
            }
        )
    linked_tasks: list[str] = []
    if metrics["ctr"] < request.minimum_ctr:
        findings.append(
            {
                "type": "creative",
                "code": "ctr_below_minimum",
                "severity": "medium",
                "gate": "warn",
                "evidence": {"ctr": metrics["ctr"], "minimum": request.minimum_ctr},
            }
        )
        linked_tasks.append(
            _linked_issue_task(
                db,
                request=request,
                user=user,
                owner="designer",
                suffix="creative",
                title=f"优化广告素材 CTR · {request.campaign_id}",
                detail="检查主图、卖点层级、文案安全区与品牌一致性。",
            )
        )
    if metrics["conversion_rate"] < request.minimum_conversion_rate:
        findings.append(
            {
                "type": "listing",
                "code": "conversion_below_minimum",
                "severity": "medium",
                "gate": "warn",
                "evidence": {
                    "conversion_rate": metrics["conversion_rate"],
                    "minimum": request.minimum_conversion_rate,
                },
            }
        )
        linked_tasks.append(
            _linked_issue_task(
                db,
                request=request,
                user=user,
                owner="listing_compliance_specialist",
                suffix="listing",
                title=f"复盘广告落地 Listing 转化 · {request.campaign_id}",
                detail="核查搜索意图、Listing 事实、价格和转化障碍。",
            )
        )
    if metrics["days_of_cover"] < request.minimum_days_of_cover:
        linked_tasks.append(
            _linked_issue_task(
                db,
                request=request,
                user=user,
                owner="procurement_specialist",
                suffix="inventory",
                title=f"评估广告放量库存约束 · {request.product_key}",
                detail="广告动作被库存覆盖天数门禁阻断，请评估补货建议。",
            )
        )
    proposed_action = (
        None if request.proposed_action_type == "none" else request.proposed_action_type
    )
    action_payload = _bounded_payload(request.proposed_action_payload)
    if proposed_action:
        action_payload = {**action_payload, "campaign_id": request.campaign_id}
    risk = "high" if blockers else ("medium" if proposed_action else "low")
    status = "blocked" if blockers else "ready"
    recommendation = {
        "note": request.recommendation_note.strip(),
        "break_even_acos": metrics["break_even_acos"],
        "observed_acos": metrics["acos"],
        "proposed_action_type": proposed_action,
        "external_write_executed": False,
    }
    snapshot = {
        "metrics": metrics,
        "constraints": constraints,
        "findings": findings,
        "recommendation": recommendation,
        "action_payload": action_payload,
    }
    row = AdvertisingRecommendation(
        tenant_id=request.tenant_id,
        recommendation_key=request.recommendation_key.strip(),
        ad_account_resource_id=account.id,
        store_resource_id=request.store_resource_id,
        campaign_id=request.campaign_id.strip(),
        product_key=request.product_key.strip(),
        metric_snapshot_json=metrics,
        constraint_snapshot_json=constraints,
        findings_json=findings,
        recommendation_json=recommendation,
        proposed_action_type=proposed_action,
        proposed_action_payload_json=action_payload,
        risk_level=risk,
        status=status,
        input_digest=_digest(snapshot),
        task_id="pending",
        linked_task_ids_json=linked_tasks,
        created_by_user_id=user.id,
    )
    task, _ = create_linked_task(
        db,
        tenant_id=row.tenant_id,
        idempotency_key=f"advertising-recommendation:{row.recommendation_key}",
        source_type="advertising_recommendation",
        source_id=row.id,
        title=f"广告巡检建议 · {row.campaign_id}",
        description=request.recommendation_note,
        owner_business_role="advertising_inspection_specialist",
        assigned_by_user_id=user.id,
        assigned_by_business_role=user.business_role,
        priority="high" if blockers else "normal",
        risk_level=risk,
        scope={
            "ad_account_resource_id": account.id,
            "store_resource_id": request.store_resource_id,
        },
        input_data={"recommendation_id": row.id, "input_digest": row.input_digest},
    )
    row.task_id = task.id
    db.add(row)
    db.flush()
    _event(
        db,
        row.tenant_id,
        "advertising_recommendation",
        row.id,
        "analyzed",
        user,
        {
            "status": status,
            "constraint_blockers": blockers,
            "linked_task_ids": linked_tasks,
            "external_write_executed": False,
        },
    )
    db.commit()
    db.refresh(row)
    return _recommendation_read(db, row)


def request_advertising_action(
    db: Session,
    *,
    recommendation_id: str,
    request: AdvertisingActionRequest,
    user: User,
) -> AdvertisingRecommendationRead:
    _require_tenant(request.tenant_id, user)
    _require_role(user, _AD_ROLES)
    set_tenant_context(db, request.tenant_id)
    row = _recommendation(db, request.tenant_id, recommendation_id)
    if row.version != request.expected_version:
        raise HTTPException(
            status_code=409, detail="Recommendation changed; reload before submitting"
        )
    if row.status != "ready":
        raise HTTPException(
            status_code=409, detail="Only an unblocked recommendation can request an action"
        )
    if row.proposed_action_type not in _AD_ACTIONS:
        raise HTTPException(status_code=409, detail="Recommendation has no controlled action")
    payload = {
        **row.proposed_action_payload_json,
        "campaign_id": row.campaign_id,
        "advertising_recommendation_id": row.id,
        "recommendation_input_digest": row.input_digest,
        "risk_level": row.risk_level,
    }
    approval = create_action_request(
        db,
        request=HighRiskActionCreate(
            tenant_id=row.tenant_id,
            resource_id=row.ad_account_resource_id,
            action_type=row.proposed_action_type,
            summary=request.summary,
            payload=payload,
        ),
        user=user,
        commit=False,
    )
    row.status = "action_pending"
    row.approval_request_id = approval.id
    row.version += 1
    row.updated_at = utc_now()
    db.add(row)
    _event(
        db,
        row.tenant_id,
        "advertising_recommendation",
        row.id,
        "approval_requested",
        user,
        {"approval_request_id": approval.id, "input_digest": row.input_digest},
    )
    db.commit()
    db.refresh(row)
    return _recommendation_read(db, row)


def list_advertising_recommendations(
    db: Session, *, tenant_id: str, user: User
) -> list[AdvertisingRecommendationRead]:
    _require_tenant(tenant_id, user)
    _require_role(user, _VIEW_ROLES)
    set_tenant_context(db, tenant_id)
    rows = db.exec(
        select(AdvertisingRecommendation)
        .where(AdvertisingRecommendation.tenant_id == tenant_id)
        .order_by(AdvertisingRecommendation.created_at.desc())
        .limit(500)
    ).all()
    return [_recommendation_read(db, row) for row in rows]


def upsert_execution_automation_policy(
    db: Session, *, request: ExecutionAutomationPolicyUpsert, user: User
) -> ExecutionAutomationPolicyRead:
    _require_tenant(request.tenant_id, user)
    _require_manager(user)
    set_tenant_context(db, request.tenant_id)
    if not request.approval_required:
        raise HTTPException(
            status_code=422,
            detail="External ad actions cannot bypass independent approval",
        )
    if request.status == "active" and (
        request.rollout_percent <= 0
        or request.max_single_value <= 0
        or request.max_daily_value <= 0
    ):
        raise HTTPException(
            status_code=422,
            detail="Active policy requires positive rollout and quantitative limits",
        )
    _authorized_resource(
        db,
        tenant_id=request.tenant_id,
        resource_id=request.resource_id,
        resource_type="ad_account",
        user=user,
        action="REQUEST",
    )
    row = db.exec(
        select(ExecutionAutomationPolicy).where(
            ExecutionAutomationPolicy.tenant_id == request.tenant_id,
            ExecutionAutomationPolicy.resource_id == request.resource_id,
            ExecutionAutomationPolicy.action_type == request.action_type,
        )
    ).first()
    now = utc_now()
    if row:
        row.status = request.status
        row.rollout_percent = request.rollout_percent
        row.max_single_value = request.max_single_value
        row.max_daily_value = request.max_daily_value
        row.max_risk_level = request.max_risk_level
        row.approval_required = True
        row.kill_switch_engaged = request.kill_switch_engaged
        row.revision += 1
        row.updated_by_user_id = user.id
        row.updated_at = now
        event_type = "policy_updated"
    else:
        row = ExecutionAutomationPolicy(
            tenant_id=request.tenant_id,
            resource_id=request.resource_id,
            action_type=request.action_type,
            status=request.status,
            rollout_percent=request.rollout_percent,
            max_single_value=request.max_single_value,
            max_daily_value=request.max_daily_value,
            max_risk_level=request.max_risk_level,
            approval_required=True,
            kill_switch_engaged=request.kill_switch_engaged,
            created_by_user_id=user.id,
            updated_by_user_id=user.id,
            created_at=now,
            updated_at=now,
        )
        event_type = "policy_created"
    db.add(row)
    db.flush()
    _event(
        db,
        row.tenant_id,
        "execution_automation_policy",
        row.id,
        event_type,
        user,
        {
            "revision": row.revision,
            "status": row.status,
            "rollout_percent": row.rollout_percent,
            "max_single_value": row.max_single_value,
            "max_daily_value": row.max_daily_value,
            "kill_switch_engaged": row.kill_switch_engaged,
            "approval_required": True,
        },
    )
    db.commit()
    db.refresh(row)
    return _policy_read(row)


def list_execution_automation_policies(
    db: Session, *, tenant_id: str, user: User
) -> list[ExecutionAutomationPolicyRead]:
    _require_tenant(tenant_id, user)
    _require_role(user, _AD_ROLES)
    set_tenant_context(db, tenant_id)
    rows = db.exec(
        select(ExecutionAutomationPolicy)
        .where(ExecutionAutomationPolicy.tenant_id == tenant_id)
        .order_by(ExecutionAutomationPolicy.updated_at.desc())
    ).all()
    return [_policy_read(row) for row in rows]


def evaluate_policy_for_staging(db: Session, action: HighRiskActionRequest) -> dict[str, object]:
    """Apply an optional stricter rollout gate after approval, never before it."""

    if action.action_type not in _AD_ACTIONS:
        return {"allowed": True, "reason": "not_an_ad_automation_action"}
    policy = db.exec(
        select(ExecutionAutomationPolicy).where(
            ExecutionAutomationPolicy.tenant_id == action.tenant_id,
            ExecutionAutomationPolicy.resource_id == action.resource_id,
            ExecutionAutomationPolicy.action_type == action.action_type,
        )
    ).first()
    if not policy:
        return {"allowed": True, "reason": "no_additional_automation_policy"}
    existing = db.exec(
        select(AutomationUsageLedger).where(
            AutomationUsageLedger.tenant_id == action.tenant_id,
            AutomationUsageLedger.request_id == action.id,
        )
    ).first()
    if existing:
        return {
            "allowed": existing.decision == "allowed",
            "reason": existing.reason,
            "policy_id": existing.policy_id,
            "policy_revision": existing.policy_revision,
        }
    value = _quantitative_value(action)
    risk = str(action.payload_json.get("risk_level") or "medium")
    cohort_key = ":".join(
        (
            action.tenant_id,
            action.resource_id,
            str(action.payload_json.get("campaign_id") or action.id),
            action.action_type,
        )
    )
    bucket = int(hashlib.sha256(cohort_key.encode()).hexdigest()[:8], 16) % 100
    usage_date = utc_now().date().isoformat()
    prior = db.exec(
        select(AutomationUsageLedger).where(
            AutomationUsageLedger.tenant_id == action.tenant_id,
            AutomationUsageLedger.policy_id == policy.id,
            AutomationUsageLedger.usage_date == usage_date,
            AutomationUsageLedger.decision == "allowed",
        )
    ).all()
    daily_total = sum(item.quantitative_value for item in prior)
    reason = "allowed"
    allowed = True
    if action.status != "approved" or not policy.approval_required:
        allowed, reason = False, "independent_approval_required"
    elif policy.status != "active":
        allowed, reason = False, "automation_policy_paused"
    elif policy.kill_switch_engaged:
        allowed, reason = False, "kill_switch_engaged"
    elif bucket >= policy.rollout_percent:
        allowed, reason = False, "outside_rollout_cohort"
    elif _RISK_RANK.get(risk, 99) > _RISK_RANK.get(policy.max_risk_level, 0):
        allowed, reason = False, "risk_above_policy_limit"
    elif value <= 0 or value > policy.max_single_value:
        allowed, reason = False, "single_action_limit_exceeded"
    elif daily_total + value > policy.max_daily_value:
        allowed, reason = False, "daily_action_limit_exceeded"
    ledger = AutomationUsageLedger(
        tenant_id=action.tenant_id,
        policy_id=policy.id,
        policy_revision=policy.revision,
        request_id=action.id,
        action_type=action.action_type,
        cohort_bucket=bucket,
        quantitative_value=value,
        usage_date=usage_date,
        decision="allowed" if allowed else "blocked",
        reason=reason,
    )
    db.add(ledger)
    db.flush()
    return {
        "allowed": allowed,
        "reason": reason,
        "policy_id": policy.id,
        "policy_revision": policy.revision,
        "cohort_bucket": bucket,
        "quantitative_value": value,
        "daily_total_before": daily_total,
    }


def schedule_effect_followups_for_execution(
    db: Session, execution: BusinessActionExecution
) -> list[AdvertisingEffectFollowUp]:
    if execution.action_type not in _AD_ACTIONS or execution.status != "succeeded":
        return []
    action = db.exec(
        select(HighRiskActionRequest).where(
            HighRiskActionRequest.tenant_id == execution.tenant_id,
            HighRiskActionRequest.id == execution.request_id,
        )
    ).one()
    recommendation_id = str(action.payload_json.get("advertising_recommendation_id") or "") or None
    recommendation = (
        db.exec(
            select(AdvertisingRecommendation).where(
                AdvertisingRecommendation.tenant_id == execution.tenant_id,
                AdvertisingRecommendation.id == recommendation_id,
            )
        ).first()
        if recommendation_id
        else None
    )
    baseline = dict(recommendation.metric_snapshot_json) if recommendation else {}
    completed_at = execution.completed_at or utc_now()
    rows: list[AdvertisingEffectFollowUp] = []
    for days in (7, 14, 30):
        existing = db.exec(
            select(AdvertisingEffectFollowUp).where(
                AdvertisingEffectFollowUp.tenant_id == execution.tenant_id,
                AdvertisingEffectFollowUp.execution_id == execution.id,
                AdvertisingEffectFollowUp.horizon_days == days,
            )
        ).first()
        if existing:
            rows.append(existing)
            continue
        row = AdvertisingEffectFollowUp(
            tenant_id=execution.tenant_id,
            execution_id=execution.id,
            request_id=execution.request_id,
            recommendation_id=recommendation_id,
            horizon_days=days,
            baseline_json=baseline,
            task_id="pending",
            due_at=completed_at + timedelta(days=days),
        )
        task, _ = create_linked_task(
            db,
            tenant_id=row.tenant_id,
            idempotency_key=f"ad-effect:{execution.id}:{days}",
            source_type="advertising_effect_follow_up",
            source_id=row.id,
            title=f"广告动作 {days} 天效果复盘",
            description="比较执行前基线与当前 ACoS、ROAS、CTR、转化率、利润和库存覆盖。",
            owner_business_role="advertising_inspection_specialist",
            assigned_by_user_id=action.requester_user_id,
            assigned_by_business_role=action.requester_business_role,
            priority="normal",
            risk_level="medium",
            due_at=row.due_at,
            scope={"ad_account_resource_id": execution.resource_id},
            input_data={
                "execution_id": execution.id,
                "request_id": execution.request_id,
                "horizon_days": days,
                "baseline": baseline,
            },
        )
        row.task_id = task.id
        db.add(row)
        db.flush()
        _system_event(
            db,
            tenant_id=row.tenant_id,
            aggregate_type="advertising_effect_follow_up",
            aggregate_id=row.id,
            event_type="scheduled_after_execution",
            detail={
                "execution_id": execution.id,
                "horizon_days": days,
                "due_at": row.due_at.isoformat(),
                "task_id": task.id,
            },
        )
        rows.append(row)
    return rows


def list_advertising_effect_followups(
    db: Session, *, tenant_id: str, user: User
) -> list[AdvertisingEffectFollowUpRead]:
    _require_tenant(tenant_id, user)
    _require_role(user, _AD_ROLES)
    set_tenant_context(db, tenant_id)
    rows = db.exec(
        select(AdvertisingEffectFollowUp)
        .where(AdvertisingEffectFollowUp.tenant_id == tenant_id)
        .order_by(AdvertisingEffectFollowUp.due_at)
    ).all()
    return [_effect_read(row) for row in rows]


def list_automation_usage(db: Session, *, tenant_id: str, user: User) -> list[AutomationUsageRead]:
    _require_tenant(tenant_id, user)
    _require_manager(user)
    set_tenant_context(db, tenant_id)
    rows = db.exec(
        select(AutomationUsageLedger)
        .where(AutomationUsageLedger.tenant_id == tenant_id)
        .order_by(AutomationUsageLedger.created_at.desc())
        .limit(500)
    ).all()
    return [_usage_read(row) for row in rows]


def advertising_overview(db: Session, *, tenant_id: str, user: User) -> AdvertisingOverview:
    _require_tenant(tenant_id, user)
    _require_role(user, _VIEW_ROLES)
    set_tenant_context(db, tenant_id)
    recommendations = db.exec(
        select(AdvertisingRecommendation).where(AdvertisingRecommendation.tenant_id == tenant_id)
    ).all()
    effects = db.exec(
        select(AdvertisingEffectFollowUp).where(AdvertisingEffectFollowUp.tenant_id == tenant_id)
    ).all()
    policies = db.exec(
        select(ExecutionAutomationPolicy).where(ExecutionAutomationPolicy.tenant_id == tenant_id)
    ).all()
    pending_approval_ids = set(
        db.exec(
            select(HighRiskActionRequest.id).where(
                HighRiskActionRequest.tenant_id == tenant_id,
                HighRiskActionRequest.status == "pending",
            )
        ).all()
    )
    return AdvertisingOverview(
        recommendations_ready=sum(item.status == "ready" for item in recommendations),
        recommendations_blocked=sum(item.status == "blocked" for item in recommendations),
        actions_waiting_approval=sum(
            item.approval_request_id in pending_approval_ids for item in recommendations
        ),
        effectiveness_reviews_pending=sum(item.status == "pending" for item in effects),
        automation_policies_active=sum(item.status == "active" for item in policies),
        kill_switches_engaged=sum(item.kill_switch_engaged for item in policies),
    )


def _metrics(request: AdvertisingRecommendationCreate) -> dict[str, float | int]:
    ctr = request.clicks / request.impressions if request.impressions else 0.0
    conversion = request.orders / request.clicks if request.clicks else 0.0
    acos = request.spend / request.attributed_sales if request.attributed_sales else 0.0
    roas = request.attributed_sales / request.spend if request.spend else 0.0
    margin = request.profit_per_order / request.price
    sellable = max(0, request.available_units - request.reserve_stock_units)
    days_cover = sellable / request.forecast_daily_sales
    return {
        "spend": request.spend,
        "attributed_sales": request.attributed_sales,
        "impressions": request.impressions,
        "clicks": request.clicks,
        "orders": request.orders,
        "ctr": round(ctr, 6),
        "conversion_rate": round(conversion, 6),
        "acos": round(acos, 6),
        "roas": round(roas, 6),
        "break_even_acos": round(max(0.0, margin), 6),
        "days_of_cover": round(days_cover, 2),
    }


def _linked_issue_task(
    db: Session,
    *,
    request: AdvertisingRecommendationCreate,
    user: User,
    owner: str,
    suffix: str,
    title: str,
    detail: str,
) -> str:
    task, _ = create_linked_task(
        db,
        tenant_id=request.tenant_id,
        idempotency_key=f"ad-inspection:{request.recommendation_key}:{suffix}",
        source_type="advertising_inspection_issue",
        source_id=request.recommendation_key,
        title=title,
        description=detail,
        owner_business_role=owner,
        assigned_by_user_id=user.id,
        assigned_by_business_role=user.business_role,
        priority="high" if suffix == "inventory" else "normal",
        risk_level="high" if suffix == "inventory" else "medium",
        scope={
            "ad_account_resource_id": request.ad_account_resource_id,
            "store_resource_id": request.store_resource_id,
        },
        input_data={
            "recommendation_key": request.recommendation_key,
            "campaign_id": request.campaign_id,
            "product_key": request.product_key,
        },
    )
    return task.id


def _recommendation(
    db: Session, tenant_id: str, recommendation_id: str
) -> AdvertisingRecommendation:
    row = db.exec(
        select(AdvertisingRecommendation).where(
            AdvertisingRecommendation.tenant_id == tenant_id,
            AdvertisingRecommendation.id == recommendation_id,
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Advertising recommendation not found")
    return row


def _recommendation_read(
    db: Session, row: AdvertisingRecommendation
) -> AdvertisingRecommendationRead:
    approval = (
        db.get(HighRiskActionRequest, row.approval_request_id) if row.approval_request_id else None
    )
    status = row.status
    if approval and approval.status == "approved":
        status = "action_approved"
    elif approval and approval.status == "rejected":
        status = "action_rejected"
    return AdvertisingRecommendationRead(
        id=row.id,
        tenant_id=row.tenant_id,
        recommendation_key=row.recommendation_key,
        ad_account_resource_id=row.ad_account_resource_id,
        store_resource_id=row.store_resource_id,
        campaign_id=row.campaign_id,
        product_key=row.product_key,
        metrics=row.metric_snapshot_json,
        constraints=row.constraint_snapshot_json,
        findings=row.findings_json,
        recommendation=row.recommendation_json,
        proposed_action_type=row.proposed_action_type,
        proposed_action_payload=row.proposed_action_payload_json,
        risk_level=row.risk_level,
        status=status,
        input_digest=row.input_digest,
        task_id=row.task_id,
        linked_task_ids=row.linked_task_ids_json,
        approval_request_id=row.approval_request_id,
        approval_status=approval.status if approval else None,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _policy_read(row: ExecutionAutomationPolicy) -> ExecutionAutomationPolicyRead:
    return ExecutionAutomationPolicyRead(
        id=row.id,
        tenant_id=row.tenant_id,
        resource_id=row.resource_id,
        action_type=row.action_type,
        status=row.status,
        rollout_percent=row.rollout_percent,
        max_single_value=row.max_single_value,
        max_daily_value=row.max_daily_value,
        max_risk_level=row.max_risk_level,
        approval_required=row.approval_required,
        kill_switch_engaged=row.kill_switch_engaged,
        revision=row.revision,
        created_by_user_id=row.created_by_user_id,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _effect_read(row: AdvertisingEffectFollowUp) -> AdvertisingEffectFollowUpRead:
    return AdvertisingEffectFollowUpRead(
        id=row.id,
        execution_id=row.execution_id,
        request_id=row.request_id,
        recommendation_id=row.recommendation_id,
        horizon_days=row.horizon_days,
        baseline=row.baseline_json,
        task_id=row.task_id,
        status=row.status,
        due_at=row.due_at,
        created_at=row.created_at,
    )


def _usage_read(row: AutomationUsageLedger) -> AutomationUsageRead:
    return AutomationUsageRead(
        id=row.id,
        policy_id=row.policy_id,
        policy_revision=row.policy_revision,
        request_id=row.request_id,
        action_type=row.action_type,
        cohort_bucket=row.cohort_bucket,
        quantitative_value=row.quantitative_value,
        usage_date=row.usage_date,
        decision=row.decision,
        reason=row.reason,
        created_at=row.created_at,
    )


def _quantitative_value(action: HighRiskActionRequest) -> float:
    payload = action.payload_json
    if action.action_type == "change_daily_budget":
        return float(payload.get("daily_budget") or 0)
    if action.action_type == "change_ad_bid":
        return float(payload.get("bid") or 0)
    if action.action_type == "update_negative_keywords":
        keywords = payload.get("keywords")
        return float(len(keywords)) if isinstance(keywords, list) else 0.0
    if action.action_type == "change_campaign_status":
        return 1.0
    return 0.0


def _bounded_payload(value: dict) -> dict:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Action payload must be valid JSON") from exc
    if len(encoded) > 32 * 1024:
        raise HTTPException(status_code=413, detail="Action payload exceeds 32KB")
    return json.loads(encoded.decode())


def _digest(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


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
            request_id=f"advertising_{uuid4().hex}",
        )
    )
    db.flush()
    if not result.allowed:
        db.commit()
        raise HTTPException(status_code=404, detail="Business resource not found")
    return row


def _event(
    db: Session,
    tenant_id: str,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    user: User,
    detail: dict,
) -> None:
    db.add(
        CommerceGovernanceEvent(
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            actor_id=user.id,
            actor_business_role=user.business_role,
            detail_json=detail,
        )
    )


def _system_event(
    db: Session,
    *,
    tenant_id: str,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    detail: dict,
) -> None:
    db.add(
        CommerceGovernanceEvent(
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            actor_type="system",
            actor_id="system",
            actor_business_role="system",
            detail_json=detail,
        )
    )


def _require_tenant(tenant_id: str, user: User) -> None:
    if tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access is forbidden")


def _require_role(user: User, roles: set[str]) -> None:
    if not is_admin_user(user) and user.business_role not in roles:
        raise HTTPException(status_code=403, detail="Business role is not permitted")


def _require_manager(user: User) -> None:
    _require_role(user, _MANAGER_ROLES)
