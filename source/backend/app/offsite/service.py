from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import get_settings
from app.db.database import set_tenant_context
from app.db.models import (
    AuthorizationDecision,
    BusinessResource,
    BusinessResourceScope,
    OffsiteChannelAsset,
    OffsiteChannelEvent,
    OffsiteChannelEvidence,
    User,
    utc_now,
)
from app.offsite.schema import (
    EvidenceType,
    OffsiteChannelAssetCreate,
    OffsiteChannelAssetRead,
    OffsiteChannelEventRead,
    OffsiteChannelEvidenceCreate,
    OffsiteChannelEvidenceRead,
    OffsiteChannelReview,
    OffsiteExecutionGuardRead,
)
from app.security.authorization import authorize_business_resource
from app.security.permissions import is_admin_user

_OFFSITE_ROLES = {"operations_supervisor", "tiktok_bd_specialist", "tiktok_tap_manager"}
_MANAGER_ROLES = {"operations_supervisor"}
_EXECUTION_ELIGIBLE_STATUSES = {"verified", "piloting", "active"}
_ASSET_TYPES = {
    "facebook_group",
    "deal_site",
    "creator",
    "media_outlet",
    "author",
    "affiliate",
    "community",
}
_LIFECYCLE_STATUSES = {
    "discovered",
    "candidate",
    "verifying",
    "verified",
    "piloting",
    "active",
    "needs_review",
    "paused",
    "rejected",
    "archived",
}
_TRANSITIONS = {
    "discovered": {"candidate", "needs_review", "rejected", "archived"},
    "candidate": {"verifying", "needs_review", "rejected", "archived"},
    "verifying": {"verified", "needs_review", "rejected", "archived"},
    "verified": {"piloting", "needs_review", "paused", "rejected", "archived"},
    "piloting": {"active", "needs_review", "paused", "rejected", "archived"},
    "active": {"needs_review", "paused", "archived"},
    "needs_review": {"candidate", "verifying", "rejected", "archived"},
    "paused": {"candidate", "verifying", "needs_review", "rejected", "archived"},
    "rejected": {"candidate", "archived"},
    "archived": {"candidate"},
}
_REQUIRED_EVIDENCE: dict[str, tuple[EvidenceType, ...]] = {
    "facebook_group": ("identity", "audience_fit", "activity", "administrator", "terms"),
    "deal_site": ("identity", "audience_fit", "terms", "fees", "contact_basis"),
    "creator": ("identity", "audience_fit", "authenticity", "contact_basis", "compliance"),
    "media_outlet": ("identity", "audience_fit", "terms", "contact_basis"),
    "author": ("identity", "current_role", "contact_basis"),
    "affiliate": ("identity", "audience_fit", "terms", "contact_basis", "compliance"),
    "community": ("identity", "audience_fit", "activity", "terms", "contact_basis"),
}
_SENSITIVE_QUERY_PARTS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "cookie",
    "credential",
    "key",
    "password",
    "secret",
    "session",
    "signature",
    "sig",
    "token",
}
_SENSITIVE_VALUE_KEY_PARTS = _SENSITIVE_QUERY_PARTS | {
    "address",
    "contact_value",
    "email",
    "phone",
    "wechat",
    "whatsapp",
}
_EMAIL_PATTERN = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?\d[\s().-]*){10,}(?!\d)")


