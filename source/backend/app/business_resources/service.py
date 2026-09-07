from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.business_execution.service import (
    add_execution_event,
    execution_for_request,
    stage_approved_execution,
)
from app.business_resources.integrity import (
    action_content_digest,
    approval_integrity_error,
    resource_context_digest,
)
from app.business_resources.schema import (
    BusinessResourceCreate,
    BusinessResourceRead,
    BusinessResourceUpdate,
    HighRiskActionCreate,
    HighRiskActionEventRead,
    HighRiskActionRead,
    ResourceScopeInput,
)
from app.config import get_settings
from app.db.models import (
    AuthorizationDecision,
    BusinessActionExecution,
    BusinessResource,
    BusinessResourceScope,
    HighRiskActionEvent,
    HighRiskActionRequest,
    User,
    utc_now,
)
from app.security.authorization import authorize_business_resource
from app.security.permissions import is_admin_user

APPROVER_ROLES = {"operations_supervisor"}
RESOURCE_ROLE_DEFAULTS: dict[str, tuple[str, ...]] = {
    "store": (
        "after_sales_specialist",
        "listing_compliance_specialist",
        "logistics_exception_specialist",
        "advertising_inspection_specialist",
        "designer",
    ),
    "carrier": ("logistics_exception_specialist",),
    "ad_account": ("advertising_inspection_specialist", "designer"),
    "supplier": ("procurement_specialist",),
    "creator_account": ("tiktok_bd_specialist", "tiktok_tap_manager"),
    "partner_account": ("tiktok_bd_specialist", "tiktok_tap_manager"),
    "social_account": ("tiktok_content_specialist", "tiktok_live_operator"),
    "live_room": ("tiktok_live_operator", "tiktok_content_specialist"),
}
KNOWN_RESOURCE_ROLES = {role for roles in RESOURCE_ROLE_DEFAULTS.values() for role in roles}

ROLE_ACTIONS: dict[str, set[str]] = {
    "after_sales_specialist": {"issue_refund"},
    "listing_compliance_specialist": {"publish_listing"},
    "logistics_exception_specialist": {"change_routing_rule"},
    "advertising_inspection_specialist": {
        "change_daily_budget",
        "change_ad_bid",
        "update_negative_keywords",
        "change_campaign_status",
    },
    "designer": {"publish_creative_asset"},
    "procurement_specialist": {"issue_purchase_order"},
    "operations_supervisor": {
        "issue_refund",
        "publish_listing",
        "change_routing_rule",
        "change_daily_budget",
        "change_ad_bid",
        "update_negative_keywords",
        "change_campaign_status",
        "publish_creative_asset",
        "issue_purchase_order",
    },
}

ACTION_RESOURCE_TYPES: dict[str, set[str]] = {
    "issue_refund": {"store"},
    "publish_listing": {"store"},
    "change_routing_rule": {"carrier"},
    "change_daily_budget": {"ad_account"},
    "change_ad_bid": {"ad_account"},
    "update_negative_keywords": {"ad_account"},
    "change_campaign_status": {"ad_account"},
    "publish_creative_asset": {"store", "ad_account"},
    "issue_purchase_order": {"supplier"},
}

ACTION_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "issue_refund": ("order_id", "amount", "currency"),
    "publish_listing": ("listing_id", "marketplace", "product_type", "attributes"),
    "change_routing_rule": ("route_policy",),
    "change_daily_budget": ("campaign_id", "daily_budget", "currency"),
    "change_ad_bid": ("campaign_id", "target_id", "bid", "currency"),
    "update_negative_keywords": ("campaign_id", "keywords", "match_type"),
    "change_campaign_status": ("campaign_id", "status"),
    "publish_creative_asset": ("asset_id", "channel"),
    "issue_purchase_order": ("po_number", "amount", "currency"),
}

