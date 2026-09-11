from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from app.db.database import set_tenant_context
from app.db.models import (
    AgentProfile,
    User,
    WorkTask,
    WorkTaskEvent,
    WorkTaskEvidence,
    WorkTaskExecutionSnapshot,
    WorkTaskRun,
    utc_now,
)
from app.security.business_roles import BUSINESS_ROLE_BY_KEY, business_role_label
from app.work_tasks.schema import (
    ReportFollowUpCommand,
    WorkTaskBatchCreate,
    WorkTaskBatchResponse,
    WorkTaskCreate,
    WorkTaskEventRead,
    WorkTaskEvidenceRead,
    WorkTaskEvidenceReference,
    WorkTaskListResponse,
    WorkTaskQueueSummary,
    WorkTaskRead,
    WorkTaskRunRead,
    WorkTaskTransition,
)

_MANAGER_ROLES = {"operations_supervisor", "platform_admin"}
_TASK_OWNER_ROLES = {
    "operations_supervisor",
    "after_sales_specialist",
    "listing_compliance_specialist",
    "logistics_exception_specialist",
    "advertising_inspection_specialist",
    "designer",
    "procurement_specialist",
    "tiktok_bd_specialist",
    "tiktok_content_specialist",
    "tiktok_shop_operator",
    "tiktok_media_buyer",
    "tiktok_tap_manager",
    "tiktok_live_operator",
}
_OPEN_STATUSES = {"pending", "in_progress", "waiting_input", "review"}
_TRANSITIONS: dict[tuple[str, str], str] = {
    ("pending", "start"): "in_progress",
    ("in_progress", "request_input"): "waiting_input",
    ("waiting_input", "resume"): "in_progress",
    ("in_progress", "request_review"): "review",
    ("review", "complete"): "completed",
    ("review", "rework"): "in_progress",
    ("pending", "fail"): "failed",
    ("in_progress", "fail"): "failed",
    ("waiting_input", "fail"): "failed",
    ("review", "fail"): "failed",
    ("failed", "retry"): "pending",
    ("pending", "cancel"): "cancelled",
    ("in_progress", "cancel"): "cancelled",
    ("waiting_input", "cancel"): "cancelled",
    ("review", "cancel"): "cancelled",
    ("completed", "archive"): "archived",
    ("failed", "archive"): "archived",
    ("cancelled", "archive"): "archived",
    ("in_progress", "takeover"): "in_progress",
    ("waiting_input", "takeover"): "waiting_input",
    ("review", "takeover"): "review",
    ("in_progress", "return_to_agent"): "pending",
    ("waiting_input", "return_to_agent"): "pending",
    ("review", "return_to_agent"): "pending",
    ("failed", "return_to_agent"): "pending",
}