def create_channel_asset(
    db: Session,
    *,
    request: OffsiteChannelAssetCreate,
    idempotency_key: str,
    user: User,
) -> OffsiteChannelAssetRead:
    """Create or replay one store-scoped channel asset without external side effects."""

    _require_tenant(request.tenant_id, user)
    _require_role(user, _OFFSITE_ROLES)
    set_tenant_context(db, request.tenant_id)
    store = _authorized_store(
        db,
        tenant_id=request.tenant_id,
        store_resource_id=request.store_resource_id,
        user=user,
        action="REQUEST",
    )
    normalized_ref = _normalize_reference(request.stable_external_ref)
    categories = _normalize_categories(request.categories)
    normalized = {
        "tenant_id": request.tenant_id,
        "brand_key": request.brand_key.strip(),
        "store_resource_id": store.id,
        "asset_type": request.asset_type,
        "canonical_name": request.canonical_name.strip(),
        "stable_external_ref": normalized_ref,
        "region": request.region.strip().upper(),
        "language": request.language.strip(),
        "categories": categories,
    }
    creation_digest = _json_digest(normalized)
    key = _normalize_idempotency_key(idempotency_key)
    existing_by_key = db.exec(
        select(OffsiteChannelAsset).where(
            OffsiteChannelAsset.tenant_id == request.tenant_id,
            OffsiteChannelAsset.idempotency_key == key,
        )
    ).first()
    if existing_by_key:
        if existing_by_key.creation_digest != creation_digest:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key was already used with different channel data",
            )
        return _asset_read(db, existing_by_key)

    external_digest = _plain_digest(normalized_ref)
    existing_identity = db.exec(
        select(OffsiteChannelAsset).where(
            OffsiteChannelAsset.tenant_id == request.tenant_id,
            OffsiteChannelAsset.brand_key == normalized["brand_key"],
            OffsiteChannelAsset.asset_type == request.asset_type,
            OffsiteChannelAsset.stable_external_digest == external_digest,
        )
    ).first()
    if existing_identity:
        if existing_identity.creation_digest != creation_digest:
            raise HTTPException(
                status_code=409,
                detail="Channel identity already exists with different scoped data",
            )
        return _asset_read(db, existing_identity)

    row = OffsiteChannelAsset(
        tenant_id=request.tenant_id,
        brand_key=normalized["brand_key"],
        store_resource_id=store.id,
        store_code=store.code,
        asset_type=request.asset_type,
        canonical_name=normalized["canonical_name"],
        stable_external_ref=normalized_ref,
        stable_external_digest=external_digest,
        region=normalized["region"],
        language=normalized["language"],
        categories_json=categories,
        owner_user_id=user.id,
        idempotency_key=key,
        creation_digest=creation_digest,
        created_by_user_id=user.id,
    )
    db.add(row)
    db.flush()
    _add_event(
        db,
        row,
        event_type="asset_created",
        user=user,
        to_status="discovered",
        detail={
            "asset_type": row.asset_type,
            "brand_key": row.brand_key,
            "store_code": row.store_code,
            "stable_external_digest": row.stable_external_digest,
        },
    )
    db.commit()
    db.refresh(row)
    return _asset_read(db, row)


def list_channel_assets(
    db: Session,
    *,
    tenant_id: str,
    user: User,
    brand_key: str | None = None,
    asset_type: str | None = None,
    lifecycle_status: str | None = None,
) -> list[OffsiteChannelAssetRead]:
    """List assets only for stores explicitly visible to the current business role."""

    _require_tenant(tenant_id, user)
    _require_role(user, _OFFSITE_ROLES)
    set_tenant_context(db, tenant_id)
    if asset_type and asset_type not in _ASSET_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported channel asset type")
    if lifecycle_status and lifecycle_status not in _LIFECYCLE_STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported channel lifecycle status")
    visible_store_ids = _visible_store_ids(db, tenant_id=tenant_id, user=user)
    if not visible_store_ids:
        return []
    statement = select(OffsiteChannelAsset).where(
        OffsiteChannelAsset.tenant_id == tenant_id,
        OffsiteChannelAsset.store_resource_id.in_(visible_store_ids),
    )
    if brand_key:
        statement = statement.where(OffsiteChannelAsset.brand_key == brand_key.strip())
    if asset_type:
        statement = statement.where(OffsiteChannelAsset.asset_type == asset_type)
    if lifecycle_status:
        statement = statement.where(OffsiteChannelAsset.lifecycle_status == lifecycle_status)
    rows = db.exec(statement.order_by(OffsiteChannelAsset.updated_at.desc()).limit(300)).all()
    if not rows:
        return []
    ids = [row.id for row in rows]
    evidence_by_asset: dict[str, list[OffsiteChannelEvidence]] = defaultdict(list)
    evidence_rows = db.exec(
        select(OffsiteChannelEvidence).where(
            OffsiteChannelEvidence.tenant_id == tenant_id,
            OffsiteChannelEvidence.asset_id.in_(ids),
        )
    ).all()
    for evidence in evidence_rows:
        evidence_by_asset[evidence.asset_id].append(evidence)
    return [
        _asset_read(
            db,
            row,
            evidence_rows=evidence_by_asset[row.id],
            include_evidence=False,
            include_events=False,
        )
        for row in rows
    ]