_SECRET_KEY_PARTS = ("password", "secret", "token", "api_key", "private_key", "credential")
_HIGH_RISK_METADATA_KEYS = {
    "daily_budget",
    "route_policy",
    "purchase_order",
    "publish_status",
    "refund_amount",
}
_MAX_METADATA_BYTES = 16 * 1024
_MAX_ACTION_PAYLOAD_BYTES = 32 * 1024


def is_approval_manager(user: User) -> bool:
    return is_admin_user(user) or user.business_role in APPROVER_ROLES


def list_resources(
    db: Session,
    *,
    tenant_id: str,
    user: User,
    resource_type: str | None = None,
) -> list[BusinessResourceRead]:
    _ensure_tenant(tenant_id, user)
    if is_approval_manager(user):
        statement = select(BusinessResource).where(BusinessResource.tenant_id == tenant_id)
        if resource_type:
            statement = statement.where(BusinessResource.resource_type == resource_type)
        rows = db.exec(
            statement.order_by(BusinessResource.resource_type, BusinessResource.name)
        ).all()
        return [_resource_read(db, row, "operator") for row in rows]

    statement = (
        select(BusinessResource, BusinessResourceScope)
        .join(BusinessResourceScope, BusinessResourceScope.resource_id == BusinessResource.id)
        .where(
            BusinessResource.tenant_id == tenant_id,
            BusinessResourceScope.tenant_id == tenant_id,
            BusinessResourceScope.business_role == user.business_role,
        )
    )
    if resource_type:
        statement = statement.where(BusinessResource.resource_type == resource_type)
    rows = db.exec(statement.order_by(BusinessResource.resource_type, BusinessResource.name)).all()
    return [_resource_read(db, resource, scope.access_level) for resource, scope in rows]


def create_resource(
    db: Session,
    *,
    request: BusinessResourceCreate,
    user: User,
) -> BusinessResourceRead:
    _require_resource_manager(user)
    _ensure_tenant(request.tenant_id, user)
    metadata = _validated_metadata(request.metadata)
    row = BusinessResource(
        tenant_id=request.tenant_id,
        resource_type=request.resource_type,
        code=request.code.strip(),
        name=request.name.strip(),
        created_by_user_id=user.id,
        metadata_json=metadata,
    )
    db.add(row)
    db.flush()
    scopes = request.scopes or [
        ResourceScopeInput(business_role=role, access_level="operator")
        for role in RESOURCE_ROLE_DEFAULTS[request.resource_type]
    ]
    _replace_scopes(db, row, scopes)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Business resource code already exists"
        ) from exc
    db.refresh(row)
    return _resource_read(db, row, "operator")


def update_resource(
    db: Session,
    *,
    resource_id: str,
    request: BusinessResourceUpdate,
    user: User,
) -> BusinessResourceRead:
    _require_resource_manager(user)
    _ensure_tenant(request.tenant_id, user)
    row = _resource(db, request.tenant_id, resource_id, for_update=True)
    _reject_update_during_uncertain_execution(db, row)
    previous_digest = resource_context_digest(db, row)
    if request.name is not None:
        row.name = request.name.strip()
    if request.status is not None:
        row.status = request.status
    if request.metadata is not None:
        row.metadata_json = _validated_metadata(request.metadata)
    if request.scopes is not None:
        _replace_scopes(db, row, request.scopes)
    db.flush()
    next_digest = resource_context_digest(db, row)
    if next_digest != previous_digest:
        row.revision += 1
        _invalidate_open_actions_for_resource(
            db,
            row,
            user,
            reason="business_resource_context_changed",
            previous_digest=previous_digest,
            next_digest=next_digest,
        )
    row.updated_at = utc_now()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _resource_read(db, row, "operator")


