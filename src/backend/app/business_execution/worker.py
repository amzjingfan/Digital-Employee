from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_
from sqlmodel import Session, select

from app.business_execution.connectors import build_connector
from app.business_execution.contracts import ConnectorOutcome, ExecutionContext
from app.business_execution.service import add_execution_event
from app.business_resources.integrity import approval_integrity_error
from app.config import Settings, get_settings
from app.db import engine
from app.db.models import (
    BusinessActionExecution,
    BusinessResource,
    HighRiskActionEvent,
    HighRiskActionRequest,
    utc_now,
)

logger = logging.getLogger(__name__)

_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None


@dataclass(frozen=True)
class _Claim:
    context: ExecutionContext
    generation: int
    phase: str
    original_receipt: dict


def run_execution_cycle(*, db_engine=None, settings: Settings | None = None) -> int:
    resolved = settings or get_settings()
    use_engine = db_engine or engine
    processed = 0
    for tenant_id in resolved.business_execution_tenant_id_list:
        _recover_stale(use_engine, tenant_id)
        for _ in range(max(1, resolved.business_execution_batch_size)):
            claim = _claim_one(use_engine, tenant_id, resolved)
            if not claim:
                break
            processed += 1
            connector = build_connector(
                "sandbox"
                if claim.context.environment == "sandbox"
                else claim.context.connector_type,
                settings=resolved,
            )
            try:
                if claim.phase == "compensation":
                    outcome = connector.compensate(claim.context, claim.original_receipt)
                else:
                    outcome = connector.execute(claim.context)
            except Exception as exc:  # last-resort isolation for connector defects
                logger.exception("Business connector raised unexpectedly")
                outcome = ConnectorOutcome(
                    disposition="unknown",
                    error_code="connector_internal_error",
                    error_message=type(exc).__name__,
                )
            _record_outcome(use_engine, claim, outcome, resolved)
    return processed


def run_execution_daemon(*, db_engine=None, settings: Settings | None = None) -> None:
    resolved = settings or get_settings()
    interval = max(0.2, resolved.business_execution_poll_seconds)
    while not _stop_event.is_set():
        try:
            run_execution_cycle(db_engine=db_engine, settings=resolved)
        except Exception:
            logger.exception("Business execution daemon polling failed")
        if _stop_event.wait(interval):
            return


def start_execution_daemon(*, db_engine=None, settings: Settings | None = None) -> bool:
    global _worker_thread
    resolved = settings or get_settings()
    if not resolved.business_execution_enabled:
        return False
    if not resolved.business_execution_tenant_id_list:
        logger.warning("Business execution is enabled but BUSINESS_EXECUTION_TENANT_IDS is empty")
        return False
    if _worker_thread and _worker_thread.is_alive():
        return True
    _stop_event.clear()
    _worker_thread = threading.Thread(
        target=run_execution_daemon,
        kwargs={"db_engine": db_engine, "settings": resolved},
        name="staffdeck-business-execution",
        daemon=True,
    )
    _worker_thread.start()
    return True


def stop_execution_daemon(timeout_seconds: float = 5.0) -> bool:
    global _worker_thread
    _stop_event.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=max(0.0, timeout_seconds))
    stopped = not (_worker_thread and _worker_thread.is_alive())
    if stopped:
        _worker_thread = None
    return stopped