def get_channel_asset(
    db: Session,
    *,
    tenant_id: str,
    asset_id: str,
    user: User,
) -> OffsiteChannelAssetRead:
    """Return one authorized channel asset with evidence and audit events."""

    row = _channel_asset(db, tenant_id=tenant_id, asset_id=asset_id, user=user, action="READ")
    return _asset_read(db, row)


def add_channel_evidence(
    db: Session,
    *,
    asset_id: str,
    request: OffsiteChannelEvidenceCreate,
    idempotency_key: str,
    user: User,
) -> OffsiteChannelAssetRead:
    """Append sourced evidence; existing evidence is never overwritten."""

    row = _channel_asset(
        db,
        tenant_id=request.tenant_id,
        asset_id=asset_id,
        user=user,
        action="REQUEST",
    )
    now = utc_now()
    captured_at = _utc_naive(request.captured_at)
    expires_at = _utc_naive(request.expires_at)
    if captured_at > now + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="captured_at cannot be in the future")
    value = _bounded_evidence_json(request.value)
    source_record_id = _normalize_source_record_id(request.source_record_id)
    key = _normalize_idempotency_key(idempotency_key)
    normalized = {
        "tenant_id": request.tenant_id,
        "brand_key": row.brand_key,
        "asset_id": row.id,
        "evidence_type": request.evidence_type,
        "evidence_class": request.evidence_class,
        "value": value,
        "source_type": request.source_type,
        "source_record_id": source_record_id,
        "ingestion_batch_id": request.ingestion_batch_id,
        "captured_at": captured_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "confidence": request.confidence,
        "rule_version": request.rule_version.strip(),
    }
    payload_digest = _json_digest(normalized)
    existing = db.exec(
        select(OffsiteChannelEvidence).where(
            OffsiteChannelEvidence.tenant_id == request.tenant_id,
            OffsiteChannelEvidence.brand_key == row.brand_key,
            OffsiteChannelEvidence.asset_id == row.id,
            OffsiteChannelEvidence.idempotency_key == key,
        )
    ).first()
    if existing:
        if existing.payload_digest != payload_digest:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key was already used with different evidence",
            )
        return _asset_read(db, row)

    evidence = OffsiteChannelEvidence(
        tenant_id=request.tenant_id,
        brand_key=row.brand_key,
        asset_id=row.id,
        evidence_type=request.evidence_type,
        evidence_class=request.evidence_class,
        value_json=value,
        source_type=request.source_type,
        source_record_id=source_record_id,
        ingestion_batch_id=request.ingestion_batch_id,
        captured_at=captured_at,
        expires_at=expires_at,
        confidence=request.confidence,
        collector_id=user.id,
        rule_version=request.rule_version.strip(),
        raw_hash=_json_digest(value),
        idempotency_key=key,
        payload_digest=payload_digest,
    )
    db.add(evidence)
    db.flush()
    previous_status = row.lifecycle_status
    row.version += 1
    row.updated_at = now
    db.add(row)
    _add_event(
        db,
        row,
        event_type="evidence_added",
        user=user,
        from_status=previous_status,
        to_status=previous_status,
        detail={
            "evidence_id": evidence.id,
            "evidence_type": evidence.evidence_type,
            "evidence_class": evidence.evidence_class,
            "source_type": evidence.source_type,
            "source_record_digest": _plain_digest(evidence.source_record_id),
            "captured_at": evidence.captured_at.isoformat(),
            "expires_at": evidence.expires_at.isoformat(),
            "rule_version": evidence.rule_version,
        },
    )
    db.commit()
    db.refresh(row)
    return _asset_read(db, row)


