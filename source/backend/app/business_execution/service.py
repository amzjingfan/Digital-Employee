from __future__ import annotations

import hashlib
from datetime import timedelta

from fastapi import HTTPException
from sqlmodel import Session, select

from app.business_execution.connectors import connector_type_for
from app.business_resources.integrity import approval_integrity_error
from app.business_resources.schema import (
    BusinessActionExecutionEventRead,
    BusinessActionExecutionRead,
    ExecutionReconciliationReport,
)
from app.config import Settings, get_settings
from app.db.models import (
    BusinessActionExecution,
    BusinessActionExecutionEvent,
    BusinessResource,
    HighRiskActionRequest,
    User,
    utc_now,
)
from app.security.permissions import is_admin_user

_MANAGER_ROLES = {"operations_supervisor"}


def stage_approved_execution(
    db: Session,
    action: HighRiskActionRequest,
    *,
    settings: Settings | None = None,
) -> BusinessActionExecution:
    """Stage the external command in the same transaction as approval."""
    existing = db.exec(
        select(BusinessActionExecution).where(
            BusinessActionExecution.tenant_id == action.tenant_id,
            BusinessActionExecution.request_id == action.id,
        )
    ).first()
    if existing:
        return existing
    if action.status != "approved":
        raise HTTPException(status_code=409, detail="Only approved actions can be staged")
    resource = db.exec(
        select(BusinessResource).where(
            BusinessResource.tenant_id == action.tenant_id,
            BusinessResource.id == action.resource_id,
        )
    ).one()
    integrity_error = approval_integrity_error(db, action, resource)
    if integrity_error:
        raise HTTPException(
            status_code=409,
            detail="Approval content or resource context changed before staging",
        )
    resolved = settings or get_settings()
    environment = resolved.business_execution_mode.strip().lower()
    if environment not in {"sandbox", "live"}:
        environment = "sandbox"
    from app.advertising.service import evaluate_policy_for_staging

    automation_gate = evaluate_policy_for_staging(db, action)
    can_queue = resolved.business_execution_enabled and bool(automation_gate["allowed"])
    status = "queued" if can_queue else "manual_resolution_required"
    key_source = f"staffdeck:v1:{action.tenant_id}:{action.id}:{action.action_type}"
    row = BusinessActionExecution(
        tenant_id=action.tenant_id,
        request_id=action.id,
        resource_id=action.resource_id,
        action_type=action.action_type,
        connector_type=connector_type_for(action.action_type, action.resource_type),
        environment=environment,
        approval_content_digest=action.content_digest,
        resource_snapshot_digest=action.resource_snapshot_digest,
        status=status,
        idempotency_key="sd-" + hashlib.sha256(key_source.encode("utf-8")).hexdigest()[:48],
        max_attempts=max(1, min(int(resolved.business_execution_max_attempts), 10)),
        next_attempt_at=utc_now() if status == "queued" else None,
        deadline_at=utc_now() + timedelta(hours=1),
        last_error_code=(
            None
            if status == "queued"
            else (
                "automation_policy_blocked"
                if resolved.business_execution_enabled
                else "execution_disabled"
            )
        ),
        last_error_message=(
            None
            if status == "queued"
            else (
                str(automation_gate["reason"])
                if resolved.business_execution_enabled
                else "Business execution is disabled"
            )
        ),
    )
    db.add(row)
    db.flush()
    add_execution_event(
        db,
        row,
        phase="execution",
        event_type="execution_staged",
        detail={
            "environment": environment,
            "connector_type": row.connector_type,
            "automation_gate": automation_gate,
        },
    )
    return row


def list_executions(
    db: Session,
    *,
    tenant_id: str,
    user: User,
    status: str | None = None,
) -> list[BusinessActionExecutionRead]:
    _ensure_tenant(tenant_id, user)
    statement = select(BusinessActionExecution).where(
        BusinessActionExecution.tenant_id == tenant_id
    )
    if not _is_manager(user):
        statement = statement.join(
            HighRiskActionRequest,
            HighRiskActionRequest.id == BusinessActionExecution.request_id,
        ).where(HighRiskActionRequest.requester_user_id == user.id)
    if status:
        statement = statement.where(BusinessActionExecution.status == status)
    rows = db.exec(statement.order_by(BusinessActionExecution.created_at.desc()).limit(500)).all()
    return [execution_read(db, row) for row in rows]


def execution_for_request(
    db: Session,
    *,
    tenant_id: str,
    request_id: str,
) -> BusinessActionExecutionRead | None:
    row = db.exec(
        select(BusinessActionExecution).where(
            BusinessActionExecution.tenant_id == tenant_id,
            BusinessActionExecution.request_id == request_id,
        )
    ).first()
    return execution_read(db, row) if row else None


