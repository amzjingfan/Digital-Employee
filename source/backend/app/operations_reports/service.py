from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import or_
from sqlmodel import Session, select

from app.db import set_tenant_context
from app.db.models import (
    AgentProfile,
    AuthorizationDecision,
    BusinessActionExecution,
    HighRiskActionRequest,
    OperationsReport,
    OperationsReportComment,
    OperationsReportSource,
    ScheduledTaskRun,
    User,
    utc_now,
)
from app.operations_reports.schema import (
    OperationsReportCommentCreate,
    OperationsReportCommentRead,
    OperationsReportFollowUpCreate,
    OperationsReportGenerate,
    OperationsReportRead,
    OperationsReportReview,
    OperationsReportSourceRead,
)
from app.work_tasks.schema import ReportEvidenceReference, ReportFollowUpCommand
from app.work_tasks.service import create_report_follow_up

_MANAGER_ROLES = {"operations_supervisor", "platform_admin"}
_FAILED_EXECUTION_STATUSES = {
    "failed",
    "compensation_failed",
    "manual_resolution_required",
}
_ACTIVE_EXECUTION_STATUSES = {
    "queued",
    "running",
    "retry_wait",
    "compensation_requested",
    "compensating",
}


def list_reports(
    db: Session,
    *,
    tenant_id: str,
    user: User,
    report_type: str | None = None,
) -> list[OperationsReportRead]:
    _require_manager(user, tenant_id)
    set_tenant_context(db, tenant_id)
    statement = select(OperationsReport).where(OperationsReport.tenant_id == tenant_id)
    if report_type:
        statement = statement.where(OperationsReport.report_type == report_type)
    rows = db.exec(statement.order_by(OperationsReport.generated_at.desc()).limit(60)).all()
    return [_read_report(db, row, include_evidence=False) for row in rows]


