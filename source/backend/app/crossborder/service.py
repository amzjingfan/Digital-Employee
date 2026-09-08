from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from app.business_resources.schema import HighRiskActionCreate
from app.business_resources.service import create_action_request
from app.config import get_settings
from app.crossborder.schema import (
    AfterSalesCaseCreate,
    AfterSalesCaseRead,
    AfterSalesClassification,
    AfterSalesClose,
    AfterSalesDraft,
    AfterSalesQueryResult,
    BusinessTraceEventRead,
    CrossborderOverview,
    HumanExceptionResolution,
    IntegrationHealthRead,
    IntegrationHealthReport,
    LogisticsAnomalyBatchCreate,
    LogisticsAnomalyBatchRead,
    LogisticsAnomalyRead,
    LogisticsEscalation,
    LogisticsResolution,
)
from app.db.database import set_tenant_context
from app.db.models import (
    AfterSalesCase,
    AfterSalesCaseEvent,
    AuthorizationDecision,
    BusinessResource,
    HighRiskActionRequest,
    IntegrationHealthEvent,
    IntegrationHealthState,
    LogisticsAnomaly,
    LogisticsAnomalyEvent,
    User,
    WorkTask,
    WorkTaskEvent,
    utc_now,
)
from app.security.authorization import authorize_business_resource
from app.security.permissions import is_admin_user
from app.work_tasks.schema import WorkTaskEvidenceReference
from app.work_tasks.service import append_task_evidence, create_linked_task

_AFTERSALES_ROLES = {"after_sales_specialist", "operations_supervisor"}
_LOGISTICS_MUTATION_ROLES = {"logistics_exception_specialist", "operations_supervisor"}
_LOGISTICS_VIEW_ROLES = _LOGISTICS_MUTATION_ROLES | {
    "after_sales_specialist",
    "procurement_specialist",
}
_MANAGER_ROLES = {"operations_supervisor"}
_HUMAN_EXCEPTION_FLAGS = {
    "order_absent",
    "identity_mismatch",
    "stale_logistics",
    "policy_conflict",
    "duplicate_claim",
    "deadline_near",
    "safety_risk",
    "privacy_risk",
    "reputation_risk",
    "dispute_risk",
}
_APPROVAL_FLAGS = {"safety_risk", "privacy_risk", "reputation_risk", "dispute_risk"}
_SAFE_ORDER_FIELDS = {
    "order_status",
    "payment_status",
    "shipment_status",
    "logistics_status",
    "sku_codes",
    "history",
    "customer_tier",
    "order_amount",
    "currency",
    "updated_at",
}
_SAFE_HISTORY_FIELDS = {"event_code", "status", "occurred_at", "source"}
_SAFE_LOGISTICS_EVIDENCE_FIELDS = {
    "last_scan_at",
    "expected_delivery_at",
    "tracking_status",
    "days_in_transit",
    "scan_count",
    "source_record_id",
    "source_updated_at",
}
_HEALTH_DOMAINS = {
    "orders",
    "payments",
    "shipping",
    "logistics",
    "knowledge",
    "approvals",
    "tasks",
}


def create_after_sales_case(
    db: Session, *, request: AfterSalesCaseCreate, user: User
) -> AfterSalesCaseRead:
    _require_tenant(request.tenant_id, user)
    _require_role(user, _AFTERSALES_ROLES)
    set_tenant_context(db, request.tenant_id)
    existing = db.exec(
        select(AfterSalesCase).where(
            AfterSalesCase.tenant_id == request.tenant_id,
            AfterSalesCase.case_key == request.case_key.strip(),
        )
    ).first()
    if existing:
        return _after_sales_read(db, existing)
    store = _authorized_resource(
        db,
        tenant_id=request.tenant_id,
        resource_id=request.store_resource_id,
        resource_type="store",
        user=user,
        action="REQUEST",
    )
    order_digest = _business_digest(request.tenant_id, request.order_reference)
    case = AfterSalesCase(
        tenant_id=request.tenant_id,
        case_key=request.case_key.strip(),
        store_resource_id=store.id,
        store_code=store.code,
        platform=request.platform.strip(),
        marketplace_country=request.marketplace_country.strip().upper(),
        language=request.language.strip(),
        order_reference_digest=order_digest,
        order_reference_masked=_mask_reference(request.order_reference),
        task_id="pending",
        created_by_user_id=user.id,
    )
    task, _ = create_linked_task(
        db,
        tenant_id=case.tenant_id,
        idempotency_key=f"after-sales-case:{case.case_key}",
        source_type="after_sales_case",
        source_id=case.id,
        title=f"售后工单 {case.order_reference_masked} · {case.platform}",
        description=request.summary,
        owner_business_role="after_sales_specialist",
        assigned_by_user_id=user.id,
        assigned_by_business_role=user.business_role,
        priority="normal",
        risk_level="medium",
        scope={
            "store_resource_id": store.id,
            "store_code": store.code,
            "country": case.marketplace_country,
        },
        input_data={"case_id": case.id, "order_reference_digest": order_digest},
    )
    case.task_id = task.id
    db.add(case)
    db.flush()
    _add_after_sales_event(
        db,
        case,
        "intake_created",
        user,
        to_status="intake",
        detail={"task_id": task.id, "store_code": store.code, "summary": request.summary},
    )
    db.commit()
    db.refresh(case)
    return _after_sales_read(db, case)


def list_after_sales_cases(
    db: Session, *, tenant_id: str, user: User, status: str | None = None
) -> list[AfterSalesCaseRead]:
    _require_tenant(tenant_id, user)
    _require_role(user, _AFTERSALES_ROLES)
    set_tenant_context(db, tenant_id)
    statement = select(AfterSalesCase).where(AfterSalesCase.tenant_id == tenant_id)
    if status:
        statement = statement.where(AfterSalesCase.status == status)
    rows = db.exec(statement.order_by(AfterSalesCase.updated_at.desc()).limit(300)).all()
    return [_after_sales_read(db, row, include_events=False) for row in rows]