def _claim_one(db_engine, tenant_id: str, settings: Settings) -> _Claim | None:
    now = utc_now()
    with Session(db_engine) as db:
        _set_tenant(db, tenant_id)
        statement = (
            select(BusinessActionExecution)
            .where(
                BusinessActionExecution.tenant_id == tenant_id,
                BusinessActionExecution.status.in_(
                    ("queued", "retry_wait", "compensation_requested")
                ),
                or_(
                    BusinessActionExecution.next_attempt_at.is_(None),
                    BusinessActionExecution.next_attempt_at <= now,
                ),
            )
            .order_by(BusinessActionExecution.created_at)
            .limit(1)
        )
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        row = db.exec(statement).first()
        if not row:
            return None
        phase = "compensation" if row.status == "compensation_requested" else "execution"
        attempt_no = (
            row.compensation_attempt_count if phase == "compensation" else row.attempt_count
        )
        if row.deadline_at and row.deadline_at <= now:
            row.status = "manual_resolution_required"
            row.last_error_code = "execution_deadline_exceeded"
            row.last_error_message = "Execution deadline exceeded before the next attempt"
            row.next_attempt_at = None
            row.updated_at = now
            db.add(row)
            add_execution_event(
                db,
                row,
                phase="reconciliation",
                event_type="deadline_exceeded",
                detail={},
                attempt_no=attempt_no,
            )
            db.commit()
            return None
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
        if phase == "execution":
            integrity_error = (
                "approval_not_active"
                if action.status != "approved"
                else approval_integrity_error(db, action, resource, execution=row)
            )
            if integrity_error:
                _invalidate_before_execution(
                    db,
                    row,
                    action,
                    reason=integrity_error,
                    now=now,
                )
                db.commit()
                return None
        row.status = "compensating" if phase == "compensation" else "running"
        if phase == "compensation":
            row.compensation_attempt_count += 1
            attempt_no = row.compensation_attempt_count
        else:
            row.attempt_count += 1
            attempt_no = row.attempt_count
        row.execution_generation += 1
        row.lease_owner = f"worker-{uuid4().hex[:12]}"
        row.lease_expires_at = now + timedelta(
            seconds=max(10, settings.business_execution_lease_seconds)
        )
        row.started_at = row.started_at or now
        row.next_attempt_at = None
        row.updated_at = now
        db.add(row)
        add_execution_event(
            db,
            row,
            phase=phase,
            event_type=f"{phase}_started",
            detail={"generation": row.execution_generation, "connector_type": row.connector_type},
            attempt_no=attempt_no,
        )
        context = ExecutionContext(
            execution_id=row.id,
            tenant_id=tenant_id,
            request_id=row.request_id,
            resource_id=row.resource_id,
            resource_type=action.resource_type,
            resource_code=resource.code,
            action_type=row.action_type,
            payload=dict(action.payload_json or {}),
            resource_metadata=dict(resource.metadata_json or {}),
            connector_type=row.connector_type,
            environment=row.environment,
            idempotency_key=row.idempotency_key,
            attempt_no=attempt_no,
        )
        claim = _Claim(
            context=context,
            generation=row.execution_generation,
            phase=phase,
            original_receipt=dict(row.receipt_json or {}),
        )
        db.commit()
        return claim


def _record_outcome(
    db_engine,
    claim: _Claim,
    outcome: ConnectorOutcome,
    settings: Settings,
) -> None:
    now = utc_now()
    with Session(db_engine) as db:
        _set_tenant(db, claim.context.tenant_id)
        statement = select(BusinessActionExecution).where(
            BusinessActionExecution.tenant_id == claim.context.tenant_id,
            BusinessActionExecution.id == claim.context.execution_id,
        )
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            statement = statement.with_for_update()
        row = db.exec(statement).one()
        expected = "compensating" if claim.phase == "compensation" else "running"
        if row.execution_generation != claim.generation or row.status != expected:
            add_execution_event(
                db,
                row,
                phase="reconciliation",
                event_type="stale_outcome_ignored",
                detail={
                    "claim_generation": claim.generation,
                    "current_generation": row.execution_generation,
                },
                attempt_no=claim.context.attempt_no,
            )
            db.commit()
            return
        row.lease_owner = None
        row.lease_expires_at = None
        row.updated_at = now
        row.external_operation_id = outcome.external_operation_id or row.external_operation_id
        row.last_error_code = outcome.error_code
        row.last_error_message = (outcome.error_message or "")[:1000] or None
        event_type = outcome.disposition
        detail = {
            "error_code": outcome.error_code,
            "error_message": row.last_error_message,
            "external_operation_id": outcome.external_operation_id,
            "receipt": outcome.receipt,
        }
        if outcome.disposition == "succeeded":
            if claim.phase == "compensation":
                row.status = "compensated"
                row.compensated_at = now
                row.receipt_json = {
                    **claim.original_receipt,
                    "compensation_receipt": outcome.receipt,
                }
                event_type = "compensation_succeeded"
            else:
                row.status = "succeeded"
                row.completed_at = now
                row.receipt_json = outcome.receipt
                event_type = "execution_succeeded"
        elif outcome.disposition == "retryable_failure":
            phase_attempts = (
                row.compensation_attempt_count
                if claim.phase == "compensation"
                else row.attempt_count
            )
            exhausted = phase_attempts >= row.max_attempts or (
                row.deadline_at is not None and row.deadline_at <= now
            )
            if exhausted:
                row.status = "compensation_failed" if claim.phase == "compensation" else "failed"
                event_type = f"{claim.phase}_attempts_exhausted"
            else:
                row.status = (
                    "compensation_requested" if claim.phase == "compensation" else "retry_wait"
                )
                delay = outcome.retry_after_seconds
                if delay is None:
                    delay = min(300.0, 5.0 * (2 ** max(0, phase_attempts - 1)))
                row.next_attempt_at = now + timedelta(seconds=max(0.0, min(delay, 900.0)))
                event_type = f"{claim.phase}_retry_scheduled"
                detail["next_attempt_at"] = row.next_attempt_at.isoformat()
        elif outcome.disposition == "terminal_failure":
            row.status = "compensation_failed" if claim.phase == "compensation" else "failed"
            event_type = f"{claim.phase}_failed"
        else:
            row.status = "manual_resolution_required"
            row.next_attempt_at = None
            event_type = "remote_outcome_unknown"
        db.add(row)
        add_execution_event(
            db,
            row,
            phase=claim.phase,
            event_type=event_type,
            detail=detail,
            attempt_no=claim.context.attempt_no,
        )
        if row.status == "succeeded" and claim.phase == "execution":
            from app.advertising.service import schedule_effect_followups_for_execution

            schedule_effect_followups_for_execution(db, row)
        db.commit()