def review_channel_asset(
    db: Session,
    *,
    asset_id: str,
    request: OffsiteChannelReview,
    user: User,
) -> OffsiteChannelAssetRead:
    """Apply a human lifecycle decision after checking cited, current evidence."""

    _require_manager(user)
    row = _mutable_channel_asset(
        db,
        tenant_id=request.tenant_id,
        asset_id=asset_id,
        expected_version=request.expected_version,
        user=user,
    )
    previous = row.lifecycle_status
    previous_tier = row.tier
    if request.lifecycle_status != previous and request.lifecycle_status not in _TRANSITIONS[previous]:
        raise HTTPException(
            status_code=409,
            detail=f"Invalid channel lifecycle transition: {previous} -> {request.lifecycle_status}",
        )
    evidence_rows = _selected_evidence(
        db,
        tenant_id=row.tenant_id,
        brand_key=row.brand_key,
        asset_id=row.id,
        evidence_ids=request.evidence_ids,
    )
    if request.lifecycle_status in _EXECUTION_ELIGIBLE_STATUSES:
        if not evidence_rows:
            raise HTTPException(
                status_code=409,
                detail="Explicit evidence citations are required for a verified lifecycle state",
            )
        state = _evidence_state(row.asset_type, evidence_rows, utc_now())
        if state["missing"] or state["expired"]:
            missing = ", ".join(state["missing"])
            expired = ", ".join(state["expired"])
            raise HTTPException(
                status_code=409,
                detail=(
                    "Current required evidence is incomplete"
                    f"; missing=[{missing}]; expired=[{expired}]"
                ),
            )
    if previous in {"rejected", "archived"} and request.lifecycle_status == "candidate":
        if not evidence_rows:
            raise HTTPException(
                status_code=409,
                detail="New evidence is required to restore a rejected or archived channel",
            )
        if row.reviewed_at and not any(item.captured_at > row.reviewed_at for item in evidence_rows):
            raise HTTPException(
                status_code=409,
                detail="Restoration evidence must be newer than the previous review",
            )

    now = utc_now()
    row.lifecycle_status = request.lifecycle_status
    row.tier = request.tier
    row.reviewed_by_user_id = user.id
    row.review_reason = request.reason.strip()
    row.reviewed_at = now
    if request.lifecycle_status in _EXECUTION_ELIGIBLE_STATUSES:
        required_types = set(_REQUIRED_EVIDENCE[row.asset_type])
        row.last_verified_at = max(
            item.captured_at
            for item in evidence_rows
            if item.evidence_class != "human_judgment"
            and item.evidence_type in required_types
        )
    row.version += 1
    row.updated_at = now
    db.add(row)
    _add_event(
        db,
        row,
        event_type="asset_reviewed",
        user=user,
        from_status=previous,
        to_status=row.lifecycle_status,
        detail={
            "from_tier": previous_tier,
            "to_tier": row.tier,
            "reason": row.review_reason,
            "evidence_ids": sorted({item.id for item in evidence_rows}),
            "external_action": "none",
        },
    )
    db.commit()
    db.refresh(row)
    return _asset_read(db, row)


