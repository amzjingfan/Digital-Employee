from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db.models import (
    BusinessResource,
    BusinessResourceScope,
    SocialAudienceSnapshot,
    SocialCreator,
    SocialCreatorEvidence,
    SocialDomainEvent,
    SocialPlatformIdentity,
    User,
)
from app.security.permissions import is_admin_user
from app.social.schema import (
    SocialAudienceCreate,
    SocialAudienceFilters,
    SocialAudienceRead,
    SocialCreatorCreate,
    SocialCreatorEvidenceInput,
    SocialCreatorEvidenceRead,
    SocialCreatorRead,
    SocialIdentityRead,
)

CREATOR_READ_ROLES = {"operations_supervisor", "tiktok_bd_specialist", "tiktok_tap_manager"}
CREATOR_MANAGE_ROLES = {"operations_supervisor", "tiktok_bd_specialist"}
AUDIENCE_CREATE_ROLES = {
    "operations_supervisor",
    "tiktok_bd_specialist",
    "tiktok_tap_manager",
}
BRAND_RESOURCE_TYPES = {"store", "social_account"}
MAX_FROZEN_AUDIENCE_SIZE = 1_000


@dataclass(frozen=True)
class _CreatorMatch:
    creator: SocialCreator
    identity: SocialPlatformIdentity
    evidence: SocialCreatorEvidence