def get_report(db: Session, *, tenant_id: str, report_id: str, user: User) -> OperationsReportRead:
    _require_manager(user, tenant_id)
    set_tenant_context(db, tenant_id)
    row = db.exec(
        select(OperationsReport).where(
            OperationsReport.tenant_id == tenant_id,
            OperationsReport.id == report_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Operations report not found")
    return _read_report(db, row, include_evidence=True)


def generate_report(
    db: Session,
    *,
    request: OperationsReportGenerate,
    user: User,
) -> OperationsReportRead:
    _require_manager(user, request.tenant_id)
    set_tenant_context(db, request.tenant_id)
    period_start, period_end, label = _period_bounds(
        request.report_type,
        request.report_date,
        request.timezone,
    )
    scope = _normalized_scope(request.scope)
    report_key = _report_key(request.report_type, period_start, period_end, scope)
    existing = db.exec(
        select(OperationsReport).where(
            OperationsReport.tenant_id == request.tenant_id,
            OperationsReport.report_key == report_key,
        )
    ).first()
    if existing is not None and not request.refresh:
        return _read_report(db, existing, include_evidence=True)
    if request.refresh:
        report_key = hashlib.sha256(
            f"{report_key}:{uuid4().hex}".encode()
        ).hexdigest()

    snapshot = _build_snapshot(
        db,
        tenant_id=request.tenant_id,
        period_start=period_start,
        period_end=period_end,
        scope=scope,
        report_type=request.report_type,
    )
    now = utc_now()
    row = OperationsReport(
        tenant_id=request.tenant_id,
        report_key=report_key,
        report_type=request.report_type,
        title=f"{label}{'日报' if request.report_type == 'daily' else '周报'}",
        timezone=request.timezone,
        period_start=period_start,
        period_end=period_end,
        generated_by_user_id=user.id,
    )
    row.scope_json = scope
    row.metrics_json = snapshot["metrics"]
    row.sections_json = snapshot["sections"]
    row.data_status = snapshot["data_status"]
    row.source_count = len(snapshot["sources"])
    row.generated_by_user_id = user.id
    row.generated_at = now
    row.updated_at = now
    db.add(row)
    db.flush()
    for source in snapshot["sources"]:
        db.add(OperationsReportSource(tenant_id=request.tenant_id, report_id=row.id, **source))
    db.commit()
    db.refresh(row)
    return _read_report(db, row, include_evidence=True)


def add_comment(
    db: Session,
    *,
    report_id: str,
    request: OperationsReportCommentCreate,
    user: User,
) -> OperationsReportRead:
    row = _load_mutable_report(db, tenant_id=request.tenant_id, report_id=report_id, user=user)
    _add_comment_row(db, row=row, user=user, action_type="comment", body=request.body, detail={})
    db.commit()
    return _read_report(db, row, include_evidence=True)


def review_report(
    db: Session,
    *,
    report_id: str,
    decision: str,
    request: OperationsReportReview,
    user: User,
) -> OperationsReportRead:
    row = _load_mutable_report(db, tenant_id=request.tenant_id, report_id=report_id, user=user)
    if row.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft reports can be reviewed")
    if decision not in {"confirmed", "rejected"}:
        raise HTTPException(status_code=422, detail="Invalid report decision")
    now = utc_now()
    row.status = decision
    row.reviewed_by_user_id = user.id
    row.review_note = request.note
    row.reviewed_at = now
    row.updated_at = now
    db.add(row)
    _add_comment_row(
        db,
        row=row,
        user=user,
        action_type=decision,
        body=request.note,
        detail={},
    )
    db.commit()
    db.refresh(row)
    return _read_report(db, row, include_evidence=True)


def create_follow_up(
    db: Session,
    *,
    report_id: str,
    request: OperationsReportFollowUpCreate,
    user: User,
) -> OperationsReportRead:
    row = _load_mutable_report(db, tenant_id=request.tenant_id, report_id=report_id, user=user)
    report_sources = db.exec(
        select(OperationsReportSource).where(
            OperationsReportSource.tenant_id == request.tenant_id,
            OperationsReportSource.report_id == report_id,
        )
    ).all()
    sources_by_id = {item.id: item for item in report_sources}
    valid_source_ids = set(sources_by_id)
    if not set(request.source_ids).issubset(valid_source_ids):
        raise HTTPException(status_code=422, detail="Follow-up contains an invalid report source")
    selected_sources = [sources_by_id[source_id] for source_id in request.source_ids]
    task, task_created = create_report_follow_up(
        db,
        command=ReportFollowUpCommand(
            tenant_id=request.tenant_id,
            report_id=row.id,
            title=request.title,
            note=request.note,
            owner_business_role=request.owner_business_role,
            priority=request.priority,
            due_at=request.due_at,
            scope=row.scope_json,
            evidence=[
                ReportEvidenceReference(
                    source_type=item.source_type,
                    source_id=item.source_id,
                    severity=item.severity,
                    label=item.label,
                    summary=item.summary,
                    source_route=item.source_route,
                    occurred_at=item.occurred_at,
                )
                for item in selected_sources
            ],
            created_by_user_id=user.id,
            created_by_business_role=user.business_role or "member",
        ),
    )
    if not task_created:
        return _read_report(db, row, include_evidence=True)
    detail = {
        "task_id": task.id,
        "task_route": f"/enterprise/work-tasks?task_id={task.id}",
        "title": request.title,
        "owner_business_role": request.owner_business_role,
        "priority": request.priority,
        "due_at": request.due_at.isoformat() if request.due_at else None,
        "source_ids": request.source_ids,
        "status": task.status,
        "assignee_agent_id": task.assignee_agent_id,
    }
    body = request.note.strip() or f"创建后续任务：{request.title}"
    _add_comment_row(
        db,
        row=row,
        user=user,
        action_type="follow_up_created",
        body=body,
        detail=detail,
    )
    db.commit()
    return _read_report(db, row, include_evidence=True)


def _build_snapshot(
    db: Session,
    *,
    tenant_id: str,
    period_start: datetime,
    period_end: datetime,
    scope: dict[str, str],
    report_type: str,
) -> dict[str, Any]:
    now = utc_now()
    approvals = db.exec(
        select(HighRiskActionRequest).where(
            HighRiskActionRequest.tenant_id == tenant_id,
            or_(
                HighRiskActionRequest.status == "pending",
                (
                    (HighRiskActionRequest.requested_at >= period_start)
                    & (HighRiskActionRequest.requested_at < period_end)
                ),
                (
                    (HighRiskActionRequest.decided_at >= period_start)
                    & (HighRiskActionRequest.decided_at < period_end)
                ),
            ),
        )
    ).all()
    executions = db.exec(
        select(BusinessActionExecution).where(
            BusinessActionExecution.tenant_id == tenant_id,
            or_(
                BusinessActionExecution.status.in_(_ACTIVE_EXECUTION_STATUSES | _FAILED_EXECUTION_STATUSES),
                (
                    (BusinessActionExecution.created_at >= period_start)
                    & (BusinessActionExecution.created_at < period_end)
                ),
                (
                    (BusinessActionExecution.updated_at >= period_start)
                    & (BusinessActionExecution.updated_at < period_end)
                ),
            ),
        )
    ).all()
    denied = db.exec(
        select(AuthorizationDecision).where(
            AuthorizationDecision.tenant_id == tenant_id,
            AuthorizationDecision.effect == "deny",
            AuthorizationDecision.occurred_at >= period_start,
            AuthorizationDecision.occurred_at < period_end,
        )
    ).all()
    runs = db.exec(
        select(ScheduledTaskRun).where(
            ScheduledTaskRun.tenant_id == tenant_id,
            ScheduledTaskRun.scheduled_for >= period_start,
            ScheduledTaskRun.scheduled_for < period_end,
        )
    ).all()
    agents = {
        item.id: item.name
        for item in db.exec(select(AgentProfile).where(AgentProfile.tenant_id == tenant_id)).all()
    }

    resource_id = scope.get("resource_id")
    role = scope.get("business_role")
    if resource_id:
        approvals = [item for item in approvals if item.resource_id == resource_id]
        executions = [item for item in executions if item.resource_id == resource_id]
    if role:
        approvals = [item for item in approvals if item.requester_business_role == role]

    pending = [item for item in approvals if item.status == "pending"]
    failed_executions = [item for item in executions if item.status in _FAILED_EXECUTION_STATUSES]
    active_executions = [item for item in executions if item.status in _ACTIVE_EXECUTION_STATUSES]
    overdue_runs = [
        item for item in runs if item.status in {"queued", "running"} and item.scheduled_for < now
    ]
    failed_runs = [item for item in runs if item.status == "failed"]

    sources: list[dict[str, Any]] = []
    source_keys: set[tuple[str, str]] = set()

    def add_source(**item: Any) -> None:
        key = (str(item["source_type"]), str(item["source_id"]))
        if key not in source_keys:
            source_keys.add(key)
            sources.append(item)

    for item in pending:
        add_source(
            source_type="approval",
            source_id=item.id,
            business_key=f"approval:{item.resource_id}:{item.action_type}",
            severity="high",
            label="待审批",
            summary=f"{item.resource_name} · {item.action_type}",
            source_route=f"/enterprise/business-resources?view=approvals&request_id={item.id}",
            occurred_at=item.requested_at,
        )
    for item in approvals:
        add_source(
            source_type="approval",
            source_id=item.id,
            business_key=f"approval:{item.resource_id}:{item.action_type}",
            severity="info",
            label={
                "approved": "审批通过",
                "rejected": "审批驳回",
                "cancelled": "审批取消",
            }.get(item.status, "审批记录"),
            summary=f"{item.resource_name} · {item.action_type} · {item.status}",
            source_route=f"/enterprise/business-resources?view=approvals&request_id={item.id}",
            occurred_at=item.decided_at or item.requested_at,
        )
    for item in failed_executions:
        add_source(
            source_type="execution",
            source_id=item.id,
            business_key=f"execution:{item.request_id}",
            severity="critical" if item.status == "manual_resolution_required" else "high",
            label="执行异常",
            summary=f"{item.action_type} · {item.last_error_code or item.status}",
            source_route=f"/enterprise/business-resources?view=executions&execution_id={item.id}",
            occurred_at=item.updated_at,
        )
    for item in executions:
        add_source(
            source_type="execution",
            source_id=item.id,
            business_key=f"execution:{item.request_id}",
            severity="info",
            label="外部执行记录",
            summary=f"{item.action_type} · {item.status}",
            source_route=f"/enterprise/business-resources?view=executions&execution_id={item.id}",
            occurred_at=item.completed_at or item.started_at or item.created_at,
        )
    for item in overdue_runs:
        add_source(
            source_type="scheduled_run",
            source_id=item.id,
            business_key=f"scheduled:{item.scheduled_task_id}",
            severity="high",
            label="逾期任务",
            summary=f"{agents.get(item.agent_id, item.agent_id)} · {item.status}",
            source_route="/enterprise/scheduled-tasks",
            occurred_at=item.scheduled_for,
        )
    for item in failed_runs:
        add_source(
            source_type="scheduled_run",
            source_id=item.id,
            business_key=f"scheduled:{item.scheduled_task_id}:{item.id}",
            severity="high",
            label="任务失败",
            summary=f"{agents.get(item.agent_id, item.agent_id)} · 执行失败",
            source_route="/enterprise/scheduled-tasks",
            occurred_at=item.finished_at or item.scheduled_for,
        )
    for item in runs:
        add_source(
            source_type="scheduled_run",
            source_id=item.id,
            business_key=f"scheduled:{item.scheduled_task_id}:{item.id}",
            severity="info",
            label="数字员工任务记录",
            summary=f"{agents.get(item.agent_id, item.agent_id)} · {item.status}",
            source_route="/enterprise/scheduled-tasks",
            occurred_at=item.finished_at or item.started_at or item.scheduled_for,
        )
    for item in denied:
        add_source(
            source_type="authorization_decision",
            source_id=item.id,
            business_key=f"authorization:{item.request_id}",
            severity="medium",
            label="授权拒绝",
            summary=f"{item.role} · {item.action} · {item.object}",
            source_route="/enterprise/operations-reports",
            occurred_at=item.occurred_at,
        )

    run_activity: dict[str, Counter[str]] = defaultdict(Counter)
    for item in runs:
        run_activity[agents.get(item.agent_id, item.agent_id)][item.status] += 1
    role_activity = [
        {"name": name, "total": sum(counts.values()), "statuses": dict(counts)}
        for name, counts in sorted(run_activity.items())
    ]
    error_roots = Counter(item.last_error_code or "unknown" for item in failed_executions)
    data_warnings: list[str] = []
    if not runs:
        data_warnings.append("报告周期内没有数字员工定时任务运行数据")
    if not approvals and not executions:
        data_warnings.append("报告周期内没有审批或外部执行数据")
    if not denied:
        data_warnings.append("报告周期内没有授权拒绝事件；该项表示无记录，不代表未发生风险")

    metrics = {
        "pending_approvals": len(pending),
        "approved": sum(1 for item in approvals if item.status == "approved"),
        "rejected": sum(1 for item in approvals if item.status == "rejected"),
        "active_executions": len(active_executions),
        "failed_executions": len(failed_executions),
        "scheduled_runs": len(runs),
        "failed_runs": len(failed_runs),
        "overdue_runs": len(overdue_runs),
        "authorization_denials": len(denied),
        "data_as_of": now.isoformat(),
    }
    sections: dict[str, Any] = {
        "major_exceptions": [
            {
                "source_id": item["source_id"],
                "severity": item["severity"],
                "summary": item["summary"],
            }
            for item in sources
            if item["severity"] in {"critical", "high"}
        ][:20],
        "must_handle": {
            "pending_approvals": len(pending),
            "manual_resolution": sum(
                1 for item in executions if item.status == "manual_resolution_required"
            ),
            "overdue_tasks": len(overdue_runs),
        },
        "role_activity": role_activity,
        "data_quality": data_warnings,
        "business_impact": {
            "high_risk_actions_waiting": len(pending),
            "external_actions_at_risk": len(failed_executions),
            "security_denials": len(denied),
        },
    }
    if report_type == "weekly":
        sections["recurring_root_causes"] = [
            {"code": code, "count": count} for code, count in error_roots.most_common(10)
        ]
        sections["improvement_candidates"] = [
            "复盘重复失败的外部连接器与幂等对账流程" if failed_executions else "本周无外部执行失败样本",
            "检查失败或逾期定时任务对应的 SOP 步骤" if failed_runs or overdue_runs else "本周无失败或逾期定时任务",
        ]

    populated_categories = sum(bool(items) for items in (approvals, executions, runs, denied))
    data_status = "available" if populated_categories >= 3 else "partial" if populated_categories else "no_data"
    return {"metrics": metrics, "sections": sections, "sources": sources, "data_status": data_status}


def _read_report(db: Session, row: OperationsReport, *, include_evidence: bool) -> OperationsReportRead:
    sources: list[OperationsReportSourceRead] = []
    comments: list[OperationsReportCommentRead] = []
    if include_evidence:
        sources = [
            OperationsReportSourceRead(
                id=item.id,
                source_type=item.source_type,
                source_id=item.source_id,
                business_key=item.business_key,
                severity=item.severity,
                label=item.label,
                summary=item.summary,
                source_route=item.source_route,
                occurred_at=item.occurred_at,
            )
            for item in db.exec(
                select(OperationsReportSource)
                .where(OperationsReportSource.report_id == row.id)
                .order_by(OperationsReportSource.occurred_at.desc())
            ).all()
        ]
        comments = [
            OperationsReportCommentRead(
                id=item.id,
                action_type=item.action_type,
                author_user_id=item.author_user_id,
                author_business_role=item.author_business_role,
                body=item.body,
                detail=dict(item.detail_json or {}),
                created_at=item.created_at,
            )
            for item in db.exec(
                select(OperationsReportComment)
                .where(OperationsReportComment.report_id == row.id)
                .order_by(OperationsReportComment.created_at)
            ).all()
        ]
    return OperationsReportRead(
        id=row.id,
        tenant_id=row.tenant_id,
        report_type=row.report_type,
        title=row.title,
        status=row.status,
        timezone=row.timezone,
        period_start=row.period_start,
        period_end=row.period_end,
        scope=dict(row.scope_json or {}),
        metrics=dict(row.metrics_json or {}),
        sections=dict(row.sections_json or {}),
        data_status=row.data_status,
        source_count=row.source_count,
        generated_by_user_id=row.generated_by_user_id,
        generated_at=row.generated_at,
        reviewed_by_user_id=row.reviewed_by_user_id,
        review_note=row.review_note,
        reviewed_at=row.reviewed_at,
        updated_at=row.updated_at,
        sources=sources,
        comments=comments,
    )


def _load_mutable_report(
    db: Session, *, tenant_id: str, report_id: str, user: User
) -> OperationsReport:
    _require_manager(user, tenant_id)
    set_tenant_context(db, tenant_id)
    row = db.exec(
        select(OperationsReport).where(
            OperationsReport.tenant_id == tenant_id,
            OperationsReport.id == report_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Operations report not found")
    return row


def _add_comment_row(
    db: Session,
    *,
    row: OperationsReport,
    user: User,
    action_type: str,
    body: str,
    detail: dict[str, Any],
) -> None:
    db.add(
        OperationsReportComment(
            tenant_id=row.tenant_id,
            report_id=row.id,
            action_type=action_type,
            author_user_id=user.id,
            author_business_role=user.business_role or "tenant_member",
            body=body.strip(),
            detail_json=detail,
        )
    )
    row.updated_at = utc_now()
    db.add(row)


def _require_manager(user: User, tenant_id: str) -> None:
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access is forbidden")
    role = "platform_admin" if user.role == "admin" else (user.business_role or "")
    if role not in _MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Operations supervisor role is required")


def _normalized_scope(scope: dict[str, str]) -> dict[str, str]:
    allowed = {"resource_id", "business_role", "brand", "platform", "site", "sku"}
    normalized = {
        key: str(value).strip()[:160]
        for key, value in scope.items()
        if key in allowed and str(value).strip()
    }
    return dict(sorted(normalized.items()))


def _period_bounds(
    report_type: str,
    report_date: date | None,
    timezone_name: str,
) -> tuple[datetime, datetime, str]:
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Unknown report timezone") from exc
    local_today = datetime.now(timezone).date()
    selected = report_date or local_today
    if selected > local_today:
        raise HTTPException(status_code=422, detail="Report date cannot be in the future")
    if report_type == "weekly":
        start_date = selected - timedelta(days=selected.weekday())
        end_date = min(start_date + timedelta(days=7), local_today + timedelta(days=1))
        label = f"{start_date.isoformat()} 至 {(end_date - timedelta(days=1)).isoformat()} "
    else:
        start_date = selected
        end_date = selected + timedelta(days=1)
        label = f"{selected.isoformat()} "
    start_local = datetime.combine(start_date, time.min, timezone)
    end_local = datetime.combine(end_date, time.min, timezone)
    start_utc = start_local.astimezone(UTC).replace(tzinfo=None)
    end_utc = end_local.astimezone(UTC).replace(tzinfo=None)
    return start_utc, end_utc, label


def _report_key(
    report_type: str,
    period_start: datetime,
    period_end: datetime,
    scope: dict[str, str],
) -> str:
    payload = json.dumps(
        {
            "type": report_type,
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
            "scope": scope,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