def retry_execution(
    db: Session,
    *,
    tenant_id: str,
    execution_id: str,
    reason: str,
    user: User,
) -> BusinessActionExecutionRead:
    row = _operator_execution(db, tenant_id, execution_id, user)
    action = db.exec(
        select(HighRiskActionRequest).where(
            HighRiskActionRequest.tenant_id == tenant_id,
            HighRiskActionRequest.id == row.request_id,
        )
    ).one()
    resource = db.exec(
        select(BusinessResource).where(
            BusinessResource.tenant_id == tenant_id,
            BusinessResource.id == row.resource_id,
        )
    ).one()
    if action.status != "approved" or approval_integrity_error(
        db,
        action,
        resource,
        execution=row,
    ):
        raise HTTPException(status_code=409, detail="Invalidated approval cannot be retried")
    if row.status not in {
        "failed",
        "retry_wait",
        "compensation_failed",
        "manual_resolution_required",
    }:
        raise HTTPException(
            status_code=409, detail="Execution is not retryable in its current state"
        )
    previous_status = row.status
    latest_event = db.exec(
        select(BusinessActionExecutionEvent)
        .where(
            BusinessActionExecutionEvent.tenant_id == tenant_id,
            BusinessActionExecutionEvent.execution_id == row.id,
        )
        .order_by(BusinessActionExecutionEvent.occurred_at.desc())
    ).first()
    retry_compensation = previous_status == "compensation_failed" or (
        previous_status == "manual_resolution_required"
        and latest_event is not None
        and latest_event.phase == "compensation"
    )
    if retry_compensation:
        row.status = "compensation_requested"
        phase = "compensation"
    else:
        row.status = "queued"
        phase = "execution"
    row.next_attempt_at = utc_now()
    row.deadline_at = utc_now() + timedelta(hours=1)
    row.lease_owner = None
    row.lease_expires_at = None
    row.last_error_code = None
    row.last_error_message = None
    row.updated_at = utc_now()
    db.add(row)
    add_execution_event(
        db,
        row,
        phase="operator",
        event_type="operator_retry_requested",
        actor=user,
        detail={"reason": reason.strip(), "previous_status": previous_status, "retry_phase": phase},
    )
    db.commit()
    db.refresh(row)
    return execution_read(db, row)


def request_compensation(
    db: Session,
    *,
    tenant_id: str,
    execution_id: str,
    reason: str,
    user: User,
) -> BusinessActionExecutionRead:
    row = _operator_execution(db, tenant_id, execution_id, user)
    action = db.exec(
        select(HighRiskActionRequest).where(
            HighRiskActionRequest.tenant_id == tenant_id,
            HighRiskActionRequest.id == row.request_id,
        )
    ).one()
    if action.requester_user_id == user.id:
        raise HTTPException(
            status_code=403, detail="Requester cannot initiate compensation for their own action"
        )
    if row.status != "succeeded":
        raise HTTPException(status_code=409, detail="Only succeeded executions can be compensated")
    row.status = "compensation_requested"
    row.next_attempt_at = utc_now()
    row.deadline_at = utc_now() + timedelta(hours=1)
    row.updated_at = utc_now()
    db.add(row)
    add_execution_event(
        db,
        row,
        phase="operator",
        event_type="compensation_requested",
        actor=user,
        detail={"reason": reason.strip()},
    )
    db.commit()
    db.refresh(row)
    return execution_read(db, row)