def get_after_sales_case(
    db: Session, *, tenant_id: str, case_id: str, user: User
) -> AfterSalesCaseRead:
    _require_tenant(tenant_id, user)
    _require_role(user, _AFTERSALES_ROLES)
    set_tenant_context(db, tenant_id)
    return _after_sales_read(db, _after_sales_case(db, tenant_id, case_id))


def record_after_sales_query(
    db: Session,
    *,
    case_id: str,
    request: AfterSalesQueryResult,
    user: User,
) -> AfterSalesCaseRead:
    case = _mutable_after_sales_case(db, case_id, request.tenant_id, request.expected_version, user)
    if case.status not in {"intake", "queried"}:
        raise HTTPException(status_code=409, detail="Order query is only valid during intake")
    safe_snapshot = _sanitize_order_snapshot(request.order_snapshot)
    citations = [item.model_dump(mode="json") for item in request.citations]
    _validate_citation_scopes(citations, case)
    dependency_failures = sorted(
        key for key, status in request.dependency_status.items() if status != "healthy"
    )
    previous = case.status
    case.order_snapshot_json = safe_snapshot
    case.citations_json = citations
    task = db.get(WorkTask, case.task_id)
    if task is None:
        raise HTTPException(status_code=409, detail="Linked work task is unavailable")
    evidence_created = append_task_evidence(
        db,
        task=task,
        evidence=[
            WorkTaskEvidenceReference(
                source_type="knowledge_citation",
                source_id=f"{citation.source_id}@{citation.version}",
                severity="info",
                label=f"{citation.title} · v{citation.version}"[:320],
                summary=f"适用范围：{citation.scope}",
                source_route=f"/enterprise/crossborder-operations?case_id={case.id}",
                occurred_at=citation.retrieved_at,
            )
            for citation in request.citations
        ],
        actor_type="human",
        actor_id=user.id,
        actor_business_role=user.business_role,
    )
    case.needs_human = bool(dependency_failures)
    case.human_reason = (
        f"dependency_unavailable:{','.join(dependency_failures)}" if dependency_failures else None
    )
    case.status = "needs_human" if dependency_failures else "queried"
    _bump(case)
    _set_task_human_hold(db, case.task_id, user, case.human_reason) if dependency_failures else None
    for dependency_key, status in request.dependency_status.items():
        _record_query_dependency(
            db,
            tenant_id=case.tenant_id,
            dependency_key=dependency_key,
            status=status,
            observed_at=request.observed_at,
            user=user,
        )
    _add_after_sales_event(
        db,
        case,
        "order_context_queried",
        user,
        from_status=previous,
        to_status=case.status,
        detail={
            "snapshot_fields": sorted(safe_snapshot),
            "citation_ids": [item["source_id"] for item in citations],
            "work_task_evidence_created": evidence_created,
            "dependency_failures": dependency_failures,
            "observed_at": request.observed_at.isoformat(),
        },
    )
    db.commit()
    db.refresh(case)
    return _after_sales_read(db, case)


def classify_after_sales_case(
    db: Session,
    *,
    case_id: str,
    request: AfterSalesClassification,
    user: User,
) -> AfterSalesCaseRead:
    case = _mutable_after_sales_case(db, case_id, request.tenant_id, request.expected_version, user)
    if case.status != "queried":
        raise HTTPException(
            status_code=409,
            detail="A fresh order query is required before classification",
        )
    if not case.citations_json:
        raise HTTPException(status_code=409, detail="Reviewed knowledge citations are required")
    flags = sorted(set(request.exception_flags) & _HUMAN_EXCEPTION_FLAGS)
    previous = case.status
    case.category = request.category
    case.risk_level = request.risk_level
    case.needs_human = bool(flags)
    case.human_reason = ",".join(flags) if flags else None
    case.status = "needs_human" if flags else "classified"
    _bump(case)
    if flags:
        _set_task_human_hold(db, case.task_id, user, case.human_reason)
    _add_after_sales_event(
        db,
        case,
        "classified",
        user,
        from_status=previous,
        to_status=case.status,
        detail={
            "category": request.category,
            "confidence": request.confidence,
            "risk_level": request.risk_level,
            "exception_flags": flags,
            "note": request.note,
        },
    )
    db.commit()
    db.refresh(case)
    return _after_sales_read(db, case)


def resolve_after_sales_exception(
    db: Session,
    *,
    case_id: str,
    request: HumanExceptionResolution,
    user: User,
) -> AfterSalesCaseRead:
    case = _mutable_after_sales_case(db, case_id, request.tenant_id, request.expected_version, user)
    if case.status != "needs_human":
        raise HTTPException(status_code=409, detail="Case is not waiting for human resolution")
    if not _is_manager(user):
        raise HTTPException(
            status_code=403,
            detail="Only an operations supervisor can resolve exceptions",
        )
    if request.resume_status == "drafted" and not case.draft_reply:
        raise HTTPException(status_code=409, detail="No reply draft exists")
    previous = case.status
    case.status = request.resume_status
    case.needs_human = False
    case.human_reason = None
    _bump(case)
    _resume_task_from_hold(db, case.task_id, user)
    _add_after_sales_event(
        db,
        case,
        "human_exception_resolved",
        user,
        from_status=previous,
        to_status=case.status,
        detail={"resolution_note": request.resolution_note},
    )
    db.commit()
    db.refresh(case)
    return _after_sales_read(db, case)


