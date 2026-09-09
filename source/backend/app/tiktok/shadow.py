"""Two-week TikTok read-only shadow-run gate."""

from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session, select

from app.db.models import TikTokShadowRun, User, utc_now

SHADOW_DURATION = timedelta(days=14)
MINIMUM_OBSERVATION_DAYS = 14


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
        ends_at=now + SHADOW_DURATION,
        last_heartbeat_at=now,
        started_by_user_id=user.id,
        baseline_json={
            "mode": "read_only",
            "writes_enabled": False,
            "roles": "tiktok_production_baseline",
            "minimum_observation_days": MINIMUM_OBSERVATION_DAYS,
            "observation_days_utc": [],
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
        run.status = "completed" if shadow_run_is_release_ready(run) else "expired"
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
    run = db.exec(
        select(TikTokShadowRun)
        .where(
            TikTokShadowRun.tenant_id == tenant_id,
            TikTokShadowRun.status == "running",
        )
        .order_by(TikTokShadowRun.started_at.desc())
    ).first()
    if not run:
        return None
    now = utc_now()
    run.observation_count += 1
    if error:
        run.error_count += 1
    baseline = dict(run.baseline_json or {})
    observation_days = {
        str(value) for value in baseline.get("observation_days_utc", []) if value
    }
    observation_days.add(now.date().isoformat())
    baseline["observation_days_utc"] = sorted(observation_days)
    run.baseline_json = baseline
    run.last_heartbeat_at = now
    run.updated_at = now
    if now >= run.ends_at:
        run.status = "completed" if shadow_run_is_release_ready(run) else "expired"
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def shadow_run_evidence_issues(run: TikTokShadowRun) -> list[str]:
    """Return stable reasons why a shadow run cannot satisfy the release gate."""

    baseline = dict(run.baseline_json or {})
    observation_days = {
        str(value) for value in baseline.get("observation_days_utc", []) if value
    }
    issues: list[str] = []
    if run.ends_at - run.started_at < SHADOW_DURATION:
        issues.append("shadow_duration_shorter_than_14_days")
    if baseline.get("mode") != "read_only" or baseline.get("writes_enabled") is not False:
        issues.append("shadow_baseline_not_read_only")
    if run.observation_count < MINIMUM_OBSERVATION_DAYS:
        issues.append("shadow_observation_count_below_14")
    if len(observation_days) < MINIMUM_OBSERVATION_DAYS:
        issues.append("shadow_observation_days_below_14")
    if run.error_count:
        issues.append("shadow_errors_recorded")
    if run.last_heartbeat_at < run.ends_at:
        issues.append("shadow_final_heartbeat_missing")
    return issues


def shadow_run_is_release_ready(run: TikTokShadowRun) -> bool:
    return not shadow_run_evidence_issues(run)


def get_shadow_run(db: Session, tenant_id: str) -> TikTokShadowRun | None:
    return db.exec(
        select(TikTokShadowRun)
        .where(TikTokShadowRun.tenant_id == tenant_id)
        .order_by(TikTokShadowRun.started_at.desc())
    ).first()