def _channel_asset(
    db: Session,
    *,
    tenant_id: str,
    asset_id: str,
    user: User,
    action: str,
) -> OffsiteChannelAsset:
    _require_tenant(tenant_id, user)
    _require_role(user, _OFFSITE_ROLES)
    set_tenant_context(db, tenant_id)
    row = db.exec(
        select(OffsiteChannelAsset).where(
            OffsiteChannelAsset.tenant_id == tenant_id,
            OffsiteChannelAsset.id == asset_id,
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Offsite channel asset not found")
    _authorized_store(
        db,
        tenant_id=tenant_id,
        store_resource_id=row.store_resource_id,
        user=user,
        action=action,
    )
    return row


def _mutable_channel_asset(
    db: Session,
    *,
    tenant_id: str,
    asset_id: str,
    expected_version: int,
    user: User,
) -> OffsiteChannelAsset:
    _require_tenant(tenant_id, user)
    _require_role(user, _OFFSITE_ROLES)
    set_tenant_context(db, tenant_id)
    statement = select(OffsiteChannelAsset).where(
        OffsiteChannelAsset.tenant_id == tenant_id,
        OffsiteChannelAsset.id == asset_id,
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    row = db.exec(statement).first()
    if not row:
        raise HTTPException(status_code=404, detail="Offsite channel asset not found")
    _authorized_store(
        db,
        tenant_id=tenant_id,
        store_resource_id=row.store_resource_id,
        user=user,
        action="REQUEST",
    )
    if row.version != expected_version:
        raise HTTPException(status_code=409, detail="Channel asset changed; reload before retrying")
    return row


def _authorized_store(
    db: Session,
    *,
    tenant_id: str,
    store_resource_id: str,
    user: User,
    action: str,
) -> BusinessResource:
    store = db.exec(
        select(BusinessResource).where(
            BusinessResource.tenant_id == tenant_id,
            BusinessResource.id == store_resource_id,
            BusinessResource.resource_type == "store",
            BusinessResource.status == "active",
        )
    ).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store scope not found")
    access_level = _store_access_level(db, store=store, user=user)
    scope_allowed = access_level == "operator" if action == "REQUEST" else access_level is not None
    policy = authorize_business_resource(
        get_settings(), db=db, user=user, resource=store, action=action
    )
    allowed = scope_allowed and policy.allowed
    reason = policy.reason if scope_allowed else "store_scope_missing_or_read_only"
    db.add(
        AuthorizationDecision(
            tenant_id=tenant_id,
            subject_id=user.id,
            subject_type="human",
            role=policy.role,
            department_id=user.business_role or policy.role,
            store_id=store.code,
            resource_type="store",
            object=f"business_resource:{store.id}",
            action=action,
            effect="allow" if allowed else "deny",
            reason=reason,
            policy_version=policy.policy_version,
            request_id=f"offsite_{uuid4().hex}",
        )
    )
    db.flush()
    if not allowed:
        db.commit()
        raise HTTPException(status_code=404, detail="Store scope not found")
    return store


def _visible_store_ids(db: Session, *, tenant_id: str, user: User) -> list[str]:
    statement = select(BusinessResource.id).where(
        BusinessResource.tenant_id == tenant_id,
        BusinessResource.resource_type == "store",
        BusinessResource.status == "active",
    )
    if not _is_manager(user):
        scoped = select(BusinessResourceScope.resource_id).where(
            BusinessResourceScope.tenant_id == tenant_id,
            BusinessResourceScope.business_role == user.business_role,
        )
        statement = statement.where(BusinessResource.id.in_(scoped))
    return list(db.exec(statement).all())


def _store_access_level(
    db: Session,
    *,
    store: BusinessResource,
    user: User,
) -> str | None:
    if _is_manager(user):
        return "operator"
    scope = db.exec(
        select(BusinessResourceScope).where(
            BusinessResourceScope.tenant_id == store.tenant_id,
            BusinessResourceScope.resource_id == store.id,
            BusinessResourceScope.business_role == user.business_role,
        )
    ).first()
    return scope.access_level if scope else None


def _selected_evidence(
    db: Session,
    *,
    tenant_id: str,
    brand_key: str,
    asset_id: str,
    evidence_ids: Iterable[str],
) -> list[OffsiteChannelEvidence]:
    unique_ids = sorted({item.strip() for item in evidence_ids if item.strip()})
    if not unique_ids:
        return []
    rows = db.exec(
        select(OffsiteChannelEvidence).where(
            OffsiteChannelEvidence.tenant_id == tenant_id,
            OffsiteChannelEvidence.brand_key == brand_key,
            OffsiteChannelEvidence.asset_id == asset_id,
            OffsiteChannelEvidence.id.in_(unique_ids),
        )
    ).all()
    if len(rows) != len(unique_ids):
        raise HTTPException(status_code=422, detail="Evidence citation is outside this channel")
    return list(rows)


def _asset_read(
    db: Session,
    row: OffsiteChannelAsset,
    *,
    evidence_rows: list[OffsiteChannelEvidence] | None = None,
    include_evidence: bool = True,
    include_events: bool = True,
) -> OffsiteChannelAssetRead:
    now = utc_now()
    evidence = evidence_rows
    if evidence is None:
        evidence = list(
            db.exec(
                select(OffsiteChannelEvidence)
                .where(
                    OffsiteChannelEvidence.tenant_id == row.tenant_id,
                    OffsiteChannelEvidence.brand_key == row.brand_key,
                    OffsiteChannelEvidence.asset_id == row.id,
                )
                .order_by(OffsiteChannelEvidence.captured_at.desc())
            ).all()
        )
    state = _evidence_state(row.asset_type, evidence, now)
    effective_status = row.lifecycle_status
    if row.lifecycle_status in _EXECUTION_ELIGIBLE_STATUSES and state["freshness"] != "fresh":
        effective_status = "needs_review"
    reasons: list[str] = []
    if effective_status not in _EXECUTION_ELIGIBLE_STATUSES:
        reasons.append(f"lifecycle_status:{effective_status}")
    reasons.extend(f"missing_evidence:{item}" for item in state["missing"])
    reasons.extend(f"expired_evidence:{item}" for item in state["expired"])
    guard_status = "eligible_for_proposal" if not reasons else "blocked"
    events = (
        db.exec(
            select(OffsiteChannelEvent)
            .where(
                OffsiteChannelEvent.tenant_id == row.tenant_id,
                OffsiteChannelEvent.brand_key == row.brand_key,
                OffsiteChannelEvent.asset_id == row.id,
            )
            .order_by(OffsiteChannelEvent.occurred_at)
        ).all()
        if include_events
        else []
    )
    return OffsiteChannelAssetRead(
        id=row.id,
        tenant_id=row.tenant_id,
        brand_key=row.brand_key,
        store_resource_id=row.store_resource_id,
        store_code=row.store_code,
        asset_type=row.asset_type,
        canonical_name=row.canonical_name,
        stable_external_ref=row.stable_external_ref,
        region=row.region,
        language=row.language,
        categories=list(row.categories_json or []),
        tier=row.tier,
        lifecycle_status=row.lifecycle_status,
        effective_lifecycle_status=effective_status,
        owner_user_id=row.owner_user_id,
        required_evidence_types=list(state["required"]),
        missing_required_evidence=list(state["missing"]),
        expired_required_evidence=list(state["expired"]),
        freshness_status=state["freshness"],
        execution_guard=OffsiteExecutionGuardRead(
            status=guard_status,
            reasons=reasons,
            evaluated_at=now,
        ),
        last_verified_at=row.last_verified_at,
        reviewed_by_user_id=row.reviewed_by_user_id,
        review_reason=row.review_reason,
        reviewed_at=row.reviewed_at,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        evidence=[_evidence_read(item, now) for item in evidence] if include_evidence else [],
        events=[
            OffsiteChannelEventRead(
                id=item.id,
                tenant_id=item.tenant_id,
                brand_key=item.brand_key,
                asset_id=item.asset_id,
                event_type=item.event_type,
                actor_type=item.actor_type,
                actor_id=item.actor_id,
                actor_business_role=item.actor_business_role,
                from_status=item.from_status,
                to_status=item.to_status,
                detail=dict(item.detail_json or {}),
                occurred_at=item.occurred_at,
            )
            for item in events
        ],
    )


def _evidence_read(row: OffsiteChannelEvidence, now: datetime) -> OffsiteChannelEvidenceRead:
    return OffsiteChannelEvidenceRead(
        id=row.id,
        tenant_id=row.tenant_id,
        brand_key=row.brand_key,
        asset_id=row.asset_id,
        evidence_type=row.evidence_type,
        evidence_class=row.evidence_class,
        value=dict(row.value_json or {}),
        source_type=row.source_type,
        source_record_id=row.source_record_id,
        ingestion_batch_id=row.ingestion_batch_id,
        captured_at=row.captured_at,
        expires_at=row.expires_at,
        confidence=row.confidence,
        collector_type=row.collector_type,
        collector_id=row.collector_id,
        rule_version=row.rule_version,
        raw_hash=row.raw_hash,
        freshness_status="fresh" if row.expires_at > now else "expired",
        created_at=row.created_at,
    )


def _evidence_state(
    asset_type: str,
    evidence_rows: Iterable[OffsiteChannelEvidence],
    now: datetime,
) -> dict[str, Any]:
    required = _REQUIRED_EVIDENCE[asset_type]
    by_type: dict[str, list[OffsiteChannelEvidence]] = defaultdict(list)
    for item in evidence_rows:
        # Human judgment is valuable audit context, but it cannot substitute for
        # sourced evidence when a channel is promoted to an execution-adjacent state.
        if item.evidence_class != "human_judgment":
            by_type[item.evidence_type].append(item)
    missing = [item for item in required if not by_type[item]]
    expired = [
        item
        for item in required
        if by_type[item] and not any(evidence.expires_at > now for evidence in by_type[item])
    ]
    freshness = "missing" if missing else "stale" if expired else "fresh"
    return {
        "required": required,
        "missing": tuple(missing),
        "expired": tuple(expired),
        "freshness": freshness,
    }


def _add_event(
    db: Session,
    row: OffsiteChannelAsset,
    *,
    event_type: str,
    user: User,
    to_status: str,
    detail: dict[str, Any],
    from_status: str | None = None,
) -> None:
    db.add(
        OffsiteChannelEvent(
            tenant_id=row.tenant_id,
            brand_key=row.brand_key,
            asset_id=row.id,
            event_type=event_type,
            actor_type="human",
            actor_id=user.id,
            actor_business_role=user.business_role,
            from_status=from_status,
            to_status=to_status,
            detail_json=detail,
        )
    )


def _require_tenant(tenant_id: str, user: User) -> None:
    if tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access is forbidden")


def _require_role(user: User, allowed: set[str]) -> None:
    if not is_admin_user(user) and user.business_role not in allowed:
        raise HTTPException(
            status_code=403,
            detail="Current business role cannot access offsite channel assets",
        )


def _require_manager(user: User) -> None:
    if not _is_manager(user):
        raise HTTPException(
            status_code=403,
            detail="Only an operations supervisor can review channel lifecycle state",
        )


def _is_manager(user: User) -> bool:
    return is_admin_user(user) or user.business_role in _MANAGER_ROLES


def _normalize_idempotency_key(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 8 or len(normalized) > 160:
        raise HTTPException(status_code=422, detail="Idempotency-Key must be 8-160 characters")
    if any(ord(char) < 33 or ord(char) > 126 for char in normalized):
        raise HTTPException(status_code=422, detail="Idempotency-Key must be printable ASCII")
    return normalized


def _normalize_categories(values: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        item = value.strip().lower()
        if not item:
            continue
        if len(item) > 80:
            raise HTTPException(status_code=422, detail="Channel category is too long")
        if item not in normalized:
            normalized.append(item)
    return sorted(normalized)


def _normalize_reference(value: str) -> str:
    normalized = value.strip()
    if any(ord(char) < 32 for char in normalized):
        raise HTTPException(status_code=422, detail="Channel reference contains control characters")
    parsed = urlsplit(normalized)
    if not parsed.scheme:
        return normalized
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=422, detail="Channel URL must use http or https")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="Channel URL must not contain credentials")
    safe_query: list[tuple[str, str]] = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        normalized_key = key.strip().lower()
        if normalized_key in _SENSITIVE_QUERY_PARTS or any(
            part in normalized_key for part in _SENSITIVE_QUERY_PARTS
        ):
            raise HTTPException(status_code=422, detail="Channel URL contains a sensitive query field")
        if normalized_key.startswith("utm_"):
            continue
        safe_query.append((key, item))
    host = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Channel URL contains an invalid port") from exc
    if ":" in host:
        host = f"[{host}]"
    if port:
        host = f"{host}:{port}"
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (parsed.scheme.lower(), host, path, urlencode(sorted(safe_query)), "")
    )


def _normalize_source_record_id(value: str) -> str:
    normalized = value.strip()
    if normalized.startswith(("http://", "https://")):
        return _normalize_reference(normalized)
    if any(ord(char) < 32 for char in normalized):
        raise HTTPException(status_code=422, detail="source_record_id contains control characters")
    lowered = normalized.lower()
    if any(f"{item}=" in lowered for item in _SENSITIVE_QUERY_PARTS):
        raise HTTPException(status_code=422, detail="source_record_id contains sensitive data")
    return normalized


def _bounded_evidence_json(value: dict[str, Any]) -> dict[str, Any]:
    _reject_sensitive_evidence(value)
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Evidence value must be valid JSON") from exc
    if len(encoded) > 16 * 1024:
        raise HTTPException(status_code=413, detail="Evidence value is too large")
    return json.loads(encoded.decode("utf-8"))


def _reject_sensitive_evidence(value: Any, *, path: str = "value") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower().replace("-", "_")
            if any(part in normalized_key for part in _SENSITIVE_VALUE_KEY_PARTS):
                raise HTTPException(
                    status_code=422,
                    detail=f"Evidence must not contain contact data or secrets ({path}.{key})",
                )
            _reject_sensitive_evidence(item, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_sensitive_evidence(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str) and (
        _EMAIL_PATTERN.search(value) or _PHONE_PATTERN.search(value)
    ):
        raise HTTPException(
            status_code=422,
            detail=f"Evidence must not contain direct contact data ({path})",
        )


def _json_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _plain_digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _utc_naive(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)