def _recover_stale(db_engine, tenant_id: str) -> None:
    now = utc_now()
    with Session(db_engine) as db:
        _set_tenant(db, tenant_id)
        rows = db.exec(
            select(BusinessActionExecution).where(
                BusinessActionExecution.tenant_id == tenant_id,
                BusinessActionExecution.status.in_(("running", "compensating")),
                or_(
                    BusinessActionExecution.lease_expires_at.is_(None),
                    BusinessActionExecution.lease_expires_at <= now,
                ),
            )
        ).all()
        for row in rows:
            previous = row.status
            if row.environment == "sandbox":
                row.status = "compensation_requested" if previous == "compensating" else "queued"
                row.next_attempt_at = now
                event_type = "stale_sandbox_attempt_requeued"
            else:
                row.status = "manual_resolution_required"
                row.next_attempt_at = None
                row.last_error_code = "remote_state_unknown"
                row.last_error_message = "Worker lease expired while the remote result was unknown"
                event_type = "stale_live_attempt_requires_reconciliation"
            row.lease_owner = None
            row.lease_expires_at = None
            row.execution_generation += 1
            row.updated_at = now
            db.add(row)
            add_execution_event(
                db,
                row,
                phase="reconciliation",
                event_type=event_type,
                detail={"previous_status": previous},
                attempt_no=(
                    row.compensation_attempt_count
                    if previous == "compensating"
                    else row.attempt_count
                ),
            )
        if rows:
            db.commit()


def _set_tenant(db: Session, tenant_id: str) -> None:
    db.info["staffdeck_tenant_id"] = tenant_id


def _invalidate_before_execution(
    db: Session,
    execution: BusinessActionExecution,
    action: HighRiskActionRequest,
    *,
    reason: str,
    now: datetime,
) -> None:
    previous_status = action.status
    if action.status != "invalidated":
        action.status = "invalidated"
        action.invalidated_at = now
        action.invalidation_reason = reason
        action.updated_at = now
        db.add(action)
        db.add(
            HighRiskActionEvent(
                tenant_id=action.tenant_id,
                request_id=action.id,
                event_type="invalidated",
                actor_user_id="system",
                actor_business_role="system",
                detail_json={
                    "reason": reason,
                    "previous_status": previous_status,
                    "phase": "pre_connector_integrity_check",
                    "execution_id": execution.id,
                },
            )
        )
    execution.status = "failed"
    execution.execution_generation += 1
    execution.lease_owner = None
    execution.lease_expires_at = None
    execution.next_attempt_at = None
    execution.last_error_code = "approval_invalidated"
    execution.last_error_message = "Approval content or resource context changed before execution"
    execution.updated_at = now
    db.add(execution)
    add_execution_event(
        db,
        execution,
        phase="reconciliation",
        event_type="approval_invalidated",
        detail={"reason": reason, "request_status": previous_status},
    )
