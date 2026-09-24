from __future__ import annotations

from datetime import UTC, datetime, timedelta
from re import fullmatch
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db.models import (
    SocialCreator,
    SocialCreatorEvidence,
    SocialPlatformIdentity,
    TikTokCreatorPoolEntry,
    TikTokCreatorPoolEvent,
    User,
    utc_now,
)


class CreatorPoolConflict(ValueError):
    def __init__(
        self, code: str, *, current_owner_user_id: str | None = None,
        revision: int | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.current_owner_user_id = current_owner_user_id
        self.revision = revision


class PoolIntakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    creator_id: str = Field(min_length=1, max_length=160)
    identity_id: str = Field(min_length=1, max_length=160)
    source_ref: str = Field(min_length=3, max_length=160)
    sla_rule_version: str = Field(min_length=1, max_length=80)
    follow_up_window_hours: int = Field(ge=1, le=720)


class PoolRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)


class PoolFollowUpRequest(PoolRevisionRequest):
    evidence_ref: str = Field(min_length=1, max_length=160)


class PoolAssignmentRequest(PoolRevisionRequest):
    target_user_id: str | None = Field(default=None, max_length=160)
    reason: Literal["staff_change", "assignment_correction", "manual_release"]


class PoolResponsibilitiesRequest(PoolRevisionRequest):
    fulfillment_user_id: str | None = Field(default=None, max_length=160)
    maintenance_user_id: str | None = Field(default=None, max_length=160)


class PoolAssignableBD(BaseModel):
    id: str
    username: str


class PoolEntryRead(BaseModel):
    id: str
    creator_id: str
    identity_id: str
    creator_name: str
    public_handle: str
    market: str
    source_ref: str
    sla_rule_version: str
    follow_up_window_hours: int
    state: Literal["public", "claimed", "reflow_candidate"]
    owner_user_id: str | None
    fulfillment_user_id: str | None
    maintenance_user_id: str | None
    follow_up_due_at: datetime | None
    revision: int


class PoolWorkspace(BaseModel):
    entries: list[PoolEntryRead]
    can_manage: bool
    can_claim: bool
    assignable_bds: list[PoolAssignableBD]
    assignable_users: list[PoolAssignableBD]


def _clock(now: datetime | None) -> datetime:
    value = now or utc_now()
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _reference(value: str, code: str) -> str:
    cleaned = value.strip()
    # A fixed opaque token cannot carry a phone number or a message excerpt.
    if fullmatch(r"evidence:[0-9a-f]{32}", cleaned) is None:
        raise CreatorPoolConflict(code)
    return cleaned


def _is_manager(user: User) -> bool:
    return user.status == "active" and (
        user.role == "admin" or user.business_role == "operations_supervisor"
    )


def _is_bd(user: User) -> bool:
    return user.status == "active" and user.business_role == "tiktok_bd_specialist"


def _manager(user: User) -> None:
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="TikTok supervisor required")


def _bd(user: User) -> None:
    if not _is_bd(user):
        raise HTTPException(status_code=403, detail="TikTok BD required")


def _entry(db: Session, user: User, entry_id: str) -> TikTokCreatorPoolEntry:
    entry = db.exec(select(TikTokCreatorPoolEntry).where(
        TikTokCreatorPoolEntry.tenant_id == user.tenant_id,
        TikTokCreatorPoolEntry.id == entry_id,
    )).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Creator pool entry not found")
    return entry


def _read(db: Session, entry: TikTokCreatorPoolEntry) -> PoolEntryRead:
    creator = db.get(SocialCreator, entry.creator_id)
    identity = db.get(SocialPlatformIdentity, entry.identity_id)
    return PoolEntryRead(
        id=entry.id, creator_id=entry.creator_id, identity_id=entry.identity_id,
        creator_name=creator.canonical_name if creator else "Unknown",
        public_handle=identity.public_handle if identity else "Unknown",
        market=entry.market, source_ref=entry.source_ref,
        sla_rule_version=entry.sla_rule_version,
        follow_up_window_hours=entry.follow_up_window_hours,
        state=entry.state, owner_user_id=entry.owner_user_id,
        fulfillment_user_id=entry.fulfillment_user_id,
        maintenance_user_id=entry.maintenance_user_id,
        follow_up_due_at=(
            _clock(entry.follow_up_due_at) if entry.follow_up_due_at is not None else None
        ),
        revision=entry.revision,
    )