def draft_after_sales_resolution(
    db: Session,
    *,
    case_id: str,
    request: AfterSalesDraft,
    user: User,
) -> AfterSalesCaseRead:
    case = _mutable_after_sales_case(db, case_id, request.tenant_id, request.expected_version, user)
    if case.status != "classified":
        raise HTTPException(status_code=409, detail="Case must be classified before drafting")
    if not case.citations_json:
        raise HTTPException(status_code=409, detail="Reply drafts require reviewed citations")
    recommendation = _bounded_json(request.recommendation, max_bytes=16 * 1024)
    approval_required = (
        request.requires_approval
        or request.refund_amount is not None
        or case.risk_level in {"high", "critical"}
    )
    previous = case.status
    case.recommendation_json = recommendation
    case.draft_reply = request.reply_draft.strip()
    case.status = "drafted"
    if approval_required:
        if request.refund_amount is None or not request.currency:
            raise HTTPException(
                status_code=422,
                detail="Refund amount and currency are required for an approval-bound draft",
            )
        summary = request.approval_summary.strip() or (
            f"售后工单 {case.case_key} 退款 {request.refund_amount:.2f} {request.currency.upper()}"
        )
        approval = create_action_request(
            db,
            request=HighRiskActionCreate(
                tenant_id=case.tenant_id,
                resource_id=case.store_resource_id,
                action_type="issue_refund",
                summary=summary,
                payload={
                    "order_id": case.order_reference_masked,
                    "order_reference_digest": case.order_reference_digest,
                    "amount": request.refund_amount,
                    "currency": request.currency.upper(),
                    "case_id": case.id,
                    "reply_digest": _plain_digest(case.draft_reply),
                },
            ),
            user=user,
            commit=False,
        )
        case.approval_request_id = approval.id
        case.status = "waiting_approval"
    _bump(case)
    _add_after_sales_event(
        db,
        case,
        "resolution_drafted",
        user,
        from_status=previous,
        to_status=case.status,
        detail={
            "approval_request_id": case.approval_request_id,
            "reply_digest": _plain_digest(case.draft_reply),
            "citation_ids": [item.get("source_id") for item in case.citations_json],
        },
    )
    db.commit()
    db.refresh(case)
    return _after_sales_read(db, case)


def close_after_sales_case(
    db: Session,
    *,
    case_id: str,
    request: AfterSalesClose,
    user: User,
) -> AfterSalesCaseRead:
    case = _mutable_after_sales_case(db, case_id, request.tenant_id, request.expected_version, user)
    if case.status not in {"drafted", "waiting_approval"}:
        raise HTTPException(status_code=409, detail="Only a reviewed draft can be closed")
    approval_status = None
    if case.approval_request_id:
        approval = db.get(HighRiskActionRequest, case.approval_request_id)
        approval_status = approval.status if approval else None
        if approval_status == "rejected":
            previous = case.status
            case.status = "rejected"
            _bump(case)
            _add_after_sales_event(
                db,
                case,
                "approval_rejected",
                user,
                from_status=previous,
                to_status="rejected",
                detail={"approval_request_id": case.approval_request_id},
            )
            db.commit()
            raise HTTPException(
                status_code=409,
                detail="Approval was rejected; submit a revised draft",
            )
        if approval_status != "approved":
            raise HTTPException(status_code=409, detail="Linked high-risk action is not approved")
    now = utc_now()
    previous = case.status
    followups = request.follow_ups or _default_case_followups(case)
    task_ids: list[str] = []
    for index, followup in enumerate(followups):
        task, _ = create_linked_task(
            db,
            tenant_id=case.tenant_id,
            idempotency_key=(
                f"after-sales-follow-up:{case.id}:{followup.owner_business_role}:{index}"
            ),
            source_type="after_sales_case_follow_up",
            source_id=case.id,
            title=followup.title,
            description=followup.note or request.root_cause,
            owner_business_role=followup.owner_business_role,
            assigned_by_user_id=user.id,
            assigned_by_business_role=user.business_role,
            priority=followup.priority,
            risk_level=case.risk_level,
            scope={"store_resource_id": case.store_resource_id, "case_id": case.id},
            input_data={"root_cause": request.root_cause, "parent_task_id": case.task_id},
            evidence=[
                WorkTaskEvidenceReference(
                    source_type="after_sales_case",
                    source_id=case.id,
                    severity=case.risk_level,
                    label=f"售后案例根因 · {case.category or 'other'}",
                    summary=(
                        f"工单 {case.order_reference_masked} 已完成人工复核，"
                        f"需 {followup.owner_business_role} 跟进。"
                    ),
                    source_route=f"/enterprise/crossborder-operations?case_id={case.id}",
                    occurred_at=now,
                )
            ],
        )
        task_ids.append(task.id)
    case.status = "closed"
    case.root_cause = request.root_cause.strip()
    case.follow_up_task_ids_json = task_ids
    case.closed_by_user_id = user.id
    case.closed_at = now
    _bump(case, now=now)
    from app.product_lifecycle.service import record_quality_issue_from_after_sales

    record_quality_issue_from_after_sales(
        db,
        case=case,
        root_cause=case.root_cause,
        task_ids=task_ids,
        user=user,
    )
    _complete_linked_task(db, case.task_id, user, request.outcome)
    _add_after_sales_event(
        db,
        case,
        "case_closed",
        user,
        from_status=previous,
        to_status="closed",
        detail={
            "outcome": request.outcome,
            "root_cause": case.root_cause,
            "approval_status": approval_status,
            "follow_up_task_ids": task_ids,
        },
    )
    db.commit()
    db.refresh(case)
    return _after_sales_read(db, case)


