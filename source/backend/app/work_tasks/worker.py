from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import case, or_
from sqlmodel import Session, select

from app.agents.releases import AgentReleaseError, verify_agent_release_for_execution
from app.config import Settings, get_settings
from app.core import AgentLoop
from app.db import engine
from app.db.database import set_tenant_context
from app.db.models import (
    AgentProfile,
    AgentServiceIdentity,
    ChatSession,
    WorkTask,
    WorkTaskEvent,
    WorkTaskEvidence,
    WorkTaskExecutionSnapshot,
    WorkTaskRun,
    new_id,
    utc_now,
)
from app.session.session_schema import ChatTurnRequest, ChatTurnResponse
from app.work_tasks.m2m import (
    ServiceIdentityError,
    ServiceTokenReceipt,
    authenticate_service_identity,
)
from app.work_tasks.snapshots import (
    WorkTaskSnapshotError,
    build_execution_snapshot,
    execution_snapshot_digest,
)

logger = logging.getLogger(__name__)

_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None


@dataclass(frozen=True)
class WorkTaskClaim:
    tenant_id: str
    task_id: str
    run_id: str
    session_id: str
    agent_id: str
    service_identity_id: str
    execution_snapshot_id: str
    snapshot_digest: str
    assigned_by_user_id: str
    generation: int
    attempt_no: int
    title: str
    description: str
    scope: dict[str, Any]
    input_data: dict[str, Any]
    evidence: tuple[dict[str, str], ...]
    execution_mode: str
    persona_prompt: str
    harness_max_actions: int
    sop_snapshots: tuple[dict[str, Any], ...]
    capability_snapshot: dict[str, Any]


@dataclass(frozen=True)
class WorkTaskOutcome:
    disposition: str
    summary: str = ""
    error_code: str | None = None
    error_message: str | None = None
    trace: dict[str, Any] | None = None


def run_work_task_cycle(
    *,
    db_engine=None,
    settings: Settings | None = None,
    source_type: str | None = None,
) -> int:
    resolved = settings or get_settings()
    use_engine = db_engine or engine
    processed = 0
    for tenant_id in resolved.work_task_execution_tenant_id_list:
        _recover_stale(use_engine, tenant_id, resolved)
        for _ in range(max(1, resolved.work_task_execution_batch_size)):
            claim = _claim_one(use_engine, tenant_id, resolved, source_type=source_type)
            if claim is None:
                break
            processed += 1
            try:
                outcome = _execute_claim(use_engine, claim)
            except Exception as exc:  # isolate one employee/task from the daemon
                logger.exception("Digital employee work-task execution failed unexpectedly")
                outcome = WorkTaskOutcome(
                    disposition="retryable_failure",
                    error_code="work_task_executor_error",
                    error_message=str(exc)[:1000] or type(exc).__name__,
                )
            _record_outcome(use_engine, claim, outcome)
    return processed


def run_work_task_daemon(*, db_engine=None, settings: Settings | None = None) -> None:
    resolved = settings or get_settings()
    interval = max(0.2, resolved.work_task_execution_poll_seconds)
    while not _stop_event.is_set():
        try:
            run_work_task_cycle(db_engine=db_engine, settings=resolved)
        except Exception:
            logger.exception("Work-task execution daemon polling failed")
        if _stop_event.wait(interval):
            return


def start_work_task_daemon(*, db_engine=None, settings: Settings | None = None) -> bool:
    global _worker_thread
    resolved = settings or get_settings()
    if not resolved.work_task_execution_enabled:
        return False
    if not resolved.work_task_execution_tenant_id_list:
        logger.warning("Work-task execution is enabled but WORK_TASK_EXECUTION_TENANT_IDS is empty")
        return False
    if resolved.work_task_execution_mode.strip().lower() not in {"sandbox", "live"}:
        raise RuntimeError("WORK_TASK_EXECUTION_MODE must be sandbox or live")
    if _worker_thread and _worker_thread.is_alive():
        return True
    _stop_event.clear()
    _worker_thread = threading.Thread(
        target=run_work_task_daemon,
        kwargs={"db_engine": db_engine, "settings": resolved},
        name="staffdeck-work-task-execution",
        daemon=True,
    )
    _worker_thread.start()
    return True