def get_creator_pool(db: Session, user: User) -> PoolWorkspace:
    manager, bd = _is_manager(user), _is_bd(user)
    if not manager and not bd:
        raise HTTPException(status_code=403, detail="TikTok creator pool access required")
    entries = list(db.exec(select(TikTokCreatorPoolEntry).where(
        TikTokCreatorPoolEntry.tenant_id == user.tenant_id,
    ).order_by(TikTokCreatorPoolEntry.created_at.desc(), TikTokCreatorPoolEntry.id)).all())
    if not manager:
        entries = [entry for entry in entries if (
            entry.state == "public" or entry.owner_user_id == user.id
        )]
    candidates = db.exec(select(User).where(
        User.tenant_id == user.tenant_id,
        User.status == "active",
        User.business_role == "tiktok_bd_specialist",
    ).order_by(User.username, User.id)).all() if manager else []
    all_candidates = db.exec(select(User).where(
        User.tenant_id == user.tenant_id,
        User.status == "active",
    ).order_by(User.username, User.id)).all() if manager else []
    return PoolWorkspace(
        entries=[_read(db, entry) for entry in entries], can_manage=manager, can_claim=bd,
        assignable_bds=[PoolAssignableBD(id=candidate.id, username=candidate.username)
                        for candidate in candidates],
        assignable_users=[PoolAssignableBD(id=candidate.id, username=candidate.username)
                          for candidate in all_candidates],
    )


def enter_creator_pool(
    db: Session, user: User, request: PoolIntakeRequest, *, now: datetime | None = None,
) -> PoolEntryRead:
    _manager(user)
    creator = db.exec(select(SocialCreator).where(
        SocialCreator.tenant_id == user.tenant_id,
        SocialCreator.id == request.creator_id,
        SocialCreator.status == "active",
    )).first()
    identity = db.exec(select(SocialPlatformIdentity).where(
        SocialPlatformIdentity.tenant_id == user.tenant_id,
        SocialPlatformIdentity.id == request.identity_id,
        SocialPlatformIdentity.creator_id == request.creator_id,
        SocialPlatformIdentity.platform == "tiktok",
        SocialPlatformIdentity.status == "active",
        SocialPlatformIdentity.verified.is_(True),
    )).first()
    if creator is None or identity is None:
        raise CreatorPoolConflict("verified_tiktok_identity_required")
    clock = _clock(now)
    latest_evidence = db.exec(select(SocialCreatorEvidence).where(
        SocialCreatorEvidence.tenant_id == user.tenant_id,
        SocialCreatorEvidence.creator_id == creator.id,
        SocialCreatorEvidence.identity_id == identity.id,
    ).order_by(
        SocialCreatorEvidence.observed_at.desc(),
        SocialCreatorEvidence.created_at.desc(),
        SocialCreatorEvidence.id.desc(),
    )).first()
    if (
        latest_evidence is None
        or _clock(latest_evidence.observed_at) > clock
        or _clock(latest_evidence.expires_at) <= clock
    ):
        raise CreatorPoolConflict("current_identity_evidence_required")
    if request.source_ref != latest_evidence.id:
        raise CreatorPoolConflict("source_evidence_mismatch")
    if db.exec(select(TikTokCreatorPoolEntry.id).where(
        TikTokCreatorPoolEntry.tenant_id == user.tenant_id,
        TikTokCreatorPoolEntry.creator_id == creator.id,
    )).first() is not None:
        raise CreatorPoolConflict("creator_already_in_pool")
    rule_version = request.sla_rule_version.strip()
    if not rule_version:
        raise CreatorPoolConflict("sla_rule_version_required")
    entry = TikTokCreatorPoolEntry(
        tenant_id=user.tenant_id, creator_id=creator.id, identity_id=identity.id,
        market="US", source_ref=latest_evidence.id,
        sla_rule_version=rule_version,
        follow_up_window_hours=request.follow_up_window_hours,
        created_by_user_id=user.id, created_at=clock, updated_at=clock,
    )
    try:
        db.add(entry)
        db.flush()
        db.add(TikTokCreatorPoolEvent(
            tenant_id=user.tenant_id, pool_id=entry.id, event_type="entered",
            actor_user_id=user.id, evidence_ref=entry.source_ref, created_at=clock,
        ))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # The unique tenant/creator constraint decides simultaneous intake requests.
        existing = db.exec(select(TikTokCreatorPoolEntry.id).where(
            TikTokCreatorPoolEntry.tenant_id == user.tenant_id,
            TikTokCreatorPoolEntry.creator_id == creator.id,
        )).first()
        if existing is not None:
            raise CreatorPoolConflict("creator_already_in_pool") from exc
        raise
    db.refresh(entry)
    return _read(db, entry)


