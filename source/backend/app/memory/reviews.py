from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db.models import (
    AgentProfile,
    ChatSession,
    MemoryRecord,
    MemoryReviewEvent,
    MemoryReviewRequest,
    User,
    utc_now,
)
from app.memory.service import memory_agent_id
from app.security.permissions import agent_owned_by_user, is_admin_user


class MemoryReviewSubmit(BaseModel):
    tenant_id: str
    note: str = Field(default="", max_length=500)


class MemoryReviewDecision(BaseModel):
    tenant_id: str
    note: str = Field(min_length=2, max_length=500)


class MemoryReviewEventRead(BaseModel):
    event_type: str
    actor_user_id: str
    actor_business_role: str
    detail: dict[str, Any]
    occurred_at: datetime


class MemoryReviewRead(BaseModel):
    id: str
    tenant_id: str
    memory_id: str
    memory_owner_user_id: str
    agent_id: str | None
    memory_digest: str
    memory_snapshot: dict[str, Any]
    status: Literal["pending", "approved", "rejected", "cancelled", "invalidated"]
    requester_user_id: str
    request_note: str | None
    decided_by_user_id: str | None
    decision_note: str | None
    requested_at: datetime
    decided_at: datetime | None
    updated_at: datetime
    events: list[MemoryReviewEventRead]


def submit_memory_review(
    db: Session,
    *,
    tenant_id: str,
    memory_id: str,
    note: str,
    user: User,
) -> MemoryReviewRead:
    _ensure_tenant(tenant_id, user)
    memory = db.exec(
        select(MemoryRecord).where(
            MemoryRecord.tenant_id == tenant_id,
            MemoryRecord.id == memory_id,
            MemoryRecord.user_id == user.id,
            MemoryRecord.kind != "conversation",
        )
    ).first()
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    snapshot = _memory_snapshot(db, memory)
    digest = _snapshot_digest(snapshot)
    idempotency_key = hashlib.sha256(
        f"{tenant_id}:{memory.id}:{digest}".encode("utf-8")
    ).hexdigest()
    existing = db.exec(
        select(MemoryReviewRequest).where(
            MemoryReviewRequest.tenant_id == tenant_id,
            MemoryReviewRequest.idempotency_key == idempotency_key,
        )
    ).first()
    if existing:
        return memory_review_read(db, existing)

    row = MemoryReviewRequest(
        tenant_id=tenant_id,
        memory_id=memory.id,
        memory_owner_user_id=memory.user_id,
        agent_id=str(snapshot.get("agent_id") or "") or None,
        idempotency_key=idempotency_key,
        memory_digest=digest,
        memory_snapshot_json=snapshot,
        requester_user_id=user.id,
        request_note=note.strip() or None,
    )
    db.add(row)
    db.flush()
    _add_event(db, row, "submitted", user, {"memory_digest": digest})
    db.commit()
    db.refresh(row)
    return memory_review_read(db, row)


def list_memory_reviews(
    db: Session,
    *,
    tenant_id: str,
    user: User,
    agent_id: str | None = None,
    status: str | None = None,
    review_queue: bool = False,
) -> list[MemoryReviewRead]:
    _ensure_tenant(tenant_id, user)
    statement = select(MemoryReviewRequest).where(MemoryReviewRequest.tenant_id == tenant_id)
    if review_queue:
        _require_reviewer(db, tenant_id, agent_id, user)
        if agent_id:
            statement = statement.where(MemoryReviewRequest.agent_id == agent_id)
    else:
        statement = statement.where(MemoryReviewRequest.requester_user_id == user.id)
        if agent_id:
            statement = statement.where(MemoryReviewRequest.agent_id == agent_id)
    if status:
        statement = statement.where(MemoryReviewRequest.status == status)
    rows = db.exec(statement.order_by(MemoryReviewRequest.requested_at.desc()).limit(500)).all()
    return [memory_review_read(db, row) for row in rows]


