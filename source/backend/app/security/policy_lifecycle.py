from __future__ import annotations

from sqlalchemy import func
from sqlmodel import Session, select

from app.config import Settings
from app.db.models import (
    AuthorizationPolicyEvent,
    AuthorizationPolicyRelease,
    User,
    utc_now,
)
from app.security.authorization import (
    clear_authorization_cache,
    default_policy_text,
    validate_policy_text,
)


class PolicyLifecycleError(ValueError):
    pass


def list_policy_releases(db: Session, *, tenant_id: str) -> list[AuthorizationPolicyRelease]:
    return list(
        db.exec(
            select(AuthorizationPolicyRelease)
            .where(AuthorizationPolicyRelease.tenant_id == tenant_id)
            .order_by(AuthorizationPolicyRelease.version.desc())
        ).all()
    )


def create_policy_draft(
    db: Session,
    settings: Settings,
    *,
    tenant_id: str,
    actor: User,
    description: str = "",
    policy_text: str | None = None,
) -> AuthorizationPolicyRelease:
    source = db.exec(
        select(AuthorizationPolicyRelease)
        .where(
            AuthorizationPolicyRelease.tenant_id == tenant_id,
            AuthorizationPolicyRelease.status == "published",
        )
        .order_by(AuthorizationPolicyRelease.version.desc())
    ).first()
    content = policy_text if policy_text is not None else (
        source.policy_text if source else default_policy_text(settings)
    )
    validation = _validate(settings, tenant_id=tenant_id, policy_text=content)
    row = AuthorizationPolicyRelease(
        tenant_id=tenant_id,
        version=_next_version(db, tenant_id),
        policy_text=content,
        policy_digest=str(validation["policy_digest"]),
        description=description.strip()[:500],
        source_release_id=source.id if source else None,
        created_by_user_id=actor.id,
    )
    db.add(row)
    db.flush()
    _event(
        db,
        row,
        "draft_created",
        actor,
        {"rule_count": validation["rule_count"], "source_release_id": row.source_release_id},
    )
    db.commit()
    db.refresh(row)
    return row


def update_policy_draft(
    db: Session,
    settings: Settings,
    *,
    tenant_id: str,
    release_id: str,
    actor: User,
    policy_text: str,
    expected_digest: str,
    description: str | None = None,
) -> AuthorizationPolicyRelease:
    row = _release(db, tenant_id, release_id, for_update=True)
    if row.status != "draft":
        raise PolicyLifecycleError("Published policy content is immutable")
    if row.policy_digest != expected_digest:
        raise PolicyLifecycleError("Policy draft changed; reload before saving")
    validation = _validate(settings, tenant_id=tenant_id, policy_text=policy_text)
    row.policy_text = policy_text
    row.policy_digest = str(validation["policy_digest"])
    if description is not None:
        row.description = description.strip()[:500]
    row.updated_at = utc_now()
    db.add(row)
    _event(
        db,
        row,
        "draft_updated",
        actor,
        {"rule_count": validation["rule_count"]},
    )
    db.commit()
    db.refresh(row)
    clear_authorization_cache()
    return row


def publish_policy(
    db: Session,
    settings: Settings,
    *,
    tenant_id: str,
    release_id: str,
    actor: User,
    reason: str,
) -> AuthorizationPolicyRelease:
    reason = reason.strip()
    if len(reason) < 3:
        raise PolicyLifecycleError("Publish reason must contain at least 3 characters")
    row = _release(db, tenant_id, release_id, for_update=True)
    if row.status != "draft":
        raise PolicyLifecycleError("Only a draft can be published")
    validation = _validate(settings, tenant_id=tenant_id, policy_text=row.policy_text)
    if str(validation["policy_digest"]) != row.policy_digest:
        raise PolicyLifecycleError("Policy digest mismatch")
    current = db.exec(
        select(AuthorizationPolicyRelease).where(
            AuthorizationPolicyRelease.tenant_id == tenant_id,
            AuthorizationPolicyRelease.status == "published",
        )
    ).first()
    now = utc_now()
    if current:
        current.status = "superseded"
        current.updated_at = now
        db.add(current)
    row.status = "published"
    row.published_by_user_id = actor.id
    row.publish_reason = reason[:1000]
    row.published_at = now
    row.updated_at = now
    db.add(row)
    _event(db, row, "published", actor, {"reason": row.publish_reason})
    db.commit()
    db.refresh(row)
    clear_authorization_cache()
    return row


def rollback_policy(
    db: Session,
    settings: Settings,
    *,
    tenant_id: str,
    target_release_id: str,
    actor: User,
    reason: str,
) -> AuthorizationPolicyRelease:
    reason = reason.strip()
    if len(reason) < 3:
        raise PolicyLifecycleError("Rollback reason must contain at least 3 characters")
    target = _release(db, tenant_id, target_release_id)
    if target.status == "draft":
        raise PolicyLifecycleError("Cannot roll back to an unpublished draft")
    validation = _validate(settings, tenant_id=tenant_id, policy_text=target.policy_text)
    current = db.exec(
        select(AuthorizationPolicyRelease).where(
            AuthorizationPolicyRelease.tenant_id == tenant_id,
            AuthorizationPolicyRelease.status == "published",
        )
    ).first()
    now = utc_now()
    if current:
        current.status = "superseded"
        current.updated_at = now
        db.add(current)
    restored = AuthorizationPolicyRelease(
        tenant_id=tenant_id,
        version=_next_version(db, tenant_id),
        status="published",
        policy_text=target.policy_text,
        policy_digest=str(validation["policy_digest"]),
        description=f"Rollback of v{target.version}: {target.description}"[:500],
        source_release_id=target.id,
        created_by_user_id=actor.id,
        published_by_user_id=actor.id,
        publish_reason=reason[:1000],
        created_at=now,
        updated_at=now,
        published_at=now,
    )
    db.add(restored)
    db.flush()
    _event(
        db,
        restored,
        "rolled_back",
        actor,
        {"reason": restored.publish_reason, "target_release_id": target.id},
    )
    db.commit()
    db.refresh(restored)
    clear_authorization_cache()
    return restored


def _validate(settings: Settings, *, tenant_id: str, policy_text: str) -> dict[str, object]:
    try:
        return validate_policy_text(settings, tenant_id=tenant_id, policy_text=policy_text)
    except ValueError as exc:
        raise PolicyLifecycleError(str(exc)) from exc


def _next_version(db: Session, tenant_id: str) -> int:
    current = db.exec(
        select(func.max(AuthorizationPolicyRelease.version)).where(
            AuthorizationPolicyRelease.tenant_id == tenant_id
        )
    ).one()
    return int(current or 0) + 1


def _release(
    db: Session,
    tenant_id: str,
    release_id: str,
    *,
    for_update: bool = False,
) -> AuthorizationPolicyRelease:
    statement = select(AuthorizationPolicyRelease).where(
        AuthorizationPolicyRelease.tenant_id == tenant_id,
        AuthorizationPolicyRelease.id == release_id,
    )
    if for_update and db.bind is not None and db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    row = db.exec(statement).first()
    if not row:
        raise PolicyLifecycleError("Authorization policy release not found")
    return row


def _event(
    db: Session,
    row: AuthorizationPolicyRelease,
    event_type: str,
    actor: User,
    detail: dict[str, object],
) -> None:
    db.add(
        AuthorizationPolicyEvent(
            tenant_id=row.tenant_id,
            release_id=row.id,
            event_type=event_type,
            actor_user_id=actor.id,
            detail_json=detail,
        )
    )
