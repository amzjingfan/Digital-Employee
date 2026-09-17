from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session
from app.db.models import AuthorizationDecision, AuthorizationPolicyEvent, User
from app.security.auth import get_current_user
from app.security.permissions import is_admin_user
from app.security.policy_lifecycle import (
    PolicyLifecycleError,
    create_policy_draft,
    list_policy_releases,
    publish_policy,
    rollback_policy,
    update_policy_draft,
)

router = APIRouter(
    prefix="/api/enterprise/authorization-decisions",
    tags=["enterprise:authorization"],
    dependencies=[Depends(get_current_user)],
)

policy_router = APIRouter(
    prefix="/api/enterprise/authorization-policies",
    tags=["enterprise:authorization-policies"],
    dependencies=[Depends(get_current_user)],
)


class PolicyDraftCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=500)
    policy_text: str | None = Field(default=None, max_length=131072)


class PolicyDraftUpdate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    expected_digest: str = Field(min_length=64, max_length=64)
    policy_text: str = Field(min_length=1, max_length=131072)
    description: str | None = Field(default=None, max_length=500)


class PolicyDecisionRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=3, max_length=1000)


@router.get("")
def list_authorization_decisions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    effect: Annotated[Literal["allow", "deny"] | None, Query()] = None,
    request_id: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict[str, object]]:
    if not is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Only administrators can view authorization decisions")
    statement = select(AuthorizationDecision).where(
        AuthorizationDecision.tenant_id == current_user.tenant_id
    )
    if effect:
        statement = statement.where(AuthorizationDecision.effect == effect)
    if request_id:
        statement = statement.where(AuthorizationDecision.request_id == request_id)
    rows = db.exec(statement.order_by(AuthorizationDecision.occurred_at.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "subject_id": row.subject_id,
            "subject_type": row.subject_type,
            "role": row.role,
            "department_id": row.department_id,
            "store_id": row.store_id,
            "resource_type": row.resource_type,
            "object": row.object,
            "action": row.action,
            "effect": row.effect,
            "reason": row.reason,
            "policy_version": row.policy_version,
            "request_id": row.request_id,
            "occurred_at": row.occurred_at.isoformat(),
        }
        for row in rows
    ]


@policy_router.get("")
def list_authorization_policies(
    tenant_id: Annotated[str, Query(min_length=1, max_length=128)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> list[dict[str, object]]:
    _require_policy_admin(current_user, tenant_id)
    return [_policy_read(row) for row in list_policy_releases(db, tenant_id=tenant_id)]


@policy_router.post("")
def create_authorization_policy_draft(
    request: PolicyDraftCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    _require_policy_admin(current_user, request.tenant_id)
    try:
        row = create_policy_draft(
            db,
            get_settings(),
            tenant_id=request.tenant_id,
            actor=current_user,
            description=request.description,
            policy_text=request.policy_text,
        )
    except PolicyLifecycleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _policy_read(row)


@policy_router.put("/{release_id}")
def update_authorization_policy_draft(
    release_id: str,
    request: PolicyDraftUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    _require_policy_admin(current_user, request.tenant_id)
    try:
        row = update_policy_draft(
            db,
            get_settings(),
            tenant_id=request.tenant_id,
            release_id=release_id,
            actor=current_user,
            policy_text=request.policy_text,
            expected_digest=request.expected_digest,
            description=request.description,
        )
    except PolicyLifecycleError as exc:
        _raise_policy_error(exc)
    return _policy_read(row)


@policy_router.post("/{release_id}/publish")
def publish_authorization_policy(
    release_id: str,
    request: PolicyDecisionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    _require_policy_admin(current_user, request.tenant_id)
    try:
        row = publish_policy(
            db,
            get_settings(),
            tenant_id=request.tenant_id,
            release_id=release_id,
            actor=current_user,
            reason=request.reason,
        )
    except PolicyLifecycleError as exc:
        _raise_policy_error(exc)
    return _policy_read(row)


@policy_router.post("/{release_id}/rollback")
def rollback_authorization_policy(
    release_id: str,
    request: PolicyDecisionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    _require_policy_admin(current_user, request.tenant_id)
    try:
        row = rollback_policy(
            db,
            get_settings(),
            tenant_id=request.tenant_id,
            target_release_id=release_id,
            actor=current_user,
            reason=request.reason,
        )
    except PolicyLifecycleError as exc:
        _raise_policy_error(exc)
    return _policy_read(row)


@policy_router.get("/events")
def list_authorization_policy_events(
    tenant_id: Annotated[str, Query(min_length=1, max_length=128)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict[str, object]]:
    _require_policy_admin(current_user, tenant_id)
    rows = db.exec(
        select(AuthorizationPolicyEvent)
        .where(AuthorizationPolicyEvent.tenant_id == tenant_id)
        .order_by(AuthorizationPolicyEvent.occurred_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "release_id": row.release_id,
            "event_type": row.event_type,
            "actor_user_id": row.actor_user_id,
            "detail": dict(row.detail_json or {}),
            "occurred_at": row.occurred_at.isoformat(),
        }
        for row in rows
    ]


def _require_policy_admin(user: User, tenant_id: str) -> None:
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Only tenant administrators can manage policies")


def _policy_read(row: object) -> dict[str, object]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "version": row.version,
        "status": row.status,
        "policy_text": row.policy_text,
        "policy_digest": row.policy_digest,
        "description": row.description,
        "source_release_id": row.source_release_id,
        "created_by_user_id": row.created_by_user_id,
        "published_by_user_id": row.published_by_user_id,
        "publish_reason": row.publish_reason,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "published_at": row.published_at.isoformat() if row.published_at else None,
    }


def _raise_policy_error(error: PolicyLifecycleError) -> None:
    detail = str(error)
    if "not found" in detail.lower():
        raise HTTPException(status_code=404, detail=detail) from error
    if any(term in detail.lower() for term in ("changed", "immutable", "only a draft", "digest")):
        raise HTTPException(status_code=409, detail=detail) from error
    raise HTTPException(status_code=422, detail=detail) from error