def stop_work_task_daemon(timeout_seconds: float = 5.0) -> bool:
    global _worker_thread
    _stop_event.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=max(0.0, timeout_seconds))
    stopped = not (_worker_thread and _worker_thread.is_alive())
    if stopped:
        _worker_thread = None
    return stopped


def _claim_one(
    db_engine,
    tenant_id: str,
    settings: Settings,
    *,
    source_type: str | None = None,
) -> WorkTaskClaim | None:
    now = utc_now()
    mode = settings.work_task_execution_mode.strip().lower()
    with Session(db_engine) as db:
        set_tenant_context(db, tenant_id)
        priority_order = case(
            (WorkTask.priority == "urgent", 0),
            (WorkTask.priority == "high", 1),
            (WorkTask.priority == "normal", 2),
            else_=3,
        )
        statement = (
            select(WorkTask)
            .where(
                WorkTask.tenant_id == tenant_id,
                WorkTask.status == "pending",
                WorkTask.control_mode == "agent",
                WorkTask.cancel_requested.is_(False),
                WorkTask.assignee_agent_id.is_not(None),
                WorkTask.attempt_count < WorkTask.max_attempts,
                or_(WorkTask.next_attempt_at.is_(None), WorkTask.next_attempt_at <= now),
            )
            .order_by(priority_order, WorkTask.due_at, WorkTask.created_at)
            .limit(1)
        )
        if source_type:
            statement = statement.where(WorkTask.source_type == source_type)
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        task = db.exec(statement).first()
        if task is None or not task.assignee_agent_id:
            return None
        agent = db.exec(
            select(AgentProfile).where(
                AgentProfile.tenant_id == tenant_id,
                AgentProfile.id == task.assignee_agent_id,
                AgentProfile.status == "active",
                AgentProfile.is_overall.is_(False),
            )
        ).first()
        if agent is None:
            task.status = "failed"
            task.last_error_code = "assigned_agent_unavailable"
            task.last_error_message = "绑定的岗位数字员工不存在或已停用"
            task.version += 1
            task.updated_at = now
            db.add(task)
            _add_event(
                db,
                task,
                "agent_unavailable",
                from_status="pending",
                to_status="failed",
                detail={"agent_id": task.assignee_agent_id},
            )
            db.commit()
            return None

        service_identity = db.exec(
            select(AgentServiceIdentity).where(
                AgentServiceIdentity.tenant_id == tenant_id,
                AgentServiceIdentity.agent_id == agent.id,
                AgentServiceIdentity.business_role == task.owner_business_role,
                AgentServiceIdentity.status == "active",
            )
        ).first()
        if service_identity is None:
            task.status = "failed"
            task.last_error_code = "service_identity_unavailable"
            task.last_error_message = "岗位数字员工缺少已启用的独立 Casdoor M2M 服务身份"
            task.version += 1
            task.updated_at = now
            db.add(task)
            _add_event(
                db,
                task,
                "service_identity_unavailable",
                from_status="pending",
                to_status="failed",
                detail={"agent_id": agent.id, "business_role": task.owner_business_role},
            )
            db.commit()
            return None

        try:
            agent_release = verify_agent_release_for_execution(db, agent)
        except AgentReleaseError as exc:
            task.status = "failed"
            task.last_error_code = "agent_release_unavailable"
            task.last_error_message = str(exc)[:1000]
            task.version += 1
            task.updated_at = now
            db.add(task)
            _add_event(
                db,
                task,
                "agent_release_unavailable",
                from_status="pending",
                to_status="failed",
                detail={"agent_id": agent.id, "reason": str(exc)[:500]},
            )
            db.commit()
            return None

        task.max_attempts = max(1, min(task.max_attempts or settings.work_task_execution_max_attempts, 10))
        task.attempt_count += 1
        task.execution_generation += 1
        task.status = "in_progress"
        task.started_at = task.started_at or now
        task.next_attempt_at = None
        task.lease_owner = f"work-task-worker-{uuid4().hex[:12]}"
        task.lease_expires_at = now + timedelta(seconds=max(30, settings.work_task_execution_lease_seconds))
        task.last_error_code = None
        task.last_error_message = None
        task.version += 1
        task.updated_at = now

        session = ChatSession(
            id=new_id("session"),
            tenant_id=tenant_id,
            user_id=task.assigned_by_user_id,
            agent_id=agent.id,
            title=f"统一任务：{task.title}"[:200],
            status="active",
            channel="work_task",
        )
        run = WorkTaskRun(
            tenant_id=tenant_id,
            task_id=task.id,
            attempt_no=task.attempt_count,
            generation=task.execution_generation,
            agent_id=agent.id,
            session_id=session.id,
            service_identity_id=service_identity.id,
            status="running",
            execution_mode=mode,
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        try:
            snapshot = build_execution_snapshot(
                db,
                task=task,
                run=run,
                agent=agent,
                agent_release=agent_release,
                service_identity=service_identity,
            )
        except WorkTaskSnapshotError as exc:
            task.status = "failed"
            task.control_mode = "agent"
            task.last_error_code = "execution_snapshot_failed"
            task.last_error_message = str(exc)[:1000]
            task.lease_owner = None
            task.lease_expires_at = None
            task.version += 1
            task.updated_at = now
            db.add(task)
            _add_event(
                db,
                task,
                "execution_snapshot_failed",
                from_status="pending",
                to_status="failed",
                detail={"agent_id": agent.id, "service_identity_id": service_identity.id},
            )
            db.commit()
            return None
        run.execution_snapshot_id = snapshot.id
        run.snapshot_digest = snapshot.snapshot_digest
        task.latest_session_id = session.id
        evidence_rows = db.exec(
            select(WorkTaskEvidence)
            .where(WorkTaskEvidence.tenant_id == tenant_id, WorkTaskEvidence.task_id == task.id)
            .order_by(WorkTaskEvidence.occurred_at.desc())
            .limit(20)
        ).all()
        db.add(session)
        db.add(task)
        # These PostgreSQL foreign keys are migration-level constraints rather
        # than ORM relationships. Flush parent rows explicitly so SQLAlchemy's
        # unit-of-work ordering cannot insert the append-only snapshot first.
        db.flush()
        db.add(run)
        db.flush()
        db.add(snapshot)
        _add_event(
            db,
            task,
            "agent_claimed",
            from_status="pending",
            to_status="in_progress",
            detail={
                "run_id": run.id,
                "session_id": session.id,
                "attempt_no": task.attempt_count,
                "generation": task.execution_generation,
                "execution_mode": mode,
                "service_identity_id": service_identity.id,
                "execution_snapshot_id": snapshot.id,
                "snapshot_digest": snapshot.snapshot_digest,
                "agent_release_id": agent_release.id,
                "agent_release_version": agent_release.version,
                "agent_release_digest": agent_release.snapshot_digest,
            },
            actor_id=agent.id,
        )
        db.commit()
        return WorkTaskClaim(
            tenant_id=tenant_id,
            task_id=task.id,
            run_id=run.id,
            session_id=session.id,
            agent_id=agent.id,
            service_identity_id=service_identity.id,
            execution_snapshot_id=snapshot.id,
            snapshot_digest=snapshot.snapshot_digest,
            assigned_by_user_id=task.assigned_by_user_id,
            generation=task.execution_generation,
            attempt_no=task.attempt_count,
            title=task.title,
            description=task.description or "",
            scope=dict(task.scope_json or {}),
            input_data=dict(task.input_json or {}),
            evidence=tuple(
                {"label": item.label, "summary": item.summary, "severity": item.severity}
                for item in evidence_rows
            ),
            execution_mode=mode,
            persona_prompt=str(snapshot.agent_snapshot_json.get("rendered_persona") or ""),
            harness_max_actions=int(snapshot.agent_snapshot_json.get("harness_max_actions") or 0),
            sop_snapshots=tuple(dict(item) for item in snapshot.sop_snapshots_json),
            capability_snapshot=dict(snapshot.capability_snapshot_json),
        )


def _execute_claim(db_engine, claim: WorkTaskClaim) -> WorkTaskOutcome:
    identity, snapshot = _load_execution_security_context(db_engine, claim)
    if identity is None or snapshot is None:
        return WorkTaskOutcome(
            disposition="terminal_failure",
            error_code="execution_security_context_invalid",
            error_message="任务快照或岗位服务身份已失效",
        )
    try:
        receipt = authenticate_service_identity(identity, get_settings())
    except ServiceIdentityError as exc:
        _record_identity_verification(db_engine, claim, error_code=exc.code)
        return WorkTaskOutcome(
            disposition=(
                "retryable_failure"
                if exc.code == "service_token_exchange_failed"
                else "terminal_failure"
            ),
            error_code=exc.code,
            error_message=str(exc),
            trace={"service_identity": _identity_trace(identity, None, exc.code)},
        )
    _record_identity_verification(db_engine, claim, receipt=receipt)
    identity_trace = _identity_trace(identity, receipt, None)
    if not _claim_is_current(db_engine, claim):
        return WorkTaskOutcome(
            disposition="stale",
            error_code="execution_superseded",
            error_message="执行身份、任务控制权或执行代际已变化",
            trace={"service_identity": identity_trace},
        )
    if claim.execution_mode == "sandbox":
        replay_input = claim.input_data if claim.input_data.get("execution_mode") == "mock_replay" else None
        if replay_input is not None:
            replay_trace = {
                "mode": "sandbox",
                "execution_mode": "mock_replay",
                "sop_id": replay_input.get("sop_id"),
                "steps": [
                    {"type": "knowledge_retrieval", "refs": replay_input.get("knowledge_refs", [])},
                    {
                        "type": "tool_call",
                        "tool_name": replay_input.get("tool_name"),
                        "source": "mock",
                        "external_write": False,
                    },
                    {"type": "evidence_attached", "count": len(claim.evidence)},
                    {"type": "human_follow_up", "status": "pending_review"},
                ],
                "snapshot_digest": claim.snapshot_digest,
                "service_identity": identity_trace,
            }
            return WorkTaskOutcome(
                disposition="succeeded",
                summary=f"[Sandbox Mock] {claim.title} 已完成只读回放，等待人工复核。",
                trace=replay_trace,
            )
        return WorkTaskOutcome(
            disposition="succeeded",
            summary=f"[Sandbox] {claim.title} 已由岗位数字员工完成初步分析，等待人工复核。",
            trace={
                "mode": "sandbox",
                "steps": ["读取任务范围", "核对来源证据", "生成处理建议", "提交人工复核"],
                "evidence_count": len(claim.evidence),
                "snapshot_digest": claim.snapshot_digest,
                "service_identity": identity_trace,
            },
        )

    phases: list[str] = []
    result: ChatTurnResponse | None = None
    with Session(db_engine) as db:
        set_tenant_context(db, claim.tenant_id)
        request = ChatTurnRequest(
            tenant_id=claim.tenant_id,
            session_id=claim.session_id,
            agent_id=claim.agent_id,
            client_turn_id=claim.run_id,
            user_id=claim.assigned_by_user_id,
            message=_work_task_message(claim),
            channel="work_task",
            interaction_mode="scheduled_task",
            context_injection=(
                "这是统一任务中心派发的内部工作任务。遵守当前员工权限与现有审批门禁；"
                "不得绕过高风险操作审批。若信息不足，明确列出需要人工补充的材料。"
            ),
            message_visibility="internal",
            forced_sop_snapshots=[dict(item) for item in claim.sop_snapshots],
            forced_persona_prompt=claim.persona_prompt,
            forced_harness_max_actions=claim.harness_max_actions,
            forced_capability_snapshot=dict(claim.capability_snapshot),
        )
        for item in AgentLoop(db).handle_turn_stream(request):
            event = str(item.get("event") or "")
            data = item.get("data")
            if isinstance(data, dict):
                phase = data.get("phase")
                if isinstance(phase, str) and phase and phase not in phases and len(phases) < 50:
                    phases.append(phase)
            if event in {"complete", "done"} and isinstance(data, dict):
                result = ChatTurnResponse.model_validate(data)
            if not _claim_is_current(db_engine, claim):
                return WorkTaskOutcome(
                    disposition="stale",
                    error_code="execution_superseded",
                    error_message="执行已被人工接管、取消或新一代任务替代",
                    trace={"phases": phases, "service_identity": identity_trace},
                )
    if result is None:
        return WorkTaskOutcome(
            disposition="retryable_failure",
            error_code="agent_incomplete_response",
            error_message="数字员工执行未返回完整结果",
            trace={"phases": phases, "service_identity": identity_trace},
        )
    return WorkTaskOutcome(
        disposition="succeeded",
        summary=result.reply[:2000],
        trace={
            "phases": phases,
            "session_id": claim.session_id,
            "snapshot_digest": claim.snapshot_digest,
            "service_identity": identity_trace,
        },
    )


def _record_outcome(db_engine, claim: WorkTaskClaim, outcome: WorkTaskOutcome) -> None:
    now = utc_now()
    with Session(db_engine) as db:
        set_tenant_context(db, claim.tenant_id)
        statement = select(WorkTask).where(
            WorkTask.tenant_id == claim.tenant_id,
            WorkTask.id == claim.task_id,
        )
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            statement = statement.with_for_update()
        task = db.exec(statement).one()
        run = db.exec(
            select(WorkTaskRun).where(
                WorkTaskRun.tenant_id == claim.tenant_id,
                WorkTaskRun.id == claim.run_id,
            )
        ).one()
        if (
            task.execution_generation != claim.generation
            or task.status != "in_progress"
            or task.control_mode != "agent"
            or task.cancel_requested
        ):
            if run.status == "running":
                run.status = "stale"
                run.error_code = "stale_outcome_ignored"
                run.error_message = "任务控制权或执行代际已变化，旧结果未写入任务"
                run.trace_json = dict(outcome.trace or {})
                run.finished_at = now
                run.updated_at = now
                db.add(run)
            _add_event(
                db,
                task,
                "stale_outcome_ignored",
                detail={"run_id": claim.run_id, "claim_generation": claim.generation},
                actor_id=claim.agent_id,
            )
            db.commit()
            return

        task.lease_owner = None
        task.lease_expires_at = None
        task.updated_at = now
        task.last_error_code = outcome.error_code
        task.last_error_message = (outcome.error_message or "")[:1000] or None
        run.result_summary = outcome.summary[:2000] or None
        run.error_code = outcome.error_code
        run.error_message = task.last_error_message
        run.trace_json = dict(outcome.trace or {})
        run.finished_at = now
        run.updated_at = now
        previous = task.status

        if outcome.disposition == "succeeded":
            task.status = "review"
            task.result_summary = outcome.summary[:2000] or None
            run.status = "succeeded"
            event_type = "agent_submitted_review"
        elif outcome.disposition == "retryable_failure" and task.attempt_count < task.max_attempts:
            task.status = "pending"
            task.next_attempt_at = now + timedelta(seconds=min(300, 5 * (2 ** max(0, task.attempt_count - 1))))
            run.status = "retrying"
            event_type = "agent_retry_scheduled"
        elif outcome.disposition == "stale":
            run.status = "stale"
            event_type = "stale_outcome_ignored"
        else:
            task.status = "failed"
            run.status = "failed"
            event_type = "agent_execution_failed"
        task.version += 1
        db.add(task)
        db.add(run)
        _add_event(
            db,
            task,
            event_type,
            from_status=previous,
            to_status=task.status,
            detail={
                "run_id": run.id,
                "attempt_no": run.attempt_no,
                "error_code": outcome.error_code,
                "next_attempt_at": task.next_attempt_at.isoformat() if task.next_attempt_at else None,
            },
            actor_id=claim.agent_id,
        )
        db.commit()


def _recover_stale(db_engine, tenant_id: str, settings: Settings) -> int:
    now = utc_now()
    recovered = 0
    with Session(db_engine) as db:
        set_tenant_context(db, tenant_id)
        statement = select(WorkTask).where(
            WorkTask.tenant_id == tenant_id,
            WorkTask.status == "in_progress",
            WorkTask.control_mode == "agent",
            WorkTask.lease_expires_at.is_not(None),
            WorkTask.lease_expires_at <= now,
        )
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        for task in db.exec(statement.limit(max(1, settings.work_task_execution_batch_size))).all():
            task.execution_generation += 1
            task.lease_owner = None
            task.lease_expires_at = None
            previous = task.status
            if task.attempt_count < task.max_attempts and not task.cancel_requested:
                task.status = "pending"
                task.next_attempt_at = now
                event_type = "expired_lease_requeued"
            else:
                task.status = "failed"
                task.last_error_code = "execution_lease_expired"
                task.last_error_message = "数字员工执行租约过期且重试次数已耗尽"
                event_type = "expired_lease_failed"
            task.version += 1
            task.updated_at = now
            running = db.exec(
                select(WorkTaskRun).where(
                    WorkTaskRun.tenant_id == tenant_id,
                    WorkTaskRun.task_id == task.id,
                    WorkTaskRun.status == "running",
                )
            ).all()
            for run in running:
                run.status = "stale"
                run.error_code = "execution_lease_expired"
                run.error_message = "Worker lease expired before a fenced outcome was committed"
                run.finished_at = now
                run.updated_at = now
                db.add(run)
            db.add(task)
            _add_event(
                db,
                task,
                event_type,
                from_status=previous,
                to_status=task.status,
                detail={"new_generation": task.execution_generation},
            )
            recovered += 1
        if recovered:
            db.commit()
    return recovered


def _claim_is_current(db_engine, claim: WorkTaskClaim) -> bool:
    with Session(db_engine) as db:
        set_tenant_context(db, claim.tenant_id)
        task = db.exec(
            select(WorkTask).where(
                WorkTask.tenant_id == claim.tenant_id,
                WorkTask.id == claim.task_id,
            )
        ).first()
        agent = db.exec(
            select(AgentProfile).where(
                AgentProfile.tenant_id == claim.tenant_id,
                AgentProfile.id == claim.agent_id,
                AgentProfile.status == "active",
            )
        ).first()
        identity = db.exec(
            select(AgentServiceIdentity).where(
                AgentServiceIdentity.tenant_id == claim.tenant_id,
                AgentServiceIdentity.id == claim.service_identity_id,
                AgentServiceIdentity.agent_id == claim.agent_id,
                AgentServiceIdentity.status == "active",
            )
        ).first()
        return bool(
            task
            and agent
            and identity
            and task.execution_generation == claim.generation
            and task.status == "in_progress"
            and task.control_mode == "agent"
            and not task.cancel_requested
        )


def _load_execution_security_context(
    db_engine, claim: WorkTaskClaim
) -> tuple[AgentServiceIdentity | None, WorkTaskExecutionSnapshot | None]:
    with Session(db_engine) as db:
        set_tenant_context(db, claim.tenant_id)
        identity = db.exec(
            select(AgentServiceIdentity).where(
                AgentServiceIdentity.tenant_id == claim.tenant_id,
                AgentServiceIdentity.id == claim.service_identity_id,
                AgentServiceIdentity.agent_id == claim.agent_id,
                AgentServiceIdentity.status == "active",
            )
        ).first()
        snapshot = db.exec(
            select(WorkTaskExecutionSnapshot).where(
                WorkTaskExecutionSnapshot.tenant_id == claim.tenant_id,
                WorkTaskExecutionSnapshot.id == claim.execution_snapshot_id,
                WorkTaskExecutionSnapshot.run_id == claim.run_id,
                WorkTaskExecutionSnapshot.task_id == claim.task_id,
                WorkTaskExecutionSnapshot.agent_id == claim.agent_id,
                WorkTaskExecutionSnapshot.service_identity_id == claim.service_identity_id,
            )
        ).first()
        if (
            identity is None
            or snapshot is None
            or snapshot.snapshot_digest != claim.snapshot_digest
            or execution_snapshot_digest(snapshot) != claim.snapshot_digest
        ):
            return None, None
        return identity, snapshot


def _record_identity_verification(
    db_engine,
    claim: WorkTaskClaim,
    *,
    receipt: ServiceTokenReceipt | None = None,
    error_code: str | None = None,
) -> None:
    with Session(db_engine) as db:
        set_tenant_context(db, claim.tenant_id)
        identity = db.exec(
            select(AgentServiceIdentity).where(
                AgentServiceIdentity.tenant_id == claim.tenant_id,
                AgentServiceIdentity.id == claim.service_identity_id,
            )
        ).first()
        if identity is None:
            return
        identity.last_error_code = error_code
        if receipt is not None:
            identity.last_verified_at = utc_now()
            identity.last_verified_subject = receipt.subject[:255]
        identity.updated_at = utc_now()
        db.add(identity)
        db.commit()


def _identity_trace(
    identity: AgentServiceIdentity,
    receipt: ServiceTokenReceipt | None,
    error_code: str | None,
) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "service_identity_id": identity.id,
        "provider": identity.provider,
        "application": f"{identity.application_owner}/{identity.application_name}",
        "client_id_fingerprint": identity.client_id_fingerprint,
        "status": "verified" if receipt else "failed",
    }
    if receipt is not None:
        trace.update(
            {
                "subject": receipt.subject,
                "audience": list(receipt.audience),
                "expires_at": receipt.expires_at.isoformat(),
                "token_fingerprint": receipt.token_fingerprint,
            }
        )
    if error_code:
        trace["error_code"] = error_code
    return trace


def _work_task_message(claim: WorkTaskClaim) -> str:
    evidence = "\n".join(
        f"- [{item['severity']}] {item['label']}: {item['summary']}" for item in claim.evidence
    ) or "- 无关联证据"
    return (
        f"任务：{claim.title}\n"
        f"说明：{claim.description or '无'}\n"
        f"数据范围：{claim.scope or {}}\n"
        f"来源证据：\n{evidence}\n\n"
        "请在当前岗位权限内完成分析，给出结论、依据、风险和下一步建议。"
        "需要外部高风险写操作时只提交审批请求，不得绕过审批直接执行。"
    )


def _add_event(
    db: Session,
    task: WorkTask,
    event_type: str,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    detail: dict[str, Any] | None = None,
    actor_id: str | None = None,
) -> None:
    db.add(
        WorkTaskEvent(
            tenant_id=task.tenant_id,
            task_id=task.id,
            event_type=event_type,
            actor_type="agent" if actor_id else "system",
            actor_id=actor_id,
            actor_business_role=task.owner_business_role if actor_id else None,
            from_status=from_status,
            to_status=to_status,
            detail_json=detail or {},
        )
    )
