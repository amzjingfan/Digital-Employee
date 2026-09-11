from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.db.models import AccountLifecycleEvent, User, UserInvitation, utc_now
from app.security.auth import hash_password
from app.security.business_roles import BUSINESS_ROLE_BY_KEY

INVITATION_STATUSES = {"pending", "accepted", "cancelled", "expired"}
USER_STATUSES = {"active", "suspended"}


def record_account_event(
    db: Session,
    *,
    tenant_id: str,
    event_type: str,
    actor_user_id: str | None,
    subject_user_id: str | None = None,
    subject_ref: str = "",
    outcome: str = "allowed",
    reason: str = "",
    detail: dict[str, Any] | None = None,
) -> AccountLifecycleEvent:
    row = AccountLifecycleEvent(
        tenant_id=tenant_id,
        event_type=event_type[:80],
        actor_user_id=actor_user_id,
        subject_user_id=subject_user_id,
        subject_ref=subject_ref[:200],
        outcome=outcome,
        reason=reason[:500],
        detail_json=detail or {},
    )
    db.add(row)
    return row


def create_invitation(
    db: Session,
    *,
    tenant_id: str,
    username: str,
    display_name: str,
    role: str,
    business_role: str,
    auth_source: str,
    invited_by: User,
    settings: Settings | None = None,
) -> tuple[UserInvitation, str]:
    settings = settings or get_settings()
    normalized_username = username.strip()[:120]
    if not normalized_username:
        raise HTTPException(status_code=400, detail="Username is required")
    if role not in {"admin", "member"}:
        raise HTTPException(status_code=400, detail="Account role is invalid")
    if auth_source not in {"local", "oidc"}:
        raise HTTPException(status_code=400, detail="Invitation auth source is invalid")
    if role == "admin":
        normalized_business_role = "platform_admin"
    else:
        normalized_business_role = business_role.strip() or "member"
        if normalized_business_role != "member" and normalized_business_role not in BUSINESS_ROLE_BY_KEY:
            raise HTTPException(status_code=400, detail="Business role is invalid")
    existing = db.exec(
        select(User).where(User.tenant_id == tenant_id, User.username == normalized_username)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Account already exists")
    pending = db.exec(
        select(UserInvitation).where(
            UserInvitation.tenant_id == tenant_id,
            UserInvitation.username == normalized_username,
            UserInvitation.status == "pending",
        )
    ).first()
    if pending and pending.expires_at > utc_now():
        raise HTTPException(status_code=409, detail="A pending invitation already exists")
    if pending:
        pending.status = "expired"
        pending.updated_at = utc_now()
        db.add(pending)

    raw_token = secrets.token_urlsafe(32)
    row = UserInvitation(
        tenant_id=tenant_id,
        username=normalized_username,
        display_name=(display_name.strip() or normalized_username)[:80],
        role=role,
        business_role=normalized_business_role,
        auth_source=auth_source,
        token_digest=invitation_token_digest(raw_token, settings=settings),
        invited_by_user_id=invited_by.id,
        expires_at=utc_now() + timedelta(seconds=settings.auth_invitation_ttl_seconds),
    )
    db.add(row)
    record_account_event(
        db,
        tenant_id=tenant_id,
        event_type="user_invited",
        actor_user_id=invited_by.id,
        subject_ref=normalized_username,
        detail={
            "invitation_id": row.id,
            "account_role": row.role,
            "business_role": row.business_role,
            "auth_source": row.auth_source,
            "expires_at": row.expires_at.isoformat(),
        },
    )
    db.commit()
    db.refresh(row)
    return row, raw_token


def accept_invitation(
    db: Session,
    *,
    tenant_id: str,
    token: str,
    password: str | None,
    settings: Settings | None = None,
) -> User:
    settings = settings or get_settings()
    digest = invitation_token_digest(token, settings=settings)
    row = db.exec(
        select(UserInvitation).where(
            UserInvitation.tenant_id == tenant_id,
            UserInvitation.token_digest == digest,
        )
    ).first()
    if not row or not hmac.compare_digest(row.token_digest, digest):
        raise HTTPException(status_code=404, detail="Invitation not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Invitation is no longer active")
    if row.expires_at <= utc_now():
        row.status = "expired"
        row.updated_at = utc_now()
        record_account_event(
            db,
            tenant_id=tenant_id,
            event_type="invitation_expired",
            actor_user_id=None,
            subject_ref=row.username,
            outcome="denied",
            reason="invitation_expired",
            detail={"invitation_id": row.id},
        )
        db.add(row)
        db.commit()
        raise HTTPException(status_code=410, detail="Invitation has expired")
    if row.auth_source != "local":
        raise HTTPException(
            status_code=409,
            detail="OIDC invitation must be completed through the identity provider",
        )
    normalized_password = (password or "").strip()
    if len(normalized_password) < 8:
        raise HTTPException(status_code=400, detail="Password must contain at least 8 characters")
    existing = db.exec(
        select(User).where(User.tenant_id == tenant_id, User.username == row.username)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Account already exists")
    user = User(
        tenant_id=tenant_id,
        username=row.username,
        display_name=row.display_name or row.username,
        role=row.role,
        business_role=row.business_role,
        authorization_source="local",
        source="web",
        password_hash=hash_password(normalized_password),
    )
    db.add(user)
    db.flush()
    row.status = "accepted"
    row.accepted_by_user_id = user.id
    row.accepted_at = utc_now()
    row.updated_at = utc_now()
    db.add(row)
    record_account_event(
        db,
        tenant_id=tenant_id,
        event_type="invitation_accepted",
        actor_user_id=user.id,
        subject_user_id=user.id,
        subject_ref=user.username,
        detail={"invitation_id": row.id},
    )
    db.commit()
    db.refresh(user)
    return user


def cancel_invitation(
    db: Session, *, tenant_id: str, invitation_id: str, actor: User
) -> UserInvitation:
    row = db.get(UserInvitation, invitation_id)
    if not row or row.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Invitation is no longer active")
    row.status = "cancelled"
    row.cancelled_at = utc_now()
    row.updated_at = utc_now()
    db.add(row)
    record_account_event(
        db,
        tenant_id=tenant_id,
        event_type="invitation_cancelled",
        actor_user_id=actor.id,
        subject_ref=row.username,
        detail={"invitation_id": row.id},
    )
    db.commit()
    db.refresh(row)
    return row


def invitation_token_digest(token: str, *, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return hmac.new(
        settings.app_secret.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