def ingest_logistics_anomalies(
    db: Session,
    *,
    request: LogisticsAnomalyBatchCreate,
    user: User,
) -> LogisticsAnomalyBatchRead:
    _require_tenant(request.tenant_id, user)
    _require_role(user, _LOGISTICS_MUTATION_ROLES)
    set_tenant_context(db, request.tenant_id)
    rows: list[LogisticsAnomaly] = []
    created_count = 0
    seen_fingerprints: set[str] = set()
    for item in request.items:
        carrier = _authorized_resource(
            db,
            tenant_id=request.tenant_id,
            resource_id=item.carrier_resource_id,
            resource_type="carrier",
            user=user,
            action="REQUEST",
        )
        if item.store_resource_id:
            _authorized_resource(
                db,
                tenant_id=request.tenant_id,
                resource_id=item.store_resource_id,
                resource_type="store",
                user=user,
                action="READ",
            )
        order_digest = _business_digest(request.tenant_id, item.order_reference)
        fingerprint = _logistics_fingerprint(
            request.tenant_id,
            order_digest,
            carrier.id,
            item.status_event_id,
            item.shipment_status,
            item.anomaly_type,
        )
        if fingerprint in seen_fingerprints:
            raise HTTPException(status_code=422, detail="Batch contains duplicate logistics events")
        seen_fingerprints.add(fingerprint)
        statement = select(LogisticsAnomaly).where(
            LogisticsAnomaly.tenant_id == request.tenant_id,
            LogisticsAnomaly.fingerprint == fingerprint,
        )
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            statement = statement.with_for_update()
        row = db.exec(statement).first()
        if row:
            row.occurrence_count += 1
            row.last_observed_at = max(row.last_observed_at, item.observed_at)
            row.severity = _max_risk(
                row.severity,
                _logistics_severity(item.anomaly_type, item.customer_impact, item.deadline_at),
            )
            _bump(row)
            _add_logistics_event(
                db,
                row,
                "duplicate_observed",
                user,
                from_status=row.status,
                to_status=row.status,
                detail={
                    "batch_key": request.batch_key,
                    "occurrence_count": row.occurrence_count,
                    "status_event_id": item.status_event_id,
                },
            )
            rows.append(row)
            continue
        dimensions = {
            "carrier": carrier.code,
            "channel": item.channel.strip(),
            "warehouse": item.warehouse.strip(),
            "country": item.country.strip().upper(),
            "sku": item.sku.strip(),
            "batch": item.batch.strip(),
        }
        cluster_key = _cluster_key(request.tenant_id, dimensions)
        severity = _logistics_severity(
            item.anomaly_type, item.customer_impact, item.deadline_at
        )
        row = LogisticsAnomaly(
            tenant_id=request.tenant_id,
            fingerprint=fingerprint,
            carrier_resource_id=carrier.id,
            carrier_code=carrier.code,
            store_resource_id=item.store_resource_id,
            platform=item.platform.strip(),
            order_reference_digest=order_digest,
            order_reference_masked=_mask_reference(item.order_reference),
            status_event_id=item.status_event_id.strip(),
            shipment_status=item.shipment_status.strip(),
            anomaly_type=item.anomaly_type,
            status="clustered",
            severity=severity,
            customer_impact=item.customer_impact,
            cluster_key=cluster_key,
            dimensions_json=dimensions,
            evidence_json=_sanitize_logistics_evidence(item.evidence),
            task_id="pending",
            deadline_at=item.deadline_at,
            first_observed_at=item.observed_at,
            last_observed_at=item.observed_at,
        )
        task, _ = create_linked_task(
            db,
            tenant_id=row.tenant_id,
            idempotency_key=f"logistics-anomaly:{fingerprint}",
            source_type="logistics_anomaly",
            source_id=row.id,
            title=f"物流异常 {row.order_reference_masked} · {row.anomaly_type}",
            description=(
                f"{carrier.name} / {row.shipment_status}；聚类 {cluster_key[:12]}，"
                f"客户影响 {row.customer_impact}。"
            ),
            owner_business_role="logistics_exception_specialist",
            assigned_by_user_id=user.id,
            assigned_by_business_role=user.business_role,
            priority=(
                "urgent" if severity == "critical" else "high" if severity == "high" else "normal"
            ),
            risk_level=severity,
            due_at=item.deadline_at,
            scope={
                "carrier_resource_id": carrier.id,
                "store_resource_id": item.store_resource_id or "",
                "cluster_key": cluster_key,
            },
            input_data={"anomaly_id": row.id, "read_only_patrol": True},
            evidence=[
                WorkTaskEvidenceReference(
                    source_type="logistics_event",
                    source_id=item.status_event_id.strip(),
                    severity=severity,
                    label=f"{carrier.code} · {item.anomaly_type}",
                    summary=(
                        f"订单 {row.order_reference_masked} 的物流状态为 "
                        f"{row.shipment_status}，客户影响 {row.customer_impact}。"
                    ),
                    source_route=(
                        f"/enterprise/crossborder-operations?anomaly_id={row.id}"
                    ),
                    occurred_at=item.observed_at,
                )
            ],
        )
        row.task_id = task.id
        db.add(row)
        db.flush()
        _add_logistics_event(
            db,
            row,
            "detected",
            user,
            to_status="detected",
            detail={"batch_key": request.batch_key, "severity": severity},
        )
        _add_logistics_event(
            db,
            row,
            "clustered",
            user,
            from_status="detected",
            to_status="clustered",
            detail={"cluster_key": cluster_key, "dimensions": dimensions, "task_id": task.id},
        )
        rows.append(row)
        created_count += 1
    db.commit()
    for row in rows:
        db.refresh(row)
    return LogisticsAnomalyBatchRead(
        items=[_logistics_read(db, row) for row in rows],
        created_count=created_count,
        deduplicated_count=len(rows) - created_count,
    )


def list_logistics_anomalies(
    db: Session,
    *,
    tenant_id: str,
    user: User,
    status: str | None = None,
    cluster_key: str | None = None,
) -> list[LogisticsAnomalyRead]:
    _require_tenant(tenant_id, user)
    _require_role(user, _LOGISTICS_VIEW_ROLES)
    set_tenant_context(db, tenant_id)
    statement = select(LogisticsAnomaly).where(LogisticsAnomaly.tenant_id == tenant_id)
    if status:
        statement = statement.where(LogisticsAnomaly.status == status)
    if cluster_key:
        statement = statement.where(LogisticsAnomaly.cluster_key == cluster_key)
    rows = db.exec(statement.order_by(LogisticsAnomaly.updated_at.desc()).limit(500)).all()
    if not _is_manager(user) and user.business_role != "logistics_exception_specialist":
        rows = [row for row in rows if user.business_role in row.escalation_targets_json]
    return [_logistics_read(db, row, include_events=False) for row in rows]


def get_logistics_anomaly(
    db: Session, *, tenant_id: str, anomaly_id: str, user: User
) -> LogisticsAnomalyRead:
    _require_tenant(tenant_id, user)
    _require_role(user, _LOGISTICS_VIEW_ROLES)
    set_tenant_context(db, tenant_id)
    row = _logistics_anomaly(db, tenant_id, anomaly_id)
    if (
        not _is_manager(user)
        and user.business_role != "logistics_exception_specialist"
        and user.business_role not in row.escalation_targets_json
    ):
        raise HTTPException(status_code=404, detail="Logistics anomaly not found")
    return _logistics_read(db, row)