def decide_memory_review(
    db: Session,
    *,
    tenant_id: str,
    review_id: str,
    decision: Literal["approved", "rejected"],
    note: str,
    user: User,
) -> MemoryReviewRead:
    _ensure_tenant(tenant_id, user)
    statement = select(MemoryReviewRequest).where(
        MemoryReviewRequest.tenant_id == tenant_id,
        MemoryReviewRequest.id == review_id,
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    row = db.exec(statement).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Memory review not found")
    _require_reviewer(db, tenant_id, row.agent_id, user)
    if row.requester_user_id == user.id:
        raise HTTPException(status_code=403, detail="Requester cannot review their own memory")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Memory review has already been decided")
    memory = db.exec(
        select(MemoryRecord).where(
            MemoryRecord.tenant_id == tenant_id,
            MemoryRecord.id == row.memory_id,
            MemoryRecord.user_id == row.memory_owner_user_id,
        )
    ).first()
    if memory is None or _snapshot_digest(_memory_snapshot(db, memory)) != row.memory_digest:
        row.status = "invalidated"
        row.decided_at = utc_now()
        row.updated_at = utc_now()
        db.add(row)
        _add_event(db, row, "invalidated", user, {"reason": "memory_changed_or_deleted"})
        db.commit()
        raise HTTPException(
            status_code=409,
            detail="Memory changed or was deleted after submission; submit a new review",
        )
    row.status = decision
    row.decided_by_user_id = user.id
    row.decision_note = note.strip()
    row.decided_at = utc_now()
    row.updated_at = utc_now()
    db.add(row)
    _add_event(db, row, decision, user, {"note": row.decision_note})
    db.commit()
    db.refresh(row)
    return memory_review_read(db, row)


def cancel_memory_review(
    db: Session,
    *,
    tenant_id: str,
    review_id: str,
    user: User,
) -> MemoryReviewRead:
    _ensure_tenant(tenant_id, user)
    row = db.exec(
        select(MemoryReviewRequest).where(
            MemoryReviewRequest.tenant_id == tenant_id,
            MemoryReviewRequest.id == review_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Memory review not found")
    if row.requester_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the requester can cancel this review")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending memory reviews can be cancelled")
    row.status = "cancelled"
    row.updated_at = utc_now()
    db.add(row)
    _add_event(db, row, "cancelled", user, {})
    db.commit()
    db.refresh(row)
    return memory_review_read(db, row)


def memory_review_read(db: Session, row: MemoryReviewRequest) -> MemoryReviewRead:
    events = db.exec(
        select(MemoryReviewEvent)
        .where(
            MemoryReviewEvent.tenant_id == row.tenant_id,
            MemoryReviewEvent.review_request_id == row.id,
        )
        .order_by(MemoryReviewEvent.occurred_at)
    ).all()
    return MemoryReviewRead(
        id=row.id,
        tenant_id=row.tenant_id,
        memory_id=row.memory_id,
        memory_owner_user_id=row.memory_owner_user_id,
        agent_id=row.agent_id,
        memory_digest=row.memory_digest,
        memory_snapshot=dict(row.memory_snapshot_json or {}),
        status=row.status,
        requester_user_id=row.requester_user_id,
        request_note=row.request_note,
        decided_by_user_id=row.decided_by_user_id,
        decision_note=row.decision_note,
        requested_at=row.requested_at,
        decided_at=row.decided_at,
        updated_at=row.updated_at,
        events=[
            MemoryReviewEventRead(
                event_type=event.event_type,
                actor_user_id=event.actor_user_id,
                actor_business_role=event.actor_business_role,
                detail=dict(event.detail_json or {}),
                occurred_at=event.occurred_at,
            )
            for event in events
        ],
    )


def _memory_snapshot(db: Session, memory: MemoryRecord) -> dict[str, Any]:
    agent_id = memory_agent_id(memory)
    if not agent_id and memory.session_id:
        session = db.get(ChatSession, memory.session_id)
        if session and session.tenant_id == memory.tenant_id:
            agent_id = session.agent_id
    return {
        "memory_id": memory.id,
        "owner_user_id": memory.user_id,
        "agent_id": agent_id,
        "kind": memory.kind,
        "content": memory.content,
        "importance": memory.importance,
        "metadata": dict(memory.metadata_json or {}),
    }


def _snapshot_digest(snapshot: dict[str, Any]) -> str:
    canonical = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_reviewer(
    db: Session,
    tenant_id: str,
    agent_id: str | None,
    user: User,
) -> None:
    if is_admin_user(user):
        return
    if not agent_id:
        raise HTTPException(status_code=403, detail="Only administrators can review unscoped memory")
    agent = db.get(AgentProfile, agent_id)
    if not agent or agent.tenant_id != tenant_id or not agent_owned_by_user(agent, user):
        raise HTTPException(status_code=403, detail="Current user cannot review this agent's memory")


def _add_event(
    db: Session,
    row: MemoryReviewRequest,
    event_type: str,
    user: User,
    detail: dict[str, Any],
) -> None:
    db.add(
        MemoryReviewEvent(
            tenant_id=row.tenant_id,
            review_request_id=row.id,
            event_type=event_type,
            actor_user_id=user.id,
            actor_business_role=user.business_role,
            detail_json=detail,
        )
    )


def _ensure_tenant(tenant_id: str, user: User) -> None:
    if tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Cannot access another tenant")