def create_task(db: Session, *, request: WorkTaskCreate, user: User) -> WorkTaskRead:
    _require_tenant(user, request.tenant_id)
    _require_role_access(user, request.owner_business_role, creating=True)
    _validate_owner_role(request.owner_business_role)
    set_tenant_context(db, request.tenant_id)
    existing = _find_by_idempotency(db, request.tenant_id, request.idempotency_key)
    if existing:
        return _read_task(db, existing, include_detail=True)
    now = utc_now()
    agent = _resolve_role_agent(db, request.tenant_id, request.owner_business_role)
    row = WorkTask(
        tenant_id=request.tenant_id,
        idempotency_key=request.idempotency_key,
        source_type="manual",
        title=request.title.strip(),
        description=request.description.strip() or None,
        owner_business_role=request.owner_business_role,
        assignee_agent_id=agent.id if agent else None,
        assigned_by_user_id=user.id,
        priority=request.priority,
        risk_level=request.risk_level,
        scope_json=request.scope,
        due_at=request.due_at,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    _append_event(db, row=row, event_type="created", user=user, to_status="pending")
    db.commit()
    db.refresh(row)
    return _read_task(db, row, include_detail=True)


def create_tasks_batch(
    db: Session,
    *,
    request: WorkTaskBatchCreate,
    user: User,
) -> WorkTaskBatchResponse:
    """Atomically create an idempotent batch of read-only patrol tasks."""

    _require_tenant(user, request.tenant_id)
    set_tenant_context(db, request.tenant_id)
    item_keys = [item.item_key for item in request.items]
    if len(set(item_keys)) != len(item_keys):
        raise HTTPException(status_code=422, detail="Batch item keys must be unique")
    rows: list[WorkTask] = []
    created_count = 0
    now = utc_now()
    for item in request.items:
        _require_role_access(user, item.owner_business_role, creating=True)
        _validate_owner_role(item.owner_business_role)
        idempotency_key = _batch_task_key(request.batch_idempotency_key, item.item_key)
        existing = _find_by_idempotency(db, request.tenant_id, idempotency_key)
        if existing:
            rows.append(existing)
            continue
        agent = _resolve_role_agent(db, request.tenant_id, item.owner_business_role)
        row = WorkTask(
            tenant_id=request.tenant_id,
            idempotency_key=idempotency_key,
            source_type="batch_patrol",
            source_id=request.batch_idempotency_key,
            title=item.title.strip(),
            description=item.description.strip() or None,
            owner_business_role=item.owner_business_role,
            assignee_agent_id=agent.id if agent else None,
            assigned_by_user_id=user.id,
            priority=item.priority,
            risk_level=item.risk_level,
            scope_json=item.scope,
            input_json={"read_only_patrol": True, "batch_item_key": item.item_key},
            due_at=item.due_at,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        _append_event(
            db,
            row=row,
            event_type="batch_patrol_created",
            user=user,
            to_status="pending",
            detail={
                "batch_idempotency_key": request.batch_idempotency_key,
                "read_only_patrol": True,
            },
        )
        rows.append(row)
        created_count += 1
    db.commit()
    for row in rows:
        db.refresh(row)
    return WorkTaskBatchResponse(
        items=[_read_task(db, row, include_detail=True) for row in rows],
        created_count=created_count,
        existing_count=len(rows) - created_count,
    )


def create_linked_task(
    db: Session,
    *,
    tenant_id: str,
    idempotency_key: str,
    source_type: str,
    source_id: str,
    title: str,
    description: str,
    owner_business_role: str,
    assigned_by_user_id: str,
    assigned_by_business_role: str,
    priority: str = "normal",
    risk_level: str = "medium",
    due_at: Any | None = None,
    scope: dict[str, Any] | None = None,
    input_data: dict[str, Any] | None = None,
    evidence: list[WorkTaskEvidenceReference] | None = None,
) -> tuple[WorkTask, bool]:
    """Create an idempotent task inside the caller's transaction."""

    _validate_owner_role(owner_business_role)
    set_tenant_context(db, tenant_id)
    existing = _find_by_idempotency(db, tenant_id, idempotency_key)
    if existing:
        append_task_evidence(
            db,
            task=existing,
            evidence=evidence or [],
            actor_type="human",
            actor_id=assigned_by_user_id,
            actor_business_role=assigned_by_business_role,
        )
        return existing, False
    now = utc_now()
    agent = _resolve_role_agent(db, tenant_id, owner_business_role)
    row = WorkTask(
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        source_type=source_type,
        source_id=source_id,
        title=title.strip(),
        description=description.strip() or None,
        owner_business_role=owner_business_role,
        assignee_agent_id=agent.id if agent else None,
        assigned_by_user_id=assigned_by_user_id,
        priority=priority,
        risk_level=risk_level,
        scope_json=scope or {},
        input_json=input_data or {},
        due_at=due_at,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    db.add(
        WorkTaskEvent(
            tenant_id=tenant_id,
            task_id=row.id,
            event_type=f"created_from_{source_type}",
            actor_type="human",
            actor_id=assigned_by_user_id,
            actor_business_role=assigned_by_business_role,
            to_status="pending",
            detail_json={"source_id": source_id, "assignee_agent_id": row.assignee_agent_id},
        )
    )
    append_task_evidence(
        db,
        task=row,
        evidence=evidence or [],
        actor_type="human",
        actor_id=assigned_by_user_id,
        actor_business_role=assigned_by_business_role,
    )
    db.flush()
    return row, True


def append_task_evidence(
    db: Session,
    *,
    task: WorkTask,
    evidence: list[WorkTaskEvidenceReference],
    actor_type: str | None = None,
    actor_id: str | None = None,
    actor_business_role: str | None = None,
) -> int:
    """Append safe, idempotent evidence references to an existing unified task."""

    if not evidence:
        return 0
    set_tenant_context(db, task.tenant_id)
    created_count = 0
    created_sources: list[dict[str, str]] = []
    for item in evidence:
        existing = db.exec(
            select(WorkTaskEvidence).where(
                WorkTaskEvidence.tenant_id == task.tenant_id,
                WorkTaskEvidence.task_id == task.id,
                WorkTaskEvidence.source_type == item.source_type,
                WorkTaskEvidence.source_id == item.source_id,
            )
        ).first()
        if existing:
            continue
        db.add(
            WorkTaskEvidence(
                tenant_id=task.tenant_id,
                task_id=task.id,
                source_type=item.source_type,
                source_id=item.source_id,
                severity=item.severity,
                label=item.label,
                summary=item.summary,
                source_route=item.source_route,
                occurred_at=item.occurred_at,
            )
        )
        created_count += 1
        created_sources.append({"source_type": item.source_type, "source_id": item.source_id})
    if created_count and actor_type:
        db.add(
            WorkTaskEvent(
                tenant_id=task.tenant_id,
                task_id=task.id,
                event_type="evidence_linked",
                actor_type=actor_type,
                actor_id=actor_id,
                actor_business_role=actor_business_role,
                from_status=task.status,
                to_status=task.status,
                detail_json={
                    "evidence_count": created_count,
                    "sources": created_sources,
                },
            )
        )
    db.flush()
    return created_count


def create_report_follow_up(
    db: Session, *, command: ReportFollowUpCommand
) -> tuple[WorkTask, bool]:
    """Create or return one durable task without committing the caller's transaction."""

    _validate_owner_role(command.owner_business_role)
    set_tenant_context(db, command.tenant_id)
    idempotency_key = _report_follow_up_key(command)
    existing = _find_by_idempotency(db, command.tenant_id, idempotency_key)
    if existing:
        return existing, False
    now = utc_now()
    agent = _resolve_role_agent(db, command.tenant_id, command.owner_business_role)
    row = WorkTask(
        tenant_id=command.tenant_id,
        idempotency_key=idempotency_key,
        source_type="operations_report_follow_up",
        source_id=command.report_id,
        source_report_id=command.report_id,
        title=command.title.strip(),
        description=command.note.strip() or None,
        owner_business_role=command.owner_business_role,
        assignee_agent_id=agent.id if agent else None,
        assigned_by_user_id=command.created_by_user_id,
        priority=command.priority,
        risk_level=_risk_from_evidence(command.evidence),
        scope_json=dict(command.scope),
        input_json={"report_id": command.report_id, "evidence_count": len(command.evidence)},
        due_at=command.due_at,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    for evidence in command.evidence:
        db.add(
            WorkTaskEvidence(
                tenant_id=command.tenant_id,
                task_id=row.id,
                source_type=evidence.source_type,
                source_id=evidence.source_id,
                severity=evidence.severity,
                label=evidence.label,
                summary=evidence.summary,
                source_route=evidence.source_route,
                occurred_at=evidence.occurred_at,
            )
        )
    db.add(
        WorkTaskEvent(
            tenant_id=command.tenant_id,
            task_id=row.id,
            event_type="created_from_report",
            actor_type="human",
            actor_id=command.created_by_user_id,
            actor_business_role=command.created_by_business_role,
            to_status="pending",
            detail_json={
                "report_id": command.report_id,
                "evidence_count": len(command.evidence),
                "assignee_agent_id": row.assignee_agent_id,
            },
        )
    )
    db.flush()
    return row, True


def list_tasks(
    db: Session,
    *,
    tenant_id: str,
    user: User,
    owner_business_role: str | None = None,
    status: str | None = None,
) -> WorkTaskListResponse:
    _require_tenant(user, tenant_id)
    set_tenant_context(db, tenant_id)
    visible_role = _visible_role(user, owner_business_role)
    statement = select(WorkTask).where(WorkTask.tenant_id == tenant_id)
    if visible_role:
        statement = statement.where(WorkTask.owner_business_role == visible_role)
    if status:
        statement = statement.where(WorkTask.status == status)
    rows = db.exec(statement.order_by(WorkTask.created_at.desc()).limit(200)).all()
    all_visible = rows
    if status:
        summary_statement = select(WorkTask).where(WorkTask.tenant_id == tenant_id)
        if visible_role:
            summary_statement = summary_statement.where(WorkTask.owner_business_role == visible_role)
        all_visible = db.exec(summary_statement).all()
    return WorkTaskListResponse(
        items=[_read_task(db, row, include_detail=False) for row in rows],
        queues=_queue_summaries(all_visible, only_role=visible_role),
    )


def get_task(db: Session, *, tenant_id: str, task_id: str, user: User) -> WorkTaskRead:
    row = _load_task(db, tenant_id=tenant_id, task_id=task_id, user=user)
    return _read_task(db, row, include_detail=True)


def transition_task(
    db: Session, *, task_id: str, request: WorkTaskTransition, user: User
) -> WorkTaskRead:
    row = _load_task(db, tenant_id=request.tenant_id, task_id=task_id, user=user)
    if row.version != request.expected_version:
        raise HTTPException(status_code=409, detail="Task was changed; reload before retrying")
    target = _TRANSITIONS.get((row.status, request.action))
    if target is None:
        raise HTTPException(
            status_code=409,
            detail=f"Action {request.action} is not allowed while task is {row.status}",
        )
    if request.action in {"cancel", "archive"} and user.business_role not in _MANAGER_ROLES and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only a manager can cancel or archive tasks")
    if request.action == "takeover" and row.control_mode == "human":
        raise HTTPException(status_code=409, detail="Task is already under human control")
    if request.action == "return_to_agent" and row.control_mode != "human":
        raise HTTPException(status_code=409, detail="Only a human-controlled task can return to the agent")
    if request.action == "return_to_agent" and not row.assignee_agent_id:
        raise HTTPException(status_code=409, detail="Task has no active digital employee assignee")
    now = utc_now()
    previous = row.status
    row.status = target
    row.version += 1
    row.updated_at = now
    if request.action in {"start", "rework", "takeover"}:
        row.control_mode = "human"
        row.cancel_requested = request.action == "takeover"
        row.taken_over_by_user_id = user.id
        row.taken_over_at = now
        row.execution_generation += 1
        row.lease_owner = None
        row.lease_expires_at = None
        row.next_attempt_at = None
    elif request.action in {"return_to_agent", "retry"}:
        row.control_mode = "agent"
        row.cancel_requested = False
        row.taken_over_by_user_id = None
        row.taken_over_at = None
        row.next_attempt_at = now
        row.last_error_code = None
        row.last_error_message = None
        row.completed_at = None
    elif request.action == "cancel":
        row.cancel_requested = True
        row.execution_generation += 1
        row.lease_owner = None
        row.lease_expires_at = None
        row.next_attempt_at = None
    if target == "in_progress" and row.started_at is None:
        row.started_at = now
    if target == "completed":
        row.completed_at = now
    elif request.action in {"retry", "rework"}:
        row.completed_at = None
    db.add(row)
    _append_event(
        db,
        row=row,
        event_type=request.action,
        user=user,
        from_status=previous,
        to_status=target,
        detail={"note": request.note.strip()} if request.note.strip() else {},
    )
    db.commit()
    db.refresh(row)
    return _read_task(db, row, include_detail=True)


def _load_task(db: Session, *, tenant_id: str, task_id: str, user: User) -> WorkTask:
    _require_tenant(user, tenant_id)
    set_tenant_context(db, tenant_id)
    row = db.exec(
        select(WorkTask).where(WorkTask.tenant_id == tenant_id, WorkTask.id == task_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _require_role_access(user, row.owner_business_role)
    return row


def _visible_role(user: User, requested_role: str | None) -> str | None:
    if user.business_role in _MANAGER_ROLES or user.role == "admin":
        if requested_role:
            _validate_owner_role(requested_role)
        return requested_role
    role = user.business_role or ""
    if role not in _TASK_OWNER_ROLES:
        raise HTTPException(status_code=403, detail="Task center is unavailable for this role")
    if requested_role and requested_role != role:
        raise HTTPException(status_code=403, detail="Cannot access another role queue")
    return role


def _require_role_access(user: User, owner_role: str, *, creating: bool = False) -> None:
    if user.business_role in _MANAGER_ROLES or user.role == "admin":
        return
    if user.business_role != owner_role:
        verb = "create for" if creating else "access"
        raise HTTPException(status_code=403, detail=f"Cannot {verb} another role queue")


def _require_tenant(user: User, tenant_id: str) -> None:
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant task access is forbidden")


def _validate_owner_role(role: str) -> None:
    if role not in _TASK_OWNER_ROLES:
        raise HTTPException(status_code=422, detail="Unsupported task owner business role")


def _find_by_idempotency(db: Session, tenant_id: str, key: str) -> WorkTask | None:
    return db.exec(
        select(WorkTask).where(WorkTask.tenant_id == tenant_id, WorkTask.idempotency_key == key)
    ).first()


def _batch_task_key(batch_key: str, item_key: str) -> str:
    canonical = json.dumps(
        {"batch": batch_key.strip(), "item": item_key.strip()},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"batch-patrol:{hashlib.sha256(canonical.encode()).hexdigest()}"


def _report_follow_up_key(command: ReportFollowUpCommand) -> str:
    canonical = json.dumps(
        {
            "report_id": command.report_id,
            "title": " ".join(command.title.lower().split()),
            "owner_business_role": command.owner_business_role,
            "evidence": sorted((item.source_type, item.source_id) for item in command.evidence),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"report-follow-up:{hashlib.sha256(canonical.encode()).hexdigest()}"


def _risk_from_evidence(evidence: list[Any]) -> str:
    # Report evidence is already redacted. Critical/high labels elevate the task;
    # otherwise management follow-ups remain medium risk and never auto-execute.
    severities = {str(item.severity).lower() for item in evidence}
    if "critical" in severities:
        return "critical"
    if "high" in severities:
        return "high"
    return "medium"


def _resolve_role_agent(db: Session, tenant_id: str, role: str) -> AgentProfile | None:
    agents = db.exec(
        select(AgentProfile).where(
            AgentProfile.tenant_id == tenant_id,
            AgentProfile.status == "active",
        )
    ).all()
    for agent in agents:
        if str((agent.metadata_json or {}).get("business_role", "")) == role:
            return agent
    keywords = {
        "operations_supervisor": ("运营主管", "主管"),
        "after_sales_specialist": ("售后", "客服"),
        "listing_compliance_specialist": ("listing", "合规"),
        "logistics_exception_specialist": ("物流", "履约"),
        "advertising_inspection_specialist": ("广告", "投放"),
        "designer": ("美工", "设计"),
        "procurement_specialist": ("采购",),
    }.get(role)
    if not keywords:
        return None
    return next((agent for agent in agents if any(key in agent.name.lower() for key in keywords)), None)


def _append_event(
    db: Session,
    *,
    row: WorkTask,
    event_type: str,
    user: User,
    from_status: str | None = None,
    to_status: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        WorkTaskEvent(
            tenant_id=row.tenant_id,
            task_id=row.id,
            event_type=event_type,
            actor_type="human",
            actor_id=user.id,
            actor_business_role=user.business_role,
            from_status=from_status,
            to_status=to_status,
            detail_json=detail or {},
        )
    )


def _read_task(db: Session, row: WorkTask, *, include_detail: bool) -> WorkTaskRead:
    agent_name = None
    if row.assignee_agent_id:
        agent = db.get(AgentProfile, row.assignee_agent_id)
        agent_name = agent.name if agent else None
    evidence: list[WorkTaskEvidenceRead] = []
    events: list[WorkTaskEventRead] = []
    runs: list[WorkTaskRunRead] = []
    if include_detail:
        evidence = [
            WorkTaskEvidenceRead(
                id=item.id,
                source_type=item.source_type,
                source_id=item.source_id,
                severity=item.severity,
                label=item.label,
                summary=item.summary,
                source_route=item.source_route,
                occurred_at=item.occurred_at,
            )
            for item in db.exec(
                select(WorkTaskEvidence)
                .where(WorkTaskEvidence.task_id == row.id)
                .order_by(WorkTaskEvidence.occurred_at.desc())
            ).all()
        ]
        events = [
            WorkTaskEventRead(
                id=item.id,
                event_type=item.event_type,
                actor_type=item.actor_type,
                actor_id=item.actor_id,
                actor_business_role=item.actor_business_role,
                from_status=item.from_status,
                to_status=item.to_status,
                detail=item.detail_json,
                created_at=item.created_at,
            )
            for item in db.exec(
                select(WorkTaskEvent)
                .where(WorkTaskEvent.task_id == row.id)
                .order_by(WorkTaskEvent.created_at)
            ).all()
        ]
        run_rows = db.exec(
            select(WorkTaskRun)
            .where(WorkTaskRun.task_id == row.id)
            .order_by(WorkTaskRun.attempt_no.desc())
        ).all()
        snapshot_ids = [item.execution_snapshot_id for item in run_rows if item.execution_snapshot_id]
        snapshots = {
            item.id: item
            for item in (
                db.exec(
                    select(WorkTaskExecutionSnapshot).where(
                        WorkTaskExecutionSnapshot.id.in_(snapshot_ids)
                    )
                ).all()
                if snapshot_ids
                else []
            )
        }
        runs = [
            WorkTaskRunRead(
                id=item.id,
                attempt_no=item.attempt_no,
                generation=item.generation,
                agent_id=item.agent_id,
                session_id=item.session_id,
                service_identity_id=item.service_identity_id,
                execution_snapshot_id=item.execution_snapshot_id,
                snapshot_digest=item.snapshot_digest,
                execution_snapshot=_snapshot_read(snapshots.get(item.execution_snapshot_id or "")),
                status=item.status,
                execution_mode=item.execution_mode,
                result_summary=item.result_summary,
                error_code=item.error_code,
                error_message=item.error_message,
                trace=item.trace_json,
                started_at=item.started_at,
                finished_at=item.finished_at,
            )
            for item in run_rows
        ]
    return WorkTaskRead(
        id=row.id,
        tenant_id=row.tenant_id,
        source_type=row.source_type,
        source_id=row.source_id,
        source_report_id=row.source_report_id,
        title=row.title,
        description=row.description,
        owner_business_role=row.owner_business_role,
        owner_role_label=business_role_label(row.owner_business_role),
        assignee_agent_id=row.assignee_agent_id,
        assignee_agent_name=agent_name,
        priority=row.priority,
        risk_level=row.risk_level,
        status=row.status,
        control_mode=row.control_mode,
        cancel_requested=row.cancel_requested,
        execution_generation=row.execution_generation,
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        next_attempt_at=row.next_attempt_at,
        lease_expires_at=row.lease_expires_at,
        latest_session_id=row.latest_session_id,
        taken_over_by_user_id=row.taken_over_by_user_id,
        taken_over_at=row.taken_over_at,
        last_error_code=row.last_error_code,
        last_error_message=row.last_error_message,
        result_summary=row.result_summary,
        scope=row.scope_json,
        due_at=row.due_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        evidence=evidence,
        events=events,
        runs=runs,
    )


def _snapshot_read(snapshot: WorkTaskExecutionSnapshot | None) -> dict[str, Any] | None:
    """Expose version receipts only; frozen prompts/content remain server-side."""

    if snapshot is None:
        return None
    identity = dict(snapshot.service_identity_snapshot_json or {})
    agent = dict(snapshot.agent_snapshot_json or {})
    return {
        "id": snapshot.id,
        "snapshot_digest": snapshot.snapshot_digest,
        "agent": {
            "agent_id": agent.get("agent_id"),
            "name": agent.get("name"),
            "business_role": agent.get("business_role"),
            "profile_digest": agent.get("profile_digest"),
        },
        "service_identity": {
            "service_identity_id": identity.get("service_identity_id"),
            "provider": identity.get("provider"),
            "application_name": identity.get("application_name"),
            "client_id_fingerprint": identity.get("client_id_fingerprint"),
        },
        "sops": [
            {
                "skill_id": item.get("skill_id"),
                "name": item.get("name"),
                "version": item.get("version"),
                "content_digest": item.get("content_digest"),
            }
            for item in snapshot.sop_snapshots_json
        ],
        "knowledge_bases": [
            {
                "knowledge_base_id": item.get("knowledge_base_id"),
                "knowledge_base_version_id": item.get("knowledge_base_version_id"),
                "name": item.get("name"),
                "version": item.get("version"),
                "metadata_digest": item.get("metadata_digest"),
            }
            for item in snapshot.knowledge_snapshots_json
        ],
        "tools": [
            {
                "tool_id": item.get("tool_id"),
                "name": item.get("display_name") or item.get("name"),
                "content_digest": item.get("content_digest"),
            }
            for item in snapshot.tool_snapshots_json
        ],
        "created_at": snapshot.created_at.isoformat(),
    }


def _queue_summaries(
    rows: list[WorkTask], *, only_role: str | None = None
) -> list[WorkTaskQueueSummary]:
    now = utc_now()
    grouped: dict[str, Counter[str]] = {}
    overdue: Counter[str] = Counter()
    for row in rows:
        grouped.setdefault(row.owner_business_role, Counter())[row.status] += 1
        if row.status in _OPEN_STATUSES and row.due_at and row.due_at < now:
            overdue[row.owner_business_role] += 1
    return [
        WorkTaskQueueSummary(
            business_role=role,
            label=business_role_label(role),
            pending=grouped.get(role, Counter())["pending"],
            in_progress=grouped.get(role, Counter())["in_progress"],
            waiting_input=grouped.get(role, Counter())["waiting_input"],
            review=grouped.get(role, Counter())["review"],
            overdue=overdue[role],
            total_open=sum(grouped.get(role, Counter())[status] for status in _OPEN_STATUSES),
        )
        for role in BUSINESS_ROLE_BY_KEY
        if role in _TASK_OWNER_ROLES and (only_role is None or role == only_role)
    ]