def escalate_logistics_anomaly(
    db: Session,
    *,
    anomaly_id: str,
    request: LogisticsEscalation,
    user: User,
) -> LogisticsAnomalyRead:
    row = _mutable_logistics_anomaly(
        db, anomaly_id, request.tenant_id, request.expected_version, user
    )
    if row.status == "resolved":
        raise HTTPException(status_code=409, detail="Resolved anomaly cannot be escalated")
    targets = sorted(set(request.targets))
    previous = row.status
    task_ids = list(row.follow_up_task_ids_json or [])
    for target in targets:
        task, _ = create_linked_task(
            db,
            tenant_id=row.tenant_id,
            idempotency_key=f"logistics-escalation:{row.id}:{target}",
            source_type="logistics_escalation",
            source_id=row.id,
            title=f"物流异常升级 · {row.order_reference_masked} · {row.anomaly_type}",
            description=request.reason,
            owner_business_role=target,
            assigned_by_user_id=user.id,
            assigned_by_business_role=user.business_role,
            priority="urgent" if row.severity == "critical" else "high",
            risk_level=row.severity,
            due_at=row.deadline_at,
            scope={
                "carrier_resource_id": row.carrier_resource_id,
                "store_resource_id": row.store_resource_id or "",
                "cluster_key": row.cluster_key,
            },
            input_data={"anomaly_id": row.id, "parent_task_id": row.task_id},
            evidence=[
                WorkTaskEvidenceReference(
                    source_type="logistics_anomaly",
                    source_id=row.id,
                    severity=row.severity,
                    label=f"物流异常 · {row.anomaly_type}",
                    summary=(
                        f"订单 {row.order_reference_masked} 的异常已升级，"
                        f"承运商 {row.carrier_code}，影响等级 {row.customer_impact}。"
                    ),
                    source_route=(
                        f"/enterprise/crossborder-operations?anomaly_id={row.id}"
                    ),
                    occurred_at=row.last_observed_at,
                )
            ],
        )
        if task.id not in task_ids:
            task_ids.append(task.id)
    row.status = "escalated"
    row.escalation_targets_json = sorted(set(row.escalation_targets_json or []) | set(targets))
    row.follow_up_task_ids_json = task_ids
    _bump(row)
    _add_logistics_event(
        db,
        row,
        "escalated",
        user,
        from_status=previous,
        to_status="escalated",
        detail={"targets": targets, "reason": request.reason, "follow_up_task_ids": task_ids},
    )
    db.commit()
    db.refresh(row)
    return _logistics_read(db, row)


def resolve_logistics_anomaly(
    db: Session,
    *,
    anomaly_id: str,
    request: LogisticsResolution,
    user: User,
) -> LogisticsAnomalyRead:
    row = _mutable_logistics_anomaly(
        db, anomaly_id, request.tenant_id, request.expected_version, user
    )
    if row.status == "resolved":
        return _logistics_read(db, row)
    previous = row.status
    now = utc_now()
    row.status = "resolved"
    row.resolution = request.resolution.strip()
    row.resolved_by_user_id = user.id
    row.resolved_at = now
    _bump(row, now=now)
    _complete_linked_task(db, row.task_id, user, request.resolution)
    _add_logistics_event(
        db,
        row,
        "resolved",
        user,
        from_status=previous,
        to_status="resolved",
        detail={"resolution": row.resolution},
    )
    db.commit()
    db.refresh(row)
    return _logistics_read(db, row)


def report_integration_health(
    db: Session,
    *,
    request: IntegrationHealthReport,
    user: User,
) -> IntegrationHealthRead:
    _require_tenant(request.tenant_id, user)
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Only operations supervisors can report health")
    if request.domain not in _HEALTH_DOMAINS:
        raise HTTPException(status_code=422, detail="Unsupported integration health domain")
    if request.source == "fault_injection":
        if not is_admin_user(user) or not get_settings().mock_api_enabled:
            raise HTTPException(status_code=403, detail="Fault injection is disabled")
    set_tenant_context(db, request.tenant_id)
    row = _upsert_health_state(db, request=request, user=user)
    db.commit()
    db.refresh(row)
    return _health_read(db, row)


def list_integration_health(
    db: Session, *, tenant_id: str, user: User
) -> list[IntegrationHealthRead]:
    _require_tenant(tenant_id, user)
    set_tenant_context(db, tenant_id)
    rows = db.exec(
        select(IntegrationHealthState)
        .where(IntegrationHealthState.tenant_id == tenant_id)
        .order_by(IntegrationHealthState.domain, IntegrationHealthState.dependency_key)
    ).all()
    return [_health_read(db, row, include_events=False) for row in rows]


def crossborder_overview(
    db: Session, *, tenant_id: str, user: User
) -> CrossborderOverview:
    _require_tenant(tenant_id, user)
    set_tenant_context(db, tenant_id)
    after_sales = db.exec(
        select(AfterSalesCase).where(AfterSalesCase.tenant_id == tenant_id)
    ).all()
    logistics = db.exec(
        select(LogisticsAnomaly).where(LogisticsAnomaly.tenant_id == tenant_id)
    ).all()
    health = db.exec(
        select(IntegrationHealthState).where(IntegrationHealthState.tenant_id == tenant_id)
    ).all()
    return CrossborderOverview(
        after_sales_open=sum(row.status not in {"closed", "rejected"} for row in after_sales),
        after_sales_needs_human=sum(row.needs_human for row in after_sales),
        logistics_open=sum(row.status != "resolved" for row in logistics),
        logistics_high_risk=sum(
            row.status != "resolved" and row.severity in {"high", "critical"}
            for row in logistics
        ),
        degraded_dependencies=sum(_effective_health_status(row) != "healthy" for row in health),
        generated_at=utc_now(),
    )


