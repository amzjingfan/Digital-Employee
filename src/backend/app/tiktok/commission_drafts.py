"""Immutable internal proposals, without financial approval or exclusive order reservation."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from re import fullmatch

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db.models import (
    TikTokCommissionDraft,
    TikTokCommissionDraftOrderRef,
    TikTokCreatorPoolEntry,
    User,
)
from app.tiktok.commission_preflight import (
    CommissionPreflightRequest,
    CommissionScopeInput,
    preflight_commission_draft,
)
from app.tiktok.creator_pool import _clock, _entry, _manager


class CommissionDraftConflict(ValueError):
    pass


class CommissionDraftSaveRequest(CommissionPreflightRequest):
    idempotency_key: str
    expected_pool_revision: int = Field(ge=1)
    scopes: list[CommissionScopeInput] = Field(min_length=1, max_length=1)

    @field_validator("idempotency_key")
    @classmethod
    def opaque_key(cls, value: str) -> str:
        if fullmatch(r"[0-9a-f]{32}", value) is None:
            raise ValueError("32 lowercase hex characters required")
        return value


class CommissionDraftRead(BaseModel):
    id: str
    pool_revision: int
    owner_user_id: str
    fulfillment_user_id: str
    maintenance_user_id: str
    rule_version: str
    rule_expires_at: datetime
    order_refs: list[str]
    development_bps: int
    fulfillment_bps: int
    maintenance_bps: int
    calculation_evidence_ref: str
    created_by_user_id: str
    created_at: datetime
    check_codes: list[str]
    overlapping_order_refs: list[str]
    overlapping_draft_ids: list[str]
    can_submit_financial_review: bool = False


def _digest(entry_id: str, request: CommissionDraftSaveRequest) -> str:
    payload = request.model_dump(mode="json", exclude={"idempotency_key"})
    encoded = json.dumps(
        {"entry_id": entry_id, "request": payload}, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _indexed_order_refs_query(tenant_id: str, order_refs: list[str]):
    return select(
        TikTokCommissionDraftOrderRef.order_ref, TikTokCommissionDraftOrderRef.draft_id,
    ).where(
        TikTokCommissionDraftOrderRef.tenant_id == tenant_id,
        TikTokCommissionDraftOrderRef.order_ref.in_(order_refs),
    )


def _overlap_index(
    db: Session, tenant_id: str, drafts: list[TikTokCommissionDraft],
) -> dict[str, set[str]]:
    order_refs = sorted({
        ref for draft in drafts for ref in json.loads(draft.order_refs_json)
    })
    if not order_refs:
        return {}
    index: dict[str, set[str]] = defaultdict(set)
    if db.get_bind().dialect.name == "postgresql":
        for ref, draft_id in db.exec(_indexed_order_refs_query(tenant_id, order_refs)).all():
            index[ref].add(draft_id)
    else:
        statement = select(TikTokCommissionDraft.id, TikTokCommissionDraft.order_refs_json).where(
            TikTokCommissionDraft.tenant_id == tenant_id,
        )
        targets = set(order_refs)
        for draft_id, order_refs_json in db.exec(statement).all():
            for ref in targets.intersection(json.loads(order_refs_json)):
                index[ref].add(draft_id)
    return index


def _read(
    draft: TikTokCommissionDraft, entry: TikTokCreatorPoolEntry,
    overlap_index: dict[str, set[str]], clock: datetime,
) -> CommissionDraftRead:
    order_refs = json.loads(draft.order_refs_json)
    overlapping_refs = sorted(
        ref for ref in order_refs if overlap_index.get(ref, set()) - {draft.id}
    )
    overlapping_ids = sorted({
        other_id for ref in overlapping_refs
        for other_id in overlap_index[ref] if other_id != draft.id
    })
    checks = ["rule_unapproved"]
    if _clock(draft.rule_expires_at) <= clock:
        checks.append("rule_version_expired")
    if draft.pool_revision != entry.revision:
        checks.append("pool_revision_changed")
    if (
        draft.owner_user_id != entry.owner_user_id
        or draft.fulfillment_user_id != entry.fulfillment_user_id
        or draft.maintenance_user_id != entry.maintenance_user_id
    ):
        checks.append("responsibilities_changed")
    if overlapping_refs:
        checks.append("saved_order_overlap")
    return CommissionDraftRead(
        id=draft.id, pool_revision=draft.pool_revision,
        owner_user_id=draft.owner_user_id,
        fulfillment_user_id=draft.fulfillment_user_id,
        maintenance_user_id=draft.maintenance_user_id,
        rule_version=draft.rule_version, rule_expires_at=draft.rule_expires_at,
        order_refs=order_refs, development_bps=draft.development_bps,
        fulfillment_bps=draft.fulfillment_bps, maintenance_bps=draft.maintenance_bps,
        calculation_evidence_ref=draft.calculation_evidence_ref,
        created_by_user_id=draft.created_by_user_id, created_at=draft.created_at,
        check_codes=checks,
        overlapping_order_refs=overlapping_refs,
        overlapping_draft_ids=overlapping_ids,
    )


def list_commission_drafts(
    db: Session, user: User, entry_id: str, *, now: datetime | None = None,
) -> list[CommissionDraftRead]:
    _manager(user)
    entry = _entry(db, user, entry_id)
    drafts = list(db.exec(select(TikTokCommissionDraft).where(
        TikTokCommissionDraft.tenant_id == user.tenant_id,
        TikTokCommissionDraft.pool_id == entry_id,
    )).all())
    overlap_index = _overlap_index(db, user.tenant_id, drafts)
    return [
        _read(draft, entry, overlap_index, _clock(now))
        for draft in sorted(
            drafts,
            key=lambda item: (item.created_at, item.id), reverse=True,
        )
    ]


def save_commission_draft(
    db: Session, user: User, entry_id: str, request: CommissionDraftSaveRequest,
    *, now: datetime | None = None,
) -> CommissionDraftRead:
    _manager(user)
    entry = _entry(db, user, entry_id)
    digest = _digest(entry_id, request)
    existing = db.exec(select(TikTokCommissionDraft).where(
        TikTokCommissionDraft.tenant_id == user.tenant_id,
        TikTokCommissionDraft.idempotency_key == request.idempotency_key,
    )).first()
    if existing is not None:
        if existing.request_digest != digest:
            raise CommissionDraftConflict("idempotency_key_reused")
        return _read(existing, entry, _overlap_index(db, user.tenant_id, [existing]), _clock(now))

    locked = db.exec(select(TikTokCreatorPoolEntry).where(
        TikTokCreatorPoolEntry.tenant_id == user.tenant_id,
        TikTokCreatorPoolEntry.id == entry_id,
    ).with_for_update().execution_options(populate_existing=True)).one()
    if locked.revision != request.expected_pool_revision:
        raise CommissionDraftConflict("creator_pool_stale")
    preflight = preflight_commission_draft(db, user, entry_id, request, now=now)
    blocked = next((code for code in preflight.check_codes if code != "rule_unapproved"), None)
    if blocked is not None:
        raise CommissionDraftConflict(blocked)

    scope = request.scopes[0]
    draft = TikTokCommissionDraft(
        tenant_id=user.tenant_id, pool_id=entry_id, pool_revision=locked.revision,
        owner_user_id=locked.owner_user_id,
        fulfillment_user_id=locked.fulfillment_user_id,
        maintenance_user_id=locked.maintenance_user_id,
        rule_version=request.rule_version, rule_expires_at=request.rule_expires_at,
        order_refs_json=json.dumps(scope.order_refs, separators=(",", ":")),
        development_bps=scope.development_bps, fulfillment_bps=scope.fulfillment_bps,
        maintenance_bps=scope.maintenance_bps,
        calculation_evidence_ref=scope.calculation_evidence_ref,
        idempotency_key=request.idempotency_key, request_digest=digest,
        created_by_user_id=user.id, created_at=_clock(now),
    )
    db.add(draft)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = db.exec(select(TikTokCommissionDraft).where(
            TikTokCommissionDraft.tenant_id == user.tenant_id,
            TikTokCommissionDraft.idempotency_key == request.idempotency_key,
        )).first()
        if replay is None:
            raise
        if replay.request_digest != digest:
            raise CommissionDraftConflict("idempotency_key_reused") from None
        draft = replay
    return _read(draft, entry, _overlap_index(db, user.tenant_id, [draft]), _clock(now))