def _transition(
    db: Session, user: User, entry: TikTokCreatorPoolEntry, *,
    expected_revision: int, expected_state: str,
    new_state: str, new_owner: str | None, due_at: datetime | None,
    event_type: str, evidence_ref: str | None = None,
    reason: str | None = None, now: datetime | None = None,
) -> PoolEntryRead:
    clock = _clock(now)
    if entry.revision != expected_revision or entry.state != expected_state:
        raise CreatorPoolConflict(
            "creator_pool_stale", current_owner_user_id=entry.owner_user_id,
            revision=entry.revision,
        )
    result = db.execute(update(TikTokCreatorPoolEntry).where(
        TikTokCreatorPoolEntry.tenant_id == user.tenant_id,
        TikTokCreatorPoolEntry.id == entry.id,
        TikTokCreatorPoolEntry.revision == expected_revision,
        TikTokCreatorPoolEntry.state == expected_state,
    ).values(
        state=new_state, owner_user_id=new_owner, follow_up_due_at=due_at,
        fulfillment_user_id=(None if new_state == "public" else entry.fulfillment_user_id),
        maintenance_user_id=(None if new_state == "public" else entry.maintenance_user_id),
        revision=expected_revision + 1, updated_at=clock,
    ).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        current = _entry(db, user, entry.id)
        raise CreatorPoolConflict(
            "creator_pool_stale", current_owner_user_id=current.owner_user_id,
            revision=current.revision,
        )
    db.add(TikTokCreatorPoolEvent(
        tenant_id=user.tenant_id, pool_id=entry.id, event_type=event_type,
        actor_user_id=user.id, previous_owner_user_id=entry.owner_user_id,
        new_owner_user_id=new_owner, evidence_ref=evidence_ref,
        previous_fulfillment_user_id=entry.fulfillment_user_id,
        new_fulfillment_user_id=(None if new_state == "public" else entry.fulfillment_user_id),
        previous_maintenance_user_id=entry.maintenance_user_id,
        new_maintenance_user_id=(None if new_state == "public" else entry.maintenance_user_id),
        reason=reason, created_at=clock,
    ))
    db.commit()
    db.refresh(entry)
    return _read(db, entry)


def claim_creator(
    db: Session, user: User, entry_id: str, *, expected_revision: int,
    now: datetime | None = None,
) -> PoolEntryRead:
    _bd(user)
    entry = _entry(db, user, entry_id)
    clock = _clock(now)
    return _transition(
        db, user, entry, expected_revision=expected_revision, expected_state="public",
        new_state="claimed", new_owner=user.id,
        due_at=clock + timedelta(hours=entry.follow_up_window_hours),
        event_type="claimed", now=clock,
    )


def record_effective_follow_up(
    db: Session, user: User, entry_id: str, *, expected_revision: int,
    evidence_ref: str, now: datetime | None = None,
) -> PoolEntryRead:
    _bd(user)
    entry = _entry(db, user, entry_id)
    if entry.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Assigned TikTok BD required")
    if entry.state not in {"claimed", "reflow_candidate"}:
        raise CreatorPoolConflict("creator_not_claimed")
    clock = _clock(now)
    return _transition(
        db, user, entry, expected_revision=expected_revision, expected_state=entry.state,
        new_state="claimed", new_owner=user.id,
        due_at=clock + timedelta(hours=entry.follow_up_window_hours),
        event_type="follow_up", evidence_ref=_reference(evidence_ref, "evidence_ref_required"),
        now=clock,
    )


def propose_reflow(
    db: Session, user: User, entry_id: str, *, expected_revision: int,
    now: datetime | None = None,
) -> PoolEntryRead:
    _manager(user)
    entry = _entry(db, user, entry_id)
    clock = _clock(now)
    if entry.state != "claimed" or entry.follow_up_due_at is None:
        raise CreatorPoolConflict("creator_not_claimed")
    if _clock(entry.follow_up_due_at) > clock:
        raise CreatorPoolConflict("follow_up_not_due")
    return _transition(
        db, user, entry, expected_revision=expected_revision, expected_state="claimed",
        new_state="reflow_candidate", new_owner=entry.owner_user_id,
        due_at=entry.follow_up_due_at, event_type="reflow_proposed",
        reason="sla_expired", now=clock,
    )


def approve_reflow(
    db: Session, user: User, entry_id: str, *, expected_revision: int,
    now: datetime | None = None,
) -> PoolEntryRead:
    _manager(user)
    entry = _entry(db, user, entry_id)
    if entry.state != "reflow_candidate":
        raise CreatorPoolConflict(
            "reflow_not_pending", current_owner_user_id=entry.owner_user_id,
            revision=entry.revision,
        )
    return _transition(
        db, user, entry, expected_revision=expected_revision,
        expected_state="reflow_candidate", new_state="public", new_owner=None,
        due_at=None, event_type="reflow_approved", reason="supervisor_approved", now=now,
    )


def assign_creator(
    db: Session, user: User, entry_id: str, *, expected_revision: int,
    target_user_id: str | None, reason: str, now: datetime | None = None,
) -> PoolEntryRead:
    _manager(user)
    entry = _entry(db, user, entry_id)
    if entry.revision != expected_revision:
        raise CreatorPoolConflict(
            "creator_pool_stale", current_owner_user_id=entry.owner_user_id,
            revision=entry.revision,
        )
    if entry.state not in {"claimed", "reflow_candidate"}:
        raise CreatorPoolConflict("creator_not_claimed")
    if target_user_id is None:
        if reason != "manual_release":
            raise CreatorPoolConflict("assignment_reason_invalid")
        new_state, event_type, due_at = "public", "released", None
    else:
        if reason not in {"staff_change", "assignment_correction"}:
            raise CreatorPoolConflict("assignment_reason_invalid")
        if target_user_id == entry.owner_user_id:
            raise CreatorPoolConflict("creator_already_assigned")
        target = db.exec(select(User).where(
            User.tenant_id == user.tenant_id,
            User.id == target_user_id,
            User.status == "active",
            User.business_role == "tiktok_bd_specialist",
        )).first()
        if target is None:
            raise CreatorPoolConflict("active_tenant_bd_required")
        new_state, event_type = "claimed", "transferred"
        due_at = _clock(now) + timedelta(hours=entry.follow_up_window_hours)
    return _transition(
        db, user, entry, expected_revision=expected_revision, expected_state=entry.state,
        new_state=new_state, new_owner=target_user_id, due_at=due_at,
        event_type=event_type, reason=reason, now=now,
    )


def set_creator_responsibilities(
    db: Session, user: User, entry_id: str, *, expected_revision: int,
    fulfillment_user_id: str | None, maintenance_user_id: str | None,
    now: datetime | None = None,
) -> PoolEntryRead:
    _manager(user)
    entry = _entry(db, user, entry_id)
    if entry.revision != expected_revision:
        raise CreatorPoolConflict(
            "creator_pool_stale", current_owner_user_id=entry.owner_user_id,
            revision=entry.revision,
        )
    if entry.state == "public":
        raise CreatorPoolConflict("creator_not_claimed")
    for target_id in (fulfillment_user_id, maintenance_user_id):
        if target_id is None:
            continue
        target = db.exec(select(User.id).where(
            User.tenant_id == user.tenant_id, User.id == target_id,
            User.status == "active",
        )).first()
        if target is None:
            raise CreatorPoolConflict("active_tenant_assignee_required")
    if (
        entry.fulfillment_user_id == fulfillment_user_id
        and entry.maintenance_user_id == maintenance_user_id
    ):
        raise CreatorPoolConflict("responsibilities_unchanged")
    clock = _clock(now)
    result = db.execute(update(TikTokCreatorPoolEntry).where(
        TikTokCreatorPoolEntry.tenant_id == user.tenant_id,
        TikTokCreatorPoolEntry.id == entry.id,
        TikTokCreatorPoolEntry.revision == expected_revision,
        TikTokCreatorPoolEntry.state == entry.state,
    ).values(
        fulfillment_user_id=fulfillment_user_id,
        maintenance_user_id=maintenance_user_id,
        revision=expected_revision + 1, updated_at=clock,
    ).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        current = _entry(db, user, entry_id)
        raise CreatorPoolConflict(
            "creator_pool_stale", current_owner_user_id=current.owner_user_id,
            revision=current.revision,
        )
    db.add(TikTokCreatorPoolEvent(
        tenant_id=user.tenant_id, pool_id=entry.id,
        event_type="responsibilities_changed", actor_user_id=user.id,
        previous_owner_user_id=entry.owner_user_id, new_owner_user_id=entry.owner_user_id,
        previous_fulfillment_user_id=entry.fulfillment_user_id,
        new_fulfillment_user_id=fulfillment_user_id,
        previous_maintenance_user_id=entry.maintenance_user_id,
        new_maintenance_user_id=maintenance_user_id,
        created_at=clock,
    ))
    db.commit()
    db.refresh(entry)
    return _read(db, entry)