def _after_sales_case(db: Session, tenant_id: str, case_id: str) -> AfterSalesCase:
    row = db.exec(
        select(AfterSalesCase).where(
            AfterSalesCase.tenant_id == tenant_id, AfterSalesCase.id == case_id
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="After-sales case not found")
    return row


def _mutable_after_sales_case(
    db: Session, case_id: str, tenant_id: str, expected_version: int, user: User
) -> AfterSalesCase:
    _require_tenant(tenant_id, user)
    _require_role(user, _AFTERSALES_ROLES)
    set_tenant_context(db, tenant_id)
    statement = select(AfterSalesCase).where(
        AfterSalesCase.tenant_id == tenant_id, AfterSalesCase.id == case_id
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    row = db.exec(statement).first()
    if not row:
        raise HTTPException(status_code=404, detail="After-sales case not found")
    if row.version != expected_version:
        raise HTTPException(status_code=409, detail="Case changed; reload before retrying")
    return row


def _logistics_anomaly(db: Session, tenant_id: str, anomaly_id: str) -> LogisticsAnomaly:
    row = db.exec(
        select(LogisticsAnomaly).where(
            LogisticsAnomaly.tenant_id == tenant_id, LogisticsAnomaly.id == anomaly_id
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Logistics anomaly not found")
    return row


def _mutable_logistics_anomaly(
    db: Session, anomaly_id: str, tenant_id: str, expected_version: int, user: User
) -> LogisticsAnomaly:
    _require_tenant(tenant_id, user)
    _require_role(user, _LOGISTICS_MUTATION_ROLES)
    set_tenant_context(db, tenant_id)
    statement = select(LogisticsAnomaly).where(
        LogisticsAnomaly.tenant_id == tenant_id, LogisticsAnomaly.id == anomaly_id
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    row = db.exec(statement).first()
    if not row:
        raise HTTPException(status_code=404, detail="Logistics anomaly not found")
    if row.version != expected_version:
        raise HTTPException(status_code=409, detail="Anomaly changed; reload before retrying")
    return row


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
            request_id=f"crossborder_{uuid4().hex}",
        )
    )
    db.flush()
    if not result.allowed:
        db.commit()
        raise HTTPException(status_code=404, detail="Business resource not found")
    return row


def _after_sales_read(
    db: Session, row: AfterSalesCase, *, include_events: bool = True
) -> AfterSalesCaseRead:
    approval = (
        db.get(HighRiskActionRequest, row.approval_request_id)
        if row.approval_request_id
        else None
    )
    events = (
        db.exec(
            select(AfterSalesCaseEvent)
            .where(
                AfterSalesCaseEvent.tenant_id == row.tenant_id,
                AfterSalesCaseEvent.case_id == row.id,
            )
            .order_by(AfterSalesCaseEvent.occurred_at)
        ).all()
        if include_events
        else []
    )
    return AfterSalesCaseRead(
        id=row.id,
        tenant_id=row.tenant_id,
        case_key=row.case_key,
        store_resource_id=row.store_resource_id,
        store_code=row.store_code,
        platform=row.platform,
        marketplace_country=row.marketplace_country,
        language=row.language,
        order_reference_masked=row.order_reference_masked,
        status=row.status,
        category=row.category,
        risk_level=row.risk_level,
        needs_human=row.needs_human,
        human_reason=row.human_reason,
        task_id=row.task_id,
        approval_request_id=row.approval_request_id,
        approval_status=approval.status if approval else None,
        order_snapshot=dict(row.order_snapshot_json or {}),
        citations=list(row.citations_json or []),
        recommendation=dict(row.recommendation_json or {}),
        draft_reply=row.draft_reply,
        root_cause=row.root_cause,
        follow_up_task_ids=list(row.follow_up_task_ids_json or []),
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        closed_at=row.closed_at,
        events=[_trace_read(event) for event in events],
    )


def _logistics_read(
    db: Session, row: LogisticsAnomaly, *, include_events: bool = True
) -> LogisticsAnomalyRead:
    events = (
        db.exec(
            select(LogisticsAnomalyEvent)
            .where(
                LogisticsAnomalyEvent.tenant_id == row.tenant_id,
                LogisticsAnomalyEvent.anomaly_id == row.id,
            )
            .order_by(LogisticsAnomalyEvent.occurred_at)
        ).all()
        if include_events
        else []
    )
    return LogisticsAnomalyRead(
        id=row.id,
        tenant_id=row.tenant_id,
        fingerprint=row.fingerprint,
        carrier_resource_id=row.carrier_resource_id,
        carrier_code=row.carrier_code,
        store_resource_id=row.store_resource_id,
        platform=row.platform,
        order_reference_masked=row.order_reference_masked,
        status_event_id=row.status_event_id,
        shipment_status=row.shipment_status,
        anomaly_type=row.anomaly_type,
        status=row.status,
        severity=row.severity,
        customer_impact=row.customer_impact,
        cluster_key=row.cluster_key,
        dimensions=dict(row.dimensions_json or {}),
        evidence=dict(row.evidence_json or {}),
        escalation_targets=list(row.escalation_targets_json or []),
        follow_up_task_ids=list(row.follow_up_task_ids_json or []),
        task_id=row.task_id,
        occurrence_count=row.occurrence_count,
        deadline_at=row.deadline_at,
        first_observed_at=row.first_observed_at,
        last_observed_at=row.last_observed_at,
        resolution=row.resolution,
        version=row.version,
        updated_at=row.updated_at,
        events=[_trace_read(event) for event in events],
    )


def _health_read(
    db: Session, row: IntegrationHealthState, *, include_events: bool = True
) -> IntegrationHealthRead:
    events = (
        db.exec(
            select(IntegrationHealthEvent)
            .where(
                IntegrationHealthEvent.tenant_id == row.tenant_id,
                IntegrationHealthEvent.state_id == row.id,
            )
            .order_by(IntegrationHealthEvent.occurred_at)
        ).all()
        if include_events
        else []
    )
    return IntegrationHealthRead(
        id=row.id,
        tenant_id=row.tenant_id,
        dependency_key=row.dependency_key,
        display_name=row.display_name,
        domain=row.domain,
        status=row.status,
        effective_status=_effective_health_status(row),
        reason_code=row.reason_code,
        message=row.message,
        recovery_hint=row.recovery_hint,
        source=row.source,
        last_success_at=row.last_success_at,
        observed_at=row.observed_at,
        stale_after_seconds=row.stale_after_seconds,
        version=row.version,
        updated_at=row.updated_at,
        events=[_trace_read(event) for event in events],
    )


def _trace_read(event: Any) -> BusinessTraceEventRead:
    return BusinessTraceEventRead(
        id=event.id,
        event_type=event.event_type,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        actor_business_role=getattr(event, "actor_business_role", None),
        from_status=event.from_status,
        to_status=event.to_status,
        detail=dict(event.detail_json or {}),
        occurred_at=event.occurred_at,
    )


def _add_after_sales_event(
    db: Session,
    row: AfterSalesCase,
    event_type: str,
    user: User,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AfterSalesCaseEvent(
            tenant_id=row.tenant_id,
            case_id=row.id,
            event_type=event_type,
            actor_type="human",
            actor_id=user.id,
            actor_business_role=user.business_role,
            from_status=from_status,
            to_status=to_status,
            detail_json=detail or {},
        )
    )


def _add_logistics_event(
    db: Session,
    row: LogisticsAnomaly,
    event_type: str,
    user: User,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        LogisticsAnomalyEvent(
            tenant_id=row.tenant_id,
            anomaly_id=row.id,
            event_type=event_type,
            actor_type="human",
            actor_id=user.id,
            actor_business_role=user.business_role,
            from_status=from_status,
            to_status=to_status,
            detail_json=detail or {},
        )
    )


def _upsert_health_state(
    db: Session, *, request: IntegrationHealthReport, user: User
) -> IntegrationHealthState:
    row = db.exec(
        select(IntegrationHealthState).where(
            IntegrationHealthState.tenant_id == request.tenant_id,
            IntegrationHealthState.dependency_key == request.dependency_key,
        )
    ).first()
    previous = row.status if row else None
    if row is None:
        row = IntegrationHealthState(
            tenant_id=request.tenant_id,
            dependency_key=request.dependency_key.strip(),
            display_name=request.display_name.strip(),
            domain=request.domain,
        )
        db.add(row)
        db.flush()
    changed = (
        row.status != request.status
        or row.reason_code != request.reason_code
        or row.message != request.message.strip()
    )
    row.display_name = request.display_name.strip()
    row.domain = request.domain
    row.status = request.status
    row.reason_code = request.reason_code
    row.message = request.message.strip()
    row.recovery_hint = request.recovery_hint.strip()
    row.source = request.source
    row.last_success_at = (
        request.last_success_at
        or (request.observed_at if request.status == "healthy" else row.last_success_at)
    )
    row.observed_at = request.observed_at
    row.stale_after_seconds = request.stale_after_seconds
    row.updated_by_user_id = user.id
    row.updated_at = utc_now()
    row.version += 1
    db.add(row)
    if changed or previous is None:
        db.add(
            IntegrationHealthEvent(
                tenant_id=row.tenant_id,
                state_id=row.id,
                event_type="recovered" if request.status == "healthy" else "degraded",
                actor_type="human",
                actor_id=user.id,
                from_status=previous,
                to_status=request.status,
                detail_json={
                    "reason_code": request.reason_code,
                    "message": request.message,
                    "source": request.source,
                },
            )
        )
    return row


def _record_query_dependency(
    db: Session,
    *,
    tenant_id: str,
    dependency_key: str,
    status: str,
    observed_at: datetime,
    user: User,
) -> None:
    normalized = (
        "healthy"
        if status == "healthy"
        else "degraded"
        if status == "stale"
        else "unavailable"
    )
    domain = dependency_key if dependency_key in _HEALTH_DOMAINS else "orders"
    _upsert_health_state(
        db,
        request=IntegrationHealthReport(
            tenant_id=tenant_id,
            dependency_key=dependency_key[:120],
            display_name=dependency_key.replace("_", " ").title()[:160],
            domain=domain,
            status=normalized,
            reason_code=None if normalized == "healthy" else f"query_{status}",
            message="" if normalized == "healthy" else f"Case query reported {status}",
            recovery_hint="Recheck connector health and refresh the case context",
            source="health_check",
            observed_at=observed_at,
        ),
        user=user,
    )


def _effective_health_status(row: IntegrationHealthState) -> str:
    stale_at = row.observed_at + timedelta(seconds=row.stale_after_seconds)
    if utc_now() > stale_at:
        return "stale"
    return row.status


def _sanitize_order_snapshot(value: dict[str, Any]) -> dict[str, Any]:
    unknown = set(value) - _SAFE_ORDER_FIELDS
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Order snapshot contains disallowed fields: {', '.join(sorted(unknown))}",
        )
    result = dict(value)
    if "sku_codes" in result:
        if not isinstance(result["sku_codes"], list) or any(
            not isinstance(item, str) for item in result["sku_codes"]
        ):
            raise HTTPException(status_code=422, detail="sku_codes must be a string list")
        result["sku_codes"] = result["sku_codes"][:100]
    if "history" in result:
        if not isinstance(result["history"], list):
            raise HTTPException(status_code=422, detail="history must be a list")
        history: list[dict[str, Any]] = []
        for event in result["history"][:50]:
            if not isinstance(event, dict):
                raise HTTPException(status_code=422, detail="history events must be objects")
            history.append({key: event[key] for key in _SAFE_HISTORY_FIELDS if key in event})
        result["history"] = history
    return _bounded_json(result, max_bytes=24 * 1024)


def _sanitize_logistics_evidence(value: dict[str, Any]) -> dict[str, Any]:
    unknown = set(value) - _SAFE_LOGISTICS_EVIDENCE_FIELDS
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Logistics evidence contains disallowed fields: {', '.join(sorted(unknown))}",
        )
    return _bounded_json(value, max_bytes=16 * 1024)


def _bounded_json(value: dict[str, Any], *, max_bytes: int) -> dict[str, Any]:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Payload must be valid JSON") from exc
    if len(encoded) > max_bytes:
        raise HTTPException(status_code=413, detail="Payload is too large")
    return json.loads(encoded.decode("utf-8"))


def _validate_citation_scopes(citations: list[dict[str, Any]], case: AfterSalesCase) -> None:
    for citation in citations:
        scope = str(citation.get("scope", ""))
        if (
            case.tenant_id not in scope
            and case.store_code not in scope
            and not scope.startswith("global:reviewed")
        ):
            raise HTTPException(status_code=422, detail="Citation scope does not cover this case")


def _default_case_followups(case: AfterSalesCase) -> list[Any]:
    from app.crossborder.schema import CaseFollowUp

    if case.category == "not_received":
        return [
            CaseFollowUp(
                owner_business_role="logistics_exception_specialist",
                title=f"复盘未收货工单 {case.order_reference_masked}",
                note="核查承运商节点、时效与同批次异常。",
                priority="high",
            )
        ]
    if case.category in {"damaged", "wrong_item"}:
        return [
            CaseFollowUp(
                owner_business_role="procurement_specialist",
                title=f"复盘质量/错发根因 {case.order_reference_masked}",
                note="核查供应商、来料、拣配或包装批次。",
                priority="high",
            ),
            CaseFollowUp(
                owner_business_role="designer",
                title=f"复盘包装与素材误导 {case.order_reference_masked}",
                note="核查包装图示、尺寸表现和场景素材是否造成误解。",
                priority="high",
            ),
            CaseFollowUp(
                owner_business_role="listing_compliance_specialist",
                title=f"复盘 Listing 事实一致性 {case.order_reference_masked}",
                note="核查 Listing 描述、属性与实际 SKU 是否一致。",
                priority="high",
            ),
        ]
    return [
        CaseFollowUp(
            owner_business_role="listing_compliance_specialist",
            title=f"复盘售后知识与 Listing {case.order_reference_masked}",
            note="核查商品说明、FAQ 与平台政策是否需要修订。",
            priority="normal",
        )
    ]


def _set_task_human_hold(
    db: Session, task_id: str, user: User, reason: str | None
) -> None:
    task = db.get(WorkTask, task_id)
    if not task or task.status in {"completed", "cancelled", "archived"}:
        return
    previous = task.status
    task.status = "waiting_input"
    task.control_mode = "human"
    task.taken_over_by_user_id = user.id
    task.taken_over_at = utc_now()
    task.execution_generation += 1
    task.cancel_requested = True
    task.lease_owner = None
    task.lease_expires_at = None
    task.next_attempt_at = None
    task.version += 1
    task.updated_at = utc_now()
    db.add(task)
    db.add(
        WorkTaskEvent(
            tenant_id=task.tenant_id,
            task_id=task.id,
            event_type="business_exception_handoff",
            actor_type="human",
            actor_id=user.id,
            actor_business_role=user.business_role,
            from_status=previous,
            to_status=task.status,
            detail_json={"reason": reason or "human_review_required"},
        )
    )


def _resume_task_from_hold(db: Session, task_id: str, user: User) -> None:
    task = db.get(WorkTask, task_id)
    if not task or task.status != "waiting_input":
        return
    task.status = "in_progress"
    task.control_mode = "human"
    task.cancel_requested = False
    task.version += 1
    task.updated_at = utc_now()
    db.add(task)
    db.add(
        WorkTaskEvent(
            tenant_id=task.tenant_id,
            task_id=task.id,
            event_type="business_exception_resolved",
            actor_type="human",
            actor_id=user.id,
            actor_business_role=user.business_role,
            from_status="waiting_input",
            to_status="in_progress",
            detail_json={},
        )
    )


def _complete_linked_task(db: Session, task_id: str, user: User, result: str) -> None:
    task = db.get(WorkTask, task_id)
    if not task or task.status in {"completed", "archived"}:
        return
    previous = task.status
    now = utc_now()
    task.status = "completed"
    task.control_mode = "human"
    task.cancel_requested = True
    task.execution_generation += 1
    task.lease_owner = None
    task.lease_expires_at = None
    task.next_attempt_at = None
    task.result_summary = result[:2000]
    task.completed_at = now
    task.version += 1
    task.updated_at = now
    db.add(task)
    db.add(
        WorkTaskEvent(
            tenant_id=task.tenant_id,
            task_id=task.id,
            event_type="business_aggregate_completed",
            actor_type="human",
            actor_id=user.id,
            actor_business_role=user.business_role,
            from_status=previous,
            to_status="completed",
            detail_json={"result": result[:500]},
        )
    )


def _bump(row: Any, *, now: datetime | None = None) -> None:
    row.version += 1
    row.updated_at = now or utc_now()


def _require_tenant(tenant_id: str, user: User) -> None:
    if tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access is forbidden")


def _require_role(user: User, roles: set[str]) -> None:
    if not is_admin_user(user) and user.business_role not in roles:
        raise HTTPException(
            status_code=403,
            detail="Current business role cannot access this workflow",
        )


def _is_manager(user: User) -> bool:
    return is_admin_user(user) or user.business_role in _MANAGER_ROLES


def _business_digest(tenant_id: str, value: str) -> str:
    canonical = "\x1f".join((tenant_id, value.strip()))
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


def _plain_digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode()).hexdigest()}"