def reconcile_execution(
    db: Session,
    *,
    execution_id: str,
    report: ExecutionReconciliationReport,
    user: User,
) -> BusinessActionExecutionRead:
    """Record a connector observation and fail closed on any identity mismatch."""

    row = _operator_execution(db, report.tenant_id, execution_id, user)
    previous_status = row.status
    mismatches: list[str] = []
    if report.observed_idempotency_key != row.idempotency_key:
        mismatches.append("idempotency_key_mismatch")
    if (
        row.external_operation_id
        and report.external_operation_id
        and row.external_operation_id != report.external_operation_id
    ):
        mismatches.append("external_operation_id_mismatch")
    now = utc_now()
    if mismatches:
        row.status = "manual_resolution_required"
        row.last_error_code = "reconciliation_identity_mismatch"
        row.last_error_message = ",".join(mismatches)
        row.next_attempt_at = None
    elif report.observed_status == "succeeded":
        if row.status in {"failed", "compensation_failed", "compensated"}:
            row.status = "manual_resolution_required"
            row.last_error_code = "reconciliation_state_conflict"
            row.last_error_message = f"Local {previous_status}, remote succeeded"
        else:
            row.status = "succeeded"
            row.completed_at = row.completed_at or now
            row.external_operation_id = report.external_operation_id or row.external_operation_id
            row.receipt_json = {
                **row.receipt_json,
                "reconciliation": {
                    "observed_status": report.observed_status,
                    "receipt_digest": report.receipt_digest,
                    "observed_at": now.isoformat(),
                },
            }
            row.last_error_code = None
            row.last_error_message = None
    elif report.observed_status == "failed":
        if row.status == "succeeded":
            row.status = "manual_resolution_required"
            row.last_error_code = "reconciliation_state_conflict"
            row.last_error_message = "Local succeeded, remote failed"
        else:
            row.status = "failed"
            row.last_error_code = "remote_confirmed_failure"
            row.last_error_message = report.note.strip()
    else:
        row.status = "manual_resolution_required"
        row.last_error_code = f"remote_{report.observed_status}"
        row.last_error_message = report.note.strip()
        row.next_attempt_at = None
    row.updated_at = now
    db.add(row)
    add_execution_event(
        db,
        row,
        phase="reconciliation",
        event_type=("reconciliation_mismatch" if mismatches else "external_state_reconciled"),
        actor=user,
        detail={
            "previous_status": previous_status,
            "observed_status": report.observed_status,
            "observed_idempotency_key": report.observed_idempotency_key,
            "external_operation_id": report.external_operation_id,
            "receipt_digest": report.receipt_digest,
            "mismatches": mismatches,
            "note": report.note,
        },
    )
    if row.status == "succeeded":
        from app.advertising.service import schedule_effect_followups_for_execution

        schedule_effect_followups_for_execution(db, row)
    db.commit()
    db.refresh(row)
    return execution_read(db, row)


def execution_read(db: Session, row: BusinessActionExecution) -> BusinessActionExecutionRead:
    events = db.exec(
        select(BusinessActionExecutionEvent)
        .where(
            BusinessActionExecutionEvent.tenant_id == row.tenant_id,
            BusinessActionExecutionEvent.execution_id == row.id,
        )
        .order_by(BusinessActionExecutionEvent.occurred_at)
    ).all()
    return BusinessActionExecutionRead(
        id=row.id,
        tenant_id=row.tenant_id,
        request_id=row.request_id,
        resource_id=row.resource_id,
        action_type=row.action_type,
        connector_type=row.connector_type,
        environment=row.environment,
        workflow_version=row.workflow_version,
        approval_content_digest=row.approval_content_digest,
        resource_snapshot_digest=row.resource_snapshot_digest,
        status=row.status,
        idempotency_key=row.idempotency_key,
        attempt_count=row.attempt_count,
        compensation_attempt_count=row.compensation_attempt_count,
        max_attempts=row.max_attempts,
        next_attempt_at=row.next_attempt_at,
        deadline_at=row.deadline_at,
        external_operation_id=row.external_operation_id,
        receipt=dict(row.receipt_json or {}),
        last_error_code=row.last_error_code,
        last_error_message=row.last_error_message,
        started_at=row.started_at,
        completed_at=row.completed_at,
        compensated_at=row.compensated_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        events=[
            BusinessActionExecutionEventRead(
                phase=event.phase,
                event_type=event.event_type,
                attempt_no=event.attempt_no,
                actor_type=event.actor_type,
                actor_id=event.actor_id,
                actor_business_role=event.actor_business_role,
                detail=dict(event.detail_json or {}),
                occurred_at=event.occurred_at,
            )
            for event in events
        ],
    )


def add_execution_event(
    db: Session,
    execution: BusinessActionExecution,
    *,
    phase: str,
    event_type: str,
    detail: dict,
    attempt_no: int = 0,
    actor: User | None = None,
) -> None:
    db.add(
        BusinessActionExecutionEvent(
            tenant_id=execution.tenant_id,
            execution_id=execution.id,
            request_id=execution.request_id,
            phase=phase,
            event_type=event_type,
            attempt_no=attempt_no,
            actor_type="user" if actor else "system",
            actor_id=actor.id if actor else None,
            actor_business_role=actor.business_role if actor else None,
            detail_json=detail,
        )
    )


def _operator_execution(
    db: Session,
    tenant_id: str,
    execution_id: str,
    user: User,
) -> BusinessActionExecution:
    _ensure_tenant(tenant_id, user)
    if not _is_manager(user):
        raise HTTPException(
            status_code=403, detail="Only operations supervisors can control executions"
        )
    statement = select(BusinessActionExecution).where(
        BusinessActionExecution.tenant_id == tenant_id,
        BusinessActionExecution.id == execution_id,
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    row = db.exec(statement).first()
    if not row:
        raise HTTPException(status_code=404, detail="Business action execution not found")
    return row


def _is_manager(user: User) -> bool:
    return is_admin_user(user) or user.business_role in _MANAGER_ROLES


def _ensure_tenant(tenant_id: str, user: User) -> None:
    if tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Cannot access another tenant")
