"""Two-week TikTok read-only shadow-run gate."""

from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session, select

from app.db.models import TikTokShadowRun, User, utc_now


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


def get_shadow_run(db: Session, tenant_id: str) -> TikTokShadowRun | None:
    return db.exec(
        select(TikTokShadowRun)
        .where(TikTokShadowRun.tenant_id == tenant_id)
        .order_by(TikTokShadowRun.started_at.desc())
    ).first()