def _mask_reference(value: str) -> str:
    normalized = value.strip()
    if len(normalized) <= 6:
        return f"{normalized[:1]}***{normalized[-1:]}"
    return f"{normalized[:2]}***{normalized[-4:]}"


def _logistics_fingerprint(
    tenant_id: str,
    order_digest: str,
    carrier_id: str,
    status_event_id: str,
    shipment_status: str,
    anomaly_type: str,
) -> str:
    canonical = "\x1f".join(
        [
            tenant_id,
            order_digest,
            carrier_id,
            status_event_id.strip().lower(),
            shipment_status.strip().lower(),
            anomaly_type,
        ]
    )
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


def _cluster_key(tenant_id: str, dimensions: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"tenant_id": tenant_id, **dimensions},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"cluster:{hashlib.sha256(canonical.encode()).hexdigest()}"


def _logistics_severity(
    anomaly_type: str, customer_impact: str, deadline_at: datetime | None
) -> str:
    if customer_impact == "critical":
        return "critical"
    if deadline_at:
        remaining = deadline_at - utc_now()
        if remaining <= timedelta(hours=6):
            return "critical"
        if remaining <= timedelta(hours=24):
            return "high"
    if customer_impact == "high" or anomaly_type in {"customs_hold", "delivery_dispute"}:
        return "high"
    if customer_impact == "low" and anomaly_type not in {"overdue", "stalled"}:
        return "low"
    return "medium"


def _max_risk(left: str, right: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    return left if order[left] >= order[right] else right
