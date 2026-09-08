"""Two-week TikTok read-only shadow-run gate."""

from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session, select

from app.db.models import (
    TikTokShadowRun,
    User,
    WorkTask,
    WorkTaskEvent,
    WorkTaskEvidence,
    utc_now,
)
from app.tiktok.schema import (
    TikTokShadowEvaluationCreate,
    TikTokShadowEvaluationRead,
    TikTokShadowQualityRead,
)

SHADOW_EVIDENCE_SOURCE_TYPE = "tiktok_shadow_evaluation"
MINIMUM_REVIEWED_OBSERVATIONS = 30
MINIMUM_ADOPTION_RATE = 0.70
REQUIRED_SHADOW_SOP_IDS = (
    "TT-SOP-002",
    "TT-SOP-003",
    "TT-SOP-004",
    "TT-SOP-007",
    "TT-SOP-009",
)
GUARDRAIL_ISSUE_CATEGORIES = {
    "severe_miss",
    "unauthorized_access",
    "false_claim",
    "unapproved_external_write",
}


class TikTokShadowError(ValueError):
    pass


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise TikTokShadowError("Only a tenant administrator can manage the shadow run")


def start_shadow_run(db: Session, user: User) -> TikTokShadowRun:
    _require_admin(user)
    now = utc_now()
    active = db.exec(
        select(TikTokShadowRun).where(
            TikTokShadowRun.tenant_id == user.tenant_id,
            TikTokShadowRun.status.in_(["planned", "running"]),
        )
    ).first()
    if active:
        return active
    run = TikTokShadowRun(
        tenant_id=user.tenant_id,
        status="running",
        started_at=now,
        ends_at=now + timedelta(days=14),
        last_heartbeat_at=now,
        started_by_user_id=user.id,
        baseline_json={
            "mode": "read_only",
            "writes_enabled": False,
            "roles": "tiktok_production_baseline",
        },
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def heartbeat_shadow_run(db: Session, tenant_id: str) -> TikTokShadowRun | None:
    run = db.exec(
        select(TikTokShadowRun)
        .where(
            TikTokShadowRun.tenant_id == tenant_id,
            TikTokShadowRun.status.in_(["planned", "running"]),
        )
        .order_by(TikTokShadowRun.started_at.desc())
    ).first()
    if not run:
        return None
    now = utc_now()
    run.last_heartbeat_at = now
    run.updated_at = now
    if now >= run.ends_at:
        run.status = "completed"
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def record_shadow_observation(
    db: Session,
    *,
    tenant_id: str,
    error: bool = False,
) -> TikTokShadowRun | None:
    run = heartbeat_shadow_run(db, tenant_id)
    if not run or run.status != "running":
        return run
    run.observation_count += 1
    if error:
        run.error_count += 1
    run.updated_at = utc_now()
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_shadow_quality(db: Session, run: TikTokShadowRun) -> TikTokShadowQualityRead:
    """Aggregate immutable, task-linked human comparisons for one shadow run."""

    evidence_rows = db.exec(
        select(WorkTaskEvidence).where(
            WorkTaskEvidence.tenant_id == run.tenant_id,
            WorkTaskEvidence.source_type == SHADOW_EVIDENCE_SOURCE_TYPE,
            WorkTaskEvidence.source_id == run.id,
        )
    ).all()
    verdict_counts = {"adopted": 0, "needs_revision": 0, "rejected": 0}
    guardrail_issue_count = 0
    covered_sop_ids: set[str] = set()
    for evidence in evidence_rows:
        verdict = evidence.label
        if verdict in verdict_counts:
            verdict_counts[verdict] += 1
        issue_category = _shadow_issue_category(evidence.source_route, run.id)
        if issue_category in GUARDRAIL_ISSUE_CATEGORIES:
            guardrail_issue_count += 1
        sop_id = _shadow_sop_id(evidence.source_route, run.id)
        if sop_id in REQUIRED_SHADOW_SOP_IDS:
            covered_sop_ids.add(sop_id)

    reviewed_count = len(evidence_rows)
    adopted_or_revised = verdict_counts["adopted"] + verdict_counts["needs_revision"]
    adoption_rate = adopted_or_revised / reviewed_count if reviewed_count else 0.0
    missing_sop_ids = sorted(set(REQUIRED_SHADOW_SOP_IDS) - covered_sop_ids)
    passed = (
        reviewed_count >= MINIMUM_REVIEWED_OBSERVATIONS
        and adoption_rate >= MINIMUM_ADOPTION_RATE
        and guardrail_issue_count == 0
        and not missing_sop_ids
    )
    return TikTokShadowQualityRead(
        reviewed_count=reviewed_count,
        adopted_count=verdict_counts["adopted"],
        needs_revision_count=verdict_counts["needs_revision"],
        rejected_count=verdict_counts["rejected"],
        guardrail_issue_count=guardrail_issue_count,
        adoption_rate=round(adoption_rate, 4),
        covered_sop_ids=sorted(covered_sop_ids),
        missing_sop_ids=missing_sop_ids,
        minimum_reviewed_count=MINIMUM_REVIEWED_OBSERVATIONS,
        passed=passed,
    )


def record_shadow_evaluation(
    db: Session,
    user: User,
    request: TikTokShadowEvaluationCreate,
) -> TikTokShadowEvaluationRead:
    """Append one human comparison without changing the evaluated task result."""

    _require_admin(user)
    run = heartbeat_shadow_run(db, user.tenant_id)
    if run is None or run.status != "running":
        raise TikTokShadowError("A running TikTok shadow window is required")
    task = db.get(WorkTask, request.task_id)
    if (
        task is None
        or task.tenant_id != user.tenant_id
        or not task.source_type.startswith("tiktok_")
    ):
        raise TikTokShadowError("TikTok task was not found in the current tenant")
    if task.status not in {"review", "completed"}:
        raise TikTokShadowError("TikTok task must be in review or completed before comparison")
    if task.input_json.get("external_writes") is not False:
        raise TikTokShadowError("Shadow evaluation requires an explicitly read-only task")
    if request.issue_category in GUARDRAIL_ISSUE_CATEGORIES and request.verdict == "adopted":
        raise TikTokShadowError("A guardrail issue cannot be marked as adopted")

    existing = db.exec(
        select(WorkTaskEvidence).where(
            WorkTaskEvidence.tenant_id == user.tenant_id,
            WorkTaskEvidence.task_id == task.id,
            WorkTaskEvidence.source_type == SHADOW_EVIDENCE_SOURCE_TYPE,
            WorkTaskEvidence.source_id == run.id,
        )
    ).first()
    route = _shadow_source_route(
        run.id,
        request.issue_category,
        str(task.input_json.get("sop_id") or "unknown"),
    )
    summary = request.summary.strip()
    if len(summary) < 3:
        raise TikTokShadowError("Shadow evaluation summary must contain at least 3 characters")
    if existing is not None:
        if (
            existing.label != request.verdict
            or existing.source_route != route
            or existing.summary != summary
        ):
            raise TikTokShadowError("This task already has an immutable shadow evaluation")
        return TikTokShadowEvaluationRead(
            shadow_run_id=run.id,
            task_id=task.id,
            verdict=request.verdict,
            issue_category=request.issue_category,
            recorded_at=existing.occurred_at,
            quality=get_shadow_quality(db, run),
        )

    now = utc_now()
    severity = (
        "critical"
        if request.issue_category in GUARDRAIL_ISSUE_CATEGORIES
        else "warning"
        if request.verdict != "adopted" or request.issue_category == "other"
        else "info"
    )
    evidence = WorkTaskEvidence(
        tenant_id=user.tenant_id,
        task_id=task.id,
        source_type=SHADOW_EVIDENCE_SOURCE_TYPE,
        source_id=run.id,
        severity=severity,
        label=request.verdict,
        summary=summary,
        source_route=route,
        occurred_at=now,
    )
    db.add(evidence)
    db.add(
        WorkTaskEvent(
            tenant_id=user.tenant_id,
            task_id=task.id,
            event_type="tiktok_shadow_evaluated",
            actor_type="human",
            actor_id=user.id,
            actor_business_role=user.business_role,
            from_status=task.status,
            to_status=task.status,
            detail_json={
                "shadow_run_id": run.id,
                "verdict": request.verdict,
                "issue_category": request.issue_category,
                "sop_id": task.input_json.get("sop_id"),
                "external_writes": False,
            },
        )
    )
    run.observation_count += 1
    if request.verdict == "rejected" or request.issue_category != "none":
        run.error_count += 1
    run.updated_at = now
    db.add(run)
    db.commit()
    db.refresh(evidence)
    db.refresh(run)
    return TikTokShadowEvaluationRead(
        shadow_run_id=run.id,
        task_id=task.id,
        verdict=request.verdict,
        issue_category=request.issue_category,
        recorded_at=evidence.occurred_at,
        quality=get_shadow_quality(db, run),
    )


def get_shadow_run(db: Session, tenant_id: str) -> TikTokShadowRun | None:
    return db.exec(
        select(TikTokShadowRun)
        .where(TikTokShadowRun.tenant_id == tenant_id)
        .order_by(TikTokShadowRun.started_at.desc())
    ).first()


def _shadow_source_route(run_id: str, issue_category: str, sop_id: str) -> str:
    return f"shadow://{run_id}/{issue_category}/{sop_id}"


def _shadow_issue_category(source_route: str, run_id: str) -> str:
    prefix = f"shadow://{run_id}/"
    suffix = source_route[len(prefix) :] if source_route.startswith(prefix) else ""
    return suffix.split("/", 1)[0] if suffix else "unknown"


def _shadow_sop_id(source_route: str, run_id: str) -> str:
    prefix = f"shadow://{run_id}/"
    suffix = source_route[len(prefix) :] if source_route.startswith(prefix) else ""
    parts = suffix.split("/", 1)
    return parts[1] if len(parts) == 2 else "unknown"