def create_action_request(
    db: Session,
    *,
    request: HighRiskActionCreate,
    user: User,
    commit: bool = True,
) -> HighRiskActionRead:
    _ensure_tenant(request.tenant_id, user)
    row = _resource(db, request.tenant_id, request.resource_id)
    if row.status != "active":
        raise HTTPException(
            status_code=409, detail="Inactive business resources cannot be actioned"
        )
    _require_resource_operator(db, row, user)
    _validate_action(row, request, user)
    action = HighRiskActionRequest(
        tenant_id=request.tenant_id,
        resource_id=row.id,
        resource_type=row.resource_type,
        resource_name=row.name,
        action_type=request.action_type,
        summary=request.summary.strip(),
        payload_json=request.payload,
        requester_user_id=user.id,
        requester_business_role=user.business_role,
    )
    action.content_digest = action_content_digest(action)
    action.resource_snapshot_digest = resource_context_digest(db, row)
    db.add(action)
    db.flush()
    _add_event(
        db,
        action,
        "requested",
        user,
        {"summary": action.summary, "action_type": action.action_type},
    )
    if commit:
        db.commit()
        db.refresh(action)
    return _action_read(db, action)


def list_action_requests(
    db: Session,
    *,
    tenant_id: str,
    user: User,
    status: str | None = None,
    approval_queue: bool = False,
) -> list[HighRiskActionRead]:
    _ensure_tenant(tenant_id, user)
    if approval_queue and not is_approval_manager(user):
        raise HTTPException(
            status_code=403, detail="Only operations supervisors can review approvals"
        )
    statement = select(HighRiskActionRequest).where(HighRiskActionRequest.tenant_id == tenant_id)
    if not approval_queue and not is_approval_manager(user):
        statement = statement.where(HighRiskActionRequest.requester_user_id == user.id)
    if status:
        statement = statement.where(HighRiskActionRequest.status == status)
    rows = db.exec(statement.order_by(HighRiskActionRequest.requested_at.desc()).limit(500)).all()
    return [_action_read(db, row) for row in rows]