def create_creator(
    db: Session,
    *,
    user: User,
    request: SocialCreatorCreate,
    idempotency_key: str,
    request_id: str,
) -> SocialCreatorRead:
    _ensure_role(user, CREATOR_MANAGE_ROLES, "Creator management is not permitted")
    key = _idempotency_key(idempotency_key)
    digest = _digest(request.model_dump(mode="json", exclude_none=True))
    replay = db.exec(
        select(SocialCreator).where(
            SocialCreator.tenant_id == user.tenant_id,
            SocialCreator.idempotency_key == key,
        )
    ).first()
    if replay:
        _ensure_same_request(replay.request_digest, digest)
        return _creator_read(db, replay)

    existing_identity = db.exec(
        select(SocialPlatformIdentity).where(
            SocialPlatformIdentity.tenant_id == user.tenant_id,
            SocialPlatformIdentity.platform == request.identity.platform,
            SocialPlatformIdentity.provider_identity_id == request.identity.provider_identity_id,
        )
    ).first()
    if existing_identity:
        raise HTTPException(status_code=409, detail="Platform identity is already registered")

    now = _now()
    evidence_values = _evidence_values(request.evidence)
    creator = SocialCreator(
        tenant_id=user.tenant_id,
        canonical_name=request.canonical_name,
        status="needs_review" if evidence_values["expires_at"] <= now else "active",
        idempotency_key=key,
        request_digest=digest,
        created_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    identity = SocialPlatformIdentity(
        tenant_id=user.tenant_id,
        creator_id=creator.id,
        platform=request.identity.platform,
        provider_identity_id=request.identity.provider_identity_id,
        public_handle=request.identity.public_handle,
        profile_url=request.identity.profile_url,
        verified=request.identity.verified,
        status=creator.status,
        created_at=now,
        updated_at=now,
    )
    evidence = SocialCreatorEvidence(
        tenant_id=user.tenant_id,
        creator_id=creator.id,
        identity_id=identity.id,
        **evidence_values,
        idempotency_key=f"initial:{creator.id}",
        request_digest=digest,
        created_by_user_id=user.id,
        created_at=now,
    )
    db.add_all(
        [
            creator,
            identity,
            evidence,
            _event(
                tenant_id=user.tenant_id,
                aggregate_type="creator",
                aggregate_id=creator.id,
                event_type="creator_registered",
                actor=user,
                request_id=request_id,
                detail={
                    "identity_id": identity.id,
                    "evidence_id": evidence.id,
                    "platform": identity.platform,
                    "rights_basis": evidence.data_rights_basis,
                    "contact_basis": evidence.contact_basis,
                },
            ),
        ]
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = db.exec(
            select(SocialCreator).where(
                SocialCreator.tenant_id == user.tenant_id,
                SocialCreator.idempotency_key == key,
            )
        ).first()
        if replay:
            _ensure_same_request(replay.request_digest, digest)
            return _creator_read(db, replay)
        raise HTTPException(
            status_code=409, detail="Creator identity conflicts with existing data"
        ) from exc
    return _creator_read(db, creator)


def add_creator_evidence(
    db: Session,
    *,
    user: User,
    creator_id: str,
    identity_id: str,
    request: SocialCreatorEvidenceInput,
    idempotency_key: str,
    request_id: str,
) -> SocialCreatorEvidenceRead:
    _ensure_role(user, CREATOR_MANAGE_ROLES, "Creator management is not permitted")
    creator = _creator(db, user.tenant_id, creator_id)
    identity = db.get(SocialPlatformIdentity, identity_id)
    if not identity or identity.tenant_id != user.tenant_id or identity.creator_id != creator.id:
        raise HTTPException(status_code=404, detail="Creator identity not found")
    key = _idempotency_key(idempotency_key)
    digest = _digest(
        {
            "creator_id": creator.id,
            "identity_id": identity.id,
            "evidence": request.model_dump(mode="json", exclude_none=True),
        }
    )
    replay = db.exec(
        select(SocialCreatorEvidence).where(
            SocialCreatorEvidence.tenant_id == user.tenant_id,
            SocialCreatorEvidence.idempotency_key == key,
        )
    ).first()
    if replay:
        _ensure_same_request(replay.request_digest, digest)
        if replay.creator_id != creator.id or replay.identity_id != identity.id:
            raise HTTPException(
                status_code=409, detail="Idempotency-Key was used for another identity"
            )
        return _evidence_read(replay)

    now = _now()
    values = _evidence_values(request)
    evidence = SocialCreatorEvidence(
        tenant_id=user.tenant_id,
        creator_id=creator.id,
        identity_id=identity.id,
        **values,
        idempotency_key=key,
        request_digest=digest,
        created_by_user_id=user.id,
        created_at=now,
    )
    if values["expires_at"] > now:
        creator.status = "active"
        creator.updated_at = now
        identity.status = "active"
        identity.updated_at = now
    db.add_all(
        [
            creator,
            identity,
            evidence,
            _event(
                tenant_id=user.tenant_id,
                aggregate_type="creator_evidence",
                aggregate_id=evidence.id,
                event_type="creator_evidence_added",
                actor=user,
                request_id=request_id,
                detail={
                    "creator_id": creator.id,
                    "identity_id": identity.id,
                    "quality_score": evidence.quality_score,
                    "rights_basis": evidence.data_rights_basis,
                    "contact_basis": evidence.contact_basis,
                    "expires_at": _as_utc(evidence.expires_at).isoformat(),
                },
            ),
        ]
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = db.exec(
            select(SocialCreatorEvidence).where(
                SocialCreatorEvidence.tenant_id == user.tenant_id,
                SocialCreatorEvidence.idempotency_key == key,
            )
        ).first()
        if replay:
            _ensure_same_request(replay.request_digest, digest)
            return _evidence_read(replay)
        raise HTTPException(
            status_code=409, detail="Creator evidence conflicts with existing data"
        ) from exc
    db.refresh(evidence)
    return _evidence_read(evidence)


def list_creators(
    db: Session,
    *,
    user: User,
    filters: SocialAudienceFilters,
    offset: int = 0,
    limit: int = 100,
) -> list[SocialCreatorRead]:
    _ensure_role(user, CREATOR_READ_ROLES, "Creator catalog access is not permitted")
    matches = _creator_matches(db, tenant_id=user.tenant_id, filters=filters)
    creators_by_id = {match.creator.id: match.creator for match in matches}
    ordered = sorted(creators_by_id.values(), key=lambda row: (row.created_at, row.id))
    return [_creator_read(db, creator) for creator in ordered[offset : offset + limit]]


def freeze_audience(
    db: Session,
    *,
    user: User,
    request: SocialAudienceCreate,
    idempotency_key: str,
    request_id: str,
) -> SocialAudienceRead:
    _ensure_role(user, AUDIENCE_CREATE_ROLES, "Audience creation is not permitted")
    brand = _brand_resource(db, user=user, brand_id=request.brand_id, require_operator=True)
    key = _idempotency_key(idempotency_key)
    filters_payload = request.filters.model_dump(mode="json", exclude_none=True)
    digest = _digest({"brand_id": brand.id, "filters": filters_payload})
    replay = db.exec(
        select(SocialAudienceSnapshot).where(
            SocialAudienceSnapshot.tenant_id == user.tenant_id,
            SocialAudienceSnapshot.brand_id == brand.id,
            SocialAudienceSnapshot.idempotency_key == key,
        )
    ).first()
    if replay:
        _ensure_same_request(replay.request_digest, digest)
        return _audience_read(replay)

    matches = _creator_matches(db, tenant_id=user.tenant_id, filters=request.filters)
    selected: dict[str, _CreatorMatch] = {}
    for match in matches:
        current = selected.get(match.creator.id)
        if current is None or _match_rank(match) > _match_rank(current):
            selected[match.creator.id] = match
    ordered = [selected[key] for key in sorted(selected)]
    if not ordered:
        raise HTTPException(
            status_code=422, detail="No eligible creators match the audience filters"
        )
    if len(ordered) > MAX_FROZEN_AUDIENCE_SIZE:
        raise HTTPException(
            status_code=422,
            detail="Audience exceeds the P0 snapshot size limit; narrow the filters",
        )

    members = [
        {
            "creator_id": match.creator.id,
            "identity_id": match.identity.id,
            "evidence_id": match.evidence.id,
            "observed_at": _as_utc(match.evidence.observed_at).isoformat(),
            "expires_at": _as_utc(match.evidence.expires_at).isoformat(),
        }
        for match in ordered
    ]
    audience_hash = _digest(
        {
            "tenant_id": user.tenant_id,
            "brand_id": brand.id,
            "filters": filters_payload,
            "members": members,
        }
    )
    snapshot = SocialAudienceSnapshot(
        tenant_id=user.tenant_id,
        brand_id=brand.id,
        filters_json=filters_payload,
        creator_ids_json=[member["creator_id"] for member in members],
        identity_ids_json=[member["identity_id"] for member in members],
        evidence_ids_json=[member["evidence_id"] for member in members],
        creator_count=len(members),
        audience_hash=audience_hash,
        idempotency_key=key,
        request_digest=digest,
        created_by_user_id=user.id,
    )
    db.add_all(
        [
            snapshot,
            _event(
                tenant_id=user.tenant_id,
                brand_id=brand.id,
                aggregate_type="audience_snapshot",
                aggregate_id=snapshot.id,
                event_type="audience_frozen",
                actor=user,
                request_id=request_id,
                detail={
                    "creator_count": snapshot.creator_count,
                    "audience_hash": snapshot.audience_hash,
                    "filter_fields": sorted(filters_payload),
                    "outreach_authorized": False,
                },
            ),
        ]
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = db.exec(
            select(SocialAudienceSnapshot).where(
                SocialAudienceSnapshot.tenant_id == user.tenant_id,
                SocialAudienceSnapshot.brand_id == brand.id,
                SocialAudienceSnapshot.idempotency_key == key,
            )
        ).first()
        if replay:
            _ensure_same_request(replay.request_digest, digest)
            return _audience_read(replay)
        raise HTTPException(
            status_code=409, detail="Audience snapshot conflicts with existing data"
        ) from exc
    db.refresh(snapshot)
    return _audience_read(snapshot)


def get_audience(
    db: Session,
    *,
    user: User,
    audience_id: str,
) -> SocialAudienceRead:
    _ensure_role(user, CREATOR_READ_ROLES, "Audience access is not permitted")
    snapshot = db.get(SocialAudienceSnapshot, audience_id)
    if not snapshot or snapshot.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Audience snapshot not found")
    _brand_resource(db, user=user, brand_id=snapshot.brand_id, require_operator=False)
    return _audience_read(snapshot)


def _creator_matches(
    db: Session,
    *,
    tenant_id: str,
    filters: SocialAudienceFilters,
) -> list[_CreatorMatch]:
    creators = db.exec(
        select(SocialCreator).where(
            SocialCreator.tenant_id == tenant_id,
            SocialCreator.status != "archived",
        )
    ).all()
    if not creators:
        return []
    creator_ids = [row.id for row in creators]
    identities = db.exec(
        select(SocialPlatformIdentity).where(
            SocialPlatformIdentity.tenant_id == tenant_id,
            SocialPlatformIdentity.creator_id.in_(creator_ids),
            SocialPlatformIdentity.status != "archived",
        )
    ).all()
    if not identities:
        return []
    identity_ids = [row.id for row in identities]
    evidence_rows = db.exec(
        select(SocialCreatorEvidence).where(
            SocialCreatorEvidence.tenant_id == tenant_id,
            SocialCreatorEvidence.identity_id.in_(identity_ids),
        )
    ).all()
    latest = _latest_evidence(evidence_rows)
    creators_by_id = {row.id: row for row in creators}
    matches: list[_CreatorMatch] = []
    for identity in identities:
        evidence = latest.get(identity.id)
        if evidence and _matches_filter(identity, evidence, filters):
            matches.append(
                _CreatorMatch(
                    creator=creators_by_id[identity.creator_id],
                    identity=identity,
                    evidence=evidence,
                )
            )
    return matches


def _creator_read(db: Session, creator: SocialCreator) -> SocialCreatorRead:
    identities = db.exec(
        select(SocialPlatformIdentity)
        .where(
            SocialPlatformIdentity.tenant_id == creator.tenant_id,
            SocialPlatformIdentity.creator_id == creator.id,
        )
        .order_by(SocialPlatformIdentity.platform, SocialPlatformIdentity.id)
    ).all()
    evidence_rows = db.exec(
        select(SocialCreatorEvidence).where(
            SocialCreatorEvidence.tenant_id == creator.tenant_id,
            SocialCreatorEvidence.creator_id == creator.id,
        )
    ).all()
    latest = _latest_evidence(evidence_rows)
    now = _now()
    has_fresh_evidence = any(not _is_stale(row.expires_at, now) for row in latest.values())
    effective_status = creator.status
    if effective_status != "archived" and not has_fresh_evidence:
        effective_status = "needs_review"
    identity_reads = []
    for identity in identities:
        evidence = latest.get(identity.id)
        identity_status = identity.status
        if identity_status != "archived" and (not evidence or _is_stale(evidence.expires_at, now)):
            identity_status = "needs_review"
        identity_reads.append(
            SocialIdentityRead(
                id=identity.id,
                platform=identity.platform,
                provider_identity_id=identity.provider_identity_id,
                public_handle=identity.public_handle,
                profile_url=identity.profile_url,
                verified=identity.verified,
                status=identity_status,
                latest_evidence=_evidence_read(evidence) if evidence else None,
            )
        )
    return SocialCreatorRead(
        id=creator.id,
        canonical_name=creator.canonical_name,
        status=effective_status,
        identities=identity_reads,
        created_at=creator.created_at,
        updated_at=creator.updated_at,
    )


def _latest_evidence(
    rows: Iterable[SocialCreatorEvidence],
) -> dict[str, SocialCreatorEvidence]:
    latest: dict[str, SocialCreatorEvidence] = {}
    for row in rows:
        current = latest.get(row.identity_id)
        if current is None or (row.observed_at, row.created_at, row.id) > (
            current.observed_at,
            current.created_at,
            current.id,
        ):
            latest[row.identity_id] = row
    return latest


def _matches_filter(
    identity: SocialPlatformIdentity,
    evidence: SocialCreatorEvidence,
    filters: SocialAudienceFilters,
) -> bool:
    if not filters.include_stale and _is_stale(evidence.expires_at):
        return False
    if filters.platform and identity.platform != filters.platform:
        return False
    if filters.country_code and evidence.country_code != filters.country_code:
        return False
    if filters.language_code and evidence.language_code != filters.language_code:
        return False
    if filters.category and (evidence.category or "").casefold() != filters.category.casefold():
        return False
    if filters.min_followers is not None and evidence.followers_count < filters.min_followers:
        return False
    if filters.max_followers is not None and evidence.followers_count > filters.max_followers:
        return False
    if (
        filters.min_engagement_rate_bps is not None
        and evidence.engagement_rate_bps < filters.min_engagement_rate_bps
    ):
        return False
    if (
        filters.audience_country_code
        and evidence.audience_country_code != filters.audience_country_code
    ):
        return False
    if filters.max_estimated_cost_minor is not None:
        if evidence.currency != filters.currency or evidence.estimated_cost_minor is None:
            return False
        if evidence.estimated_cost_minor > filters.max_estimated_cost_minor:
            return False
    if filters.min_quality_score is not None and evidence.quality_score < filters.min_quality_score:
        return False
    return not (filters.require_contactable and evidence.contact_basis == "none")


def _brand_resource(
    db: Session,
    *,
    user: User,
    brand_id: str,
    require_operator: bool,
) -> BusinessResource:
    resource = db.get(BusinessResource, brand_id)
    if (
        not resource
        or resource.tenant_id != user.tenant_id
        or resource.status != "active"
        or resource.resource_type not in BRAND_RESOURCE_TYPES
    ):
        raise HTTPException(status_code=404, detail="Brand scope not found")
    if is_admin_user(user) or user.business_role == "operations_supervisor":
        return resource
    scope = db.exec(
        select(BusinessResourceScope).where(
            BusinessResourceScope.tenant_id == user.tenant_id,
            BusinessResourceScope.resource_id == resource.id,
            BusinessResourceScope.business_role == user.business_role,
        )
    ).first()
    if not scope or (require_operator and scope.access_level != "operator"):
        raise HTTPException(status_code=403, detail="Brand scope denied")
    return resource


def _creator(db: Session, tenant_id: str, creator_id: str) -> SocialCreator:
    creator = db.get(SocialCreator, creator_id)
    if not creator or creator.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Creator not found")
    return creator


def _evidence_values(request: SocialCreatorEvidenceInput) -> dict[str, object]:
    return {
        **request.model_dump(exclude={"observed_at", "expires_at"}),
        "observed_at": _utc_instant(request.observed_at),
        "expires_at": _utc_instant(request.expires_at),
    }


def _evidence_read(evidence: SocialCreatorEvidence) -> SocialCreatorEvidenceRead:
    return SocialCreatorEvidenceRead(
        id=evidence.id,
        creator_id=evidence.creator_id,
        identity_id=evidence.identity_id,
        country_code=evidence.country_code,
        language_code=evidence.language_code,
        category=evidence.category,
        followers_count=evidence.followers_count,
        engagement_rate_bps=evidence.engagement_rate_bps,
        audience_country_code=evidence.audience_country_code,
        estimated_cost_minor=evidence.estimated_cost_minor,
        currency=evidence.currency,
        quality_score=evidence.quality_score,
        source_ref=evidence.source_ref,
        data_rights_basis=evidence.data_rights_basis,
        contact_basis=evidence.contact_basis,
        observed_at=evidence.observed_at,
        expires_at=evidence.expires_at,
        stale=_is_stale(evidence.expires_at),
        created_at=evidence.created_at,
    )


def _audience_read(snapshot: SocialAudienceSnapshot) -> SocialAudienceRead:
    return SocialAudienceRead(
        id=snapshot.id,
        brand_id=snapshot.brand_id,
        status="frozen",
        filters=SocialAudienceFilters.model_validate(snapshot.filters_json or {}),
        creator_ids=list(snapshot.creator_ids_json or []),
        identity_ids=list(snapshot.identity_ids_json or []),
        evidence_ids=list(snapshot.evidence_ids_json or []),
        creator_count=snapshot.creator_count,
        audience_hash=snapshot.audience_hash,
        created_by_user_id=snapshot.created_by_user_id,
        created_at=snapshot.created_at,
    )


def _event(
    *,
    tenant_id: str,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    actor: User,
    request_id: str,
    detail: dict[str, object],
    brand_id: str | None = None,
) -> SocialDomainEvent:
    return SocialDomainEvent(
        tenant_id=tenant_id,
        brand_id=brand_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        actor_user_id=actor.id,
        request_id=(request_id.strip() or "request-unavailable")[:200],
        detail_json=detail,
    )


def _ensure_role(user: User, allowed: set[str], message: str) -> None:
    if not is_admin_user(user) and user.business_role not in allowed:
        raise HTTPException(status_code=403, detail=message)


def _idempotency_key(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 8 or len(normalized) > 160:
        raise HTTPException(
            status_code=422, detail="Idempotency-Key must contain 8 to 160 characters"
        )
    return normalized


def _ensure_same_request(stored_digest: str, current_digest: str) -> None:
    if stored_digest != current_digest:
        raise HTTPException(
            status_code=409, detail="Idempotency-Key was reused with different input"
        )


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _utc_instant(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_stale(value: datetime, now: datetime | None = None) -> bool:
    return _as_utc(value) <= (now or _now())


def _match_rank(match: _CreatorMatch) -> tuple[int, datetime, str]:
    return (match.evidence.quality_score, match.evidence.observed_at, match.identity.id)