def decide_action_request(
    db: Session,
    *,
    tenant_id: str,
    request_id: str,
    decision: str,
    reason: str,
    user: User,
) -> HighRiskActionRead:
    _ensure_tenant(tenant_id, user)
    if not is_approval_manager(user):
        raise HTTPException(
            status_code=403, detail="Only operations supervisors can decide approvals"
        )
    statement = select(HighRiskActionRequest).where(
        HighRiskActionRequest.tenant_id == tenant_id,
        HighRiskActionRequest.id == request_id,
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    row = db.exec(statement).first()
    if not row:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if row.requester_user_id == user.id:
        raise HTTPException(
            status_code=403, detail="Requester cannot approve or reject their own request"
        )
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Approval request has already been decided")
    if decision not in {"approved", "rejected"}:
        raise ValueError("decision must be approved or rejected")
    resource = _resource(db, tenant_id, row.resource_id)
    integrity_error = approval_integrity_error(db, row, resource)
    if integrity_error:
        _invalidate_action(
            db,
            row,
            actor=user,
            reason=integrity_error,
            detail={"phase": "approval_decision"},
        )
        db.commit()
        raise HTTPException(
            status_code=409,
            detail="Approval content or resource context changed; submit a new request",
        )
    row.status = decision
    row.decided_by_user_id = user.id
    row.decision_reason = reason.strip()
    row.decided_at = utc_now()
    row.updated_at = utc_now()
    db.add(row)
    _add_event(db, row, decision, user, {"reason": row.decision_reason})
    if decision == "approved":
        stage_approved_execution(db, row)
    db.commit()
    db.refresh(row)
    return _action_read(db, row)


def cancel_action_request(
    db: Session,
    *,
    tenant_id: str,
    request_id: str,
    user: User,
) -> HighRiskActionRead:
    _ensure_tenant(tenant_id, user)
    row = db.exec(
        select(HighRiskActionRequest).where(
            HighRiskActionRequest.tenant_id == tenant_id,
            HighRiskActionRequest.id == request_id,
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if row.requester_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the requester can cancel this request")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending requests can be cancelled")
    row.status = "cancelled"
    row.updated_at = utc_now()
    db.add(row)
    _add_event(db, row, "cancelled", user, {})
    db.commit()
    db.refresh(row)
    return _action_read(db, row)


def _resource_read(db: Session, row: BusinessResource, access_level: str) -> BusinessResourceRead:
    scopes = db.exec(
        select(BusinessResourceScope)
        .where(
            BusinessResourceScope.tenant_id == row.tenant_id,
            BusinessResourceScope.resource_id == row.id,
        )
        .order_by(BusinessResourceScope.business_role)
    ).all()
    return BusinessResourceRead(
        id=row.id,
        tenant_id=row.tenant_id,
        resource_type=row.resource_type,
        code=row.code,
        name=row.name,
        status=row.status,
        revision=row.revision,
        access_level=access_level,
        metadata=dict(row.metadata_json or {}),
        scopes=[
            ResourceScopeInput(business_role=item.business_role, access_level=item.access_level)
            for item in scopes
        ],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _action_read(db: Session, row: HighRiskActionRequest) -> HighRiskActionRead:
    events = db.exec(
        select(HighRiskActionEvent)
        .where(
            HighRiskActionEvent.tenant_id == row.tenant_id,
            HighRiskActionEvent.request_id == row.id,
        )
        .order_by(HighRiskActionEvent.occurred_at)
    ).all()
    return HighRiskActionRead(
        id=row.id,
        tenant_id=row.tenant_id,
        resource_id=row.resource_id,
        resource_type=row.resource_type,
        resource_name=row.resource_name,
        action_type=row.action_type,
        summary=row.summary,
        payload=dict(row.payload_json or {}),
        status=row.status,
        content_digest=row.content_digest,
        resource_snapshot_digest=row.resource_snapshot_digest,
        requester_user_id=row.requester_user_id,
        requester_business_role=row.requester_business_role,
        decided_by_user_id=row.decided_by_user_id,
        decision_reason=row.decision_reason,
        requested_at=row.requested_at,
        decided_at=row.decided_at,
        invalidated_at=row.invalidated_at,
        invalidation_reason=row.invalidation_reason,
        execution=execution_for_request(
            db,
            tenant_id=row.tenant_id,
            request_id=row.id,
        ),
        events=[
            HighRiskActionEventRead(
                event_type=event.event_type,
                actor_user_id=event.actor_user_id,
                actor_business_role=event.actor_business_role,
                detail=dict(event.detail_json or {}),
                occurred_at=event.occurred_at,
            )
            for event in events
        ],
    )


def _resource(
    db: Session,
    tenant_id: str,
    resource_id: str,
    *,
    for_update: bool = False,
) -> BusinessResource:
    statement = select(BusinessResource).where(
        BusinessResource.tenant_id == tenant_id,
        BusinessResource.id == resource_id,
    )
    if for_update and db.bind is not None and db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    row = db.exec(statement).first()
    if not row:
        raise HTTPException(status_code=404, detail="Business resource not found")
    return row


def _replace_scopes(
    db: Session,
    resource: BusinessResource,
    scopes: Iterable[ResourceScopeInput],
) -> None:
    normalized: dict[str, str] = {}
    for scope in scopes:
        if scope.business_role not in KNOWN_RESOURCE_ROLES:
            raise HTTPException(
                status_code=400, detail=f"Unsupported business role: {scope.business_role}"
            )
        normalized[scope.business_role] = scope.access_level
    existing = db.exec(
        select(BusinessResourceScope).where(
            BusinessResourceScope.tenant_id == resource.tenant_id,
            BusinessResourceScope.resource_id == resource.id,
        )
    ).all()
    for item in existing:
        db.delete(item)
    for role, access_level in sorted(normalized.items()):
        db.add(
            BusinessResourceScope(
                tenant_id=resource.tenant_id,
                resource_id=resource.id,
                business_role=role,
                access_level=access_level,
            )
        )


def _require_resource_operator(db: Session, resource: BusinessResource, user: User) -> None:
    result = authorize_business_resource(
        get_settings(),
        db=db,
        user=user,
        resource=resource,
        action="REQUEST",
    )
    db.add(
        AuthorizationDecision(
            tenant_id=user.tenant_id,
            subject_id=user.id,
            subject_type="human",
            role=result.role,
            department_id=user.business_role or result.role,
            store_id=resource.code if resource.resource_type == "store" else "",
            resource_type=resource.resource_type,
            object=f"business_resource:{resource.id}",
            action="REQUEST",
            effect="allow" if result.allowed else "deny",
            reason=result.reason,
            policy_version=result.policy_version,
            request_id=f"scope_{uuid4().hex}",
        )
    )
    if not result.allowed:
        db.commit()
        raise HTTPException(status_code=404, detail="Business resource not found")


def _validate_action(
    resource: BusinessResource,
    request: HighRiskActionCreate,
    user: User,
) -> None:
    allowed = ROLE_ACTIONS.get(user.business_role, set())
    if is_admin_user(user):
        allowed = set(ACTION_RESOURCE_TYPES)
    if request.action_type not in allowed:
        raise HTTPException(
            status_code=403, detail="Current business role cannot request this action"
        )
    if resource.resource_type not in ACTION_RESOURCE_TYPES[request.action_type]:
        raise HTTPException(
            status_code=400, detail="Action does not match the selected resource type"
        )
    if (
        len(json.dumps(request.payload, ensure_ascii=False).encode("utf-8"))
        > _MAX_ACTION_PAYLOAD_BYTES
    ):
        raise HTTPException(status_code=413, detail="Action payload exceeds 32KB")
    _reject_secret_material(request.payload)
    missing = []
    for key in ACTION_REQUIRED_FIELDS[request.action_type]:
        value = request.payload.get(key)
        if value is None or value == "":
            missing.append(key)
    if missing:
        raise HTTPException(
            status_code=422, detail=f"Missing action payload fields: {', '.join(missing)}"
        )
    if request.action_type in {
        "issue_refund",
        "change_daily_budget",
        "change_ad_bid",
        "issue_purchase_order",
    }:
        amount_key = {
            "change_daily_budget": "daily_budget",
            "change_ad_bid": "bid",
        }.get(request.action_type, "amount")
        value = request.payload.get(amount_key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise HTTPException(status_code=422, detail=f"{amount_key} must be a positive number")
    if request.action_type == "update_negative_keywords":
        keywords = request.payload.get("keywords")
        if not isinstance(keywords, list) or not keywords or len(keywords) > 500:
            raise HTTPException(status_code=422, detail="keywords must contain 1 to 500 terms")
    if request.action_type == "change_campaign_status" and request.payload.get("status") not in {
        "enabled",
        "paused",
    }:
        raise HTTPException(status_code=422, detail="campaign status must be enabled or paused")


def _validated_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(metadata, ensure_ascii=False).encode("utf-8")) > _MAX_METADATA_BYTES:
        raise HTTPException(status_code=413, detail="Business resource metadata exceeds 16KB")
    _reject_secret_material(metadata)
    forbidden = sorted(_HIGH_RISK_METADATA_KEYS.intersection(metadata))
    if forbidden:
        raise HTTPException(
            status_code=400,
            detail=f"High-risk fields require an approval request: {', '.join(forbidden)}",
        )
    return dict(metadata)


def _reject_secret_material(payload: Any) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized = str(key).lower()
            if any(part in normalized for part in _SECRET_KEY_PARTS):
                raise HTTPException(
                    status_code=400, detail="Secrets must not be stored in business resources"
                )
            _reject_secret_material(value)
    elif isinstance(payload, list):
        for value in payload:
            _reject_secret_material(value)


def _add_event(
    db: Session,
    request: HighRiskActionRequest,
    event_type: str,
    user: User,
    detail: dict[str, Any],
) -> None:
    db.add(
        HighRiskActionEvent(
            tenant_id=request.tenant_id,
            request_id=request.id,
            event_type=event_type,
            actor_user_id=user.id,
            actor_business_role=user.business_role,
            detail_json=detail,
        )
    )


def _invalidate_action(
    db: Session,
    request: HighRiskActionRequest,
    *,
    actor: User | None,
    reason: str,
    detail: dict[str, Any],
) -> None:
    if request.status == "invalidated":
        return
    previous_status = request.status
    request.status = "invalidated"
    request.invalidated_at = utc_now()
    request.invalidation_reason = reason
    request.updated_at = utc_now()
    db.add(request)
    db.add(
        HighRiskActionEvent(
            tenant_id=request.tenant_id,
            request_id=request.id,
            event_type="invalidated",
            actor_user_id=actor.id if actor else "system",
            actor_business_role=actor.business_role if actor else "system",
            detail_json={
                "reason": reason,
                "previous_status": previous_status,
                **detail,
            },
        )
    )


def _reject_update_during_uncertain_execution(
    db: Session,
    resource: BusinessResource,
) -> None:
    blocking = db.exec(
        select(BusinessActionExecution)
        .join(
            HighRiskActionRequest,
            HighRiskActionRequest.id == BusinessActionExecution.request_id,
        )
        .where(
            BusinessActionExecution.tenant_id == resource.tenant_id,
            BusinessActionExecution.resource_id == resource.id,
            BusinessActionExecution.status.in_(
                (
                    "running",
                    "compensation_requested",
                    "compensating",
                    "compensation_failed",
                    "manual_resolution_required",
                )
            ),
        )
    ).first()
    if blocking:
        raise HTTPException(
            status_code=409,
            detail=(
                "Resource cannot change while an execution outcome or compensation is unresolved"
            ),
        )


def _invalidate_open_actions_for_resource(
    db: Session,
    resource: BusinessResource,
    actor: User,
    *,
    reason: str,
    previous_digest: str,
    next_digest: str,
) -> None:
    actions = db.exec(
        select(HighRiskActionRequest).where(
            HighRiskActionRequest.tenant_id == resource.tenant_id,
            HighRiskActionRequest.resource_id == resource.id,
            HighRiskActionRequest.status.in_(("pending", "approved")),
        )
    ).all()
    for action in actions:
        execution = db.exec(
            select(BusinessActionExecution).where(
                BusinessActionExecution.tenant_id == resource.tenant_id,
                BusinessActionExecution.request_id == action.id,
            )
        ).first()
        if execution and execution.status in {"succeeded", "compensated"}:
            continue
        _invalidate_action(
            db,
            action,
            actor=actor,
            reason=reason,
            detail={
                "resource_id": resource.id,
                "resource_revision": resource.revision,
                "previous_resource_digest": previous_digest,
                "current_resource_digest": next_digest,
            },
        )
        if execution is None:
            continue
        execution.status = "failed"
        execution.execution_generation += 1
        execution.lease_owner = None
        execution.lease_expires_at = None
        execution.next_attempt_at = None
        execution.last_error_code = "approval_invalidated"
        execution.last_error_message = "Approved business resource context changed before execution"
        execution.updated_at = utc_now()
        db.add(execution)
        add_execution_event(
            db,
            execution,
            phase="reconciliation",
            event_type="approval_invalidated",
            actor=actor,
            detail={
                "reason": reason,
                "resource_revision": resource.revision,
                "previous_resource_digest": previous_digest,
                "current_resource_digest": next_digest,
            },
        )


def _require_resource_manager(user: User) -> None:
    if not is_approval_manager(user):
        raise HTTPException(
            status_code=403, detail="Only operations supervisors can manage resources"
        )


def _ensure_tenant(tenant_id: str, user: User) -> None:
    if tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Cannot access another tenant")
