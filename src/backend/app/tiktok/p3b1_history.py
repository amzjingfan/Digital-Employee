from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db.models import (
    TikTokDataValidationRun,
    TikTokDataValidationScope,
    TikTokFieldContract,
    TikTokHistoryBatch,
    TikTokHistoryFact,
    TikTokHistoryMetricDefinition,
    TikTokHistoryReconciliation,
    TikTokHistorySignoff,
    User,
    utc_now,
)
from app.security.permissions import ensure_tenant_admin
from app.tiktok.data_validation import (
    DATA_VALIDATION_CATALOG_VERSION,
    FIELD_CODES,
    validate_data_validation_dataset,
)
from app.tiktok.recorded_validation import (
    MAX_RECORDED_REQUEST_BYTES,
    TikTokRecordedValidationInputError,
    compute_contract_digest,
    validate_recorded_dataset_shape,
)
from app.tiktok.schema import TikTokRecordedDataset

COLLECTIONS = {
    "samples": ("sample", "application_id"),
    "orders": ("order", "order_id"),
    "logistics": ("logistics", "tracking_number"),
    "videos": ("video", "video_id"),
    "attribution": ("attribution", "order_id"),
    "gmv": ("gmv", "order_id"),
}
MAX_HISTORY_REQUEST_BYTES = MAX_RECORDED_REQUEST_BYTES

METRICS = (
    ("sample_count", "样品数", "count(sample)", "records", None, None),
    ("delivered_count", "已签收记录数", "count(logistics.status=delivered)", "records", None, None),
    ("video_views", "播放量", "sum(video.view_count)", "views", "view_count", None),
    ("video_likes", "点赞量", "sum(video.like_count)", "likes", "like_count", None),
    ("order_count", "订单数", "count(order)", "orders", None, None),
    ("gmv", "GMV", "sum(gmv.amount) by currency", "currency", "amount", None),
)


class HistoryConflict(ValueError):
    """Stable, secret-free rejection for an invalid historical import or review."""


def _reject_nonstandard_json(_value: str) -> None:
    raise TikTokRecordedValidationInputError("history_json_invalid")


async def read_history_import_request(request: Request) -> HistoryImportRequest:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise TikTokRecordedValidationInputError("history_content_type_required", 415)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_HISTORY_REQUEST_BYTES:
            raise TikTokRecordedValidationInputError("history_payload_too_large", 413)
    try:
        raw = json.loads(body, parse_constant=_reject_nonstandard_json)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TikTokRecordedValidationInputError("history_json_invalid") from None
    finally:
        body.clear()
    if not isinstance(raw, dict):
        raise TikTokRecordedValidationInputError("history_schema_invalid")
    validate_recorded_dataset_shape(raw.get("dataset"))
    try:
        return HistoryImportRequest.model_validate(raw)
    except ValidationError:
        raise TikTokRecordedValidationInputError("history_schema_invalid") from None


class HistoryImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recorded_run_id: str = Field(min_length=1, max_length=160)
    source_kind: Literal["synthetic", "approved_redacted_history"]
    assigned_bd_user_id: str = Field(min_length=1, max_length=160)
    dataset: TikTokRecordedDataset


class HistoryImportResult(BaseModel):
    batch_id: str
    inserted_count: int
    source_kind: str


class ReconciliationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["matched", "difference", "needs_review"]
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def require_meaningful_reason(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("reconciliation_reason_required")
        return value.strip()


class HistoryConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_ref: str = Field(min_length=3, max_length=200)


class HistoryFactRead(BaseModel):
    id: str
    tenant_id: str
    domain: str
    business_key: str
    observed_at: datetime
    source_label: str
    source_kind: str
    assigned_bd_user_id: str
    values: dict[str, object]
    latest_verdict: str | None


class HistoryMetricRead(BaseModel):
    code: str
    version: int
    label: str
    value: str | None
    unit: str
    reason: str | None = None
    formula: str
    timezone: str
    window: str


class HistoryWorkspace(BaseModel):
    tenant_id: str
    total_count: int
    reviewed_count: int
    eligible_reviewed_count: int
    exit_ready: bool
    can_confirm: bool
    facts: list[HistoryFactRead]
    metrics: list[HistoryMetricRead]
    bd_options: list[dict[str, str]]


class ReconciliationRead(BaseModel):
    id: str
    fact_id: str
    verdict: str
    reason: str
    reviewed_by_user_id: str
    created_at: datetime


class HistorySignoffRead(BaseModel):
    id: str
    reviewed_count: int
    approval_ref: str
    confirmed_by_user_id: str
    created_at: datetime


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _digest(value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _metric_definitions(db: Session, tenant_id: str) -> None:
    existing = {
        row.code
        for row in db.exec(
            select(TikTokHistoryMetricDefinition).where(
                TikTokHistoryMetricDefinition.tenant_id == tenant_id,
                TikTokHistoryMetricDefinition.version == 1,
            )
        ).all()
    }
    for code, label, formula, unit, numerator, denominator in METRICS:
        if code not in existing:
            db.add(TikTokHistoryMetricDefinition(
                tenant_id=tenant_id,
                code=code,
                label=label,
                formula=formula,
                unit=unit,
                numerator=numerator,
                denominator=denominator,
            ))


def import_history(
    db: Session,
    user: User,
    request: HistoryImportRequest,
    *,
    now: datetime | None = None,
) -> HistoryImportResult:
    ensure_tenant_admin(user.tenant_id, user)
    clock = _aware(now or utc_now())
    run = db.exec(
        select(TikTokDataValidationRun).where(
            TikTokDataValidationRun.tenant_id == user.tenant_id,
            TikTokDataValidationRun.id == request.recorded_run_id,
        )
    ).first()
    if run is None:
        raise HistoryConflict("recorded_run_not_found")
    if run.mode != "recorded" or run.status != "passed":
        raise HistoryConflict("recorded_run_not_passed")
    if run.approval_valid_until is None or _aware(run.approval_valid_until) <= clock:
        raise HistoryConflict("recorded_approval_expired")
    scope = db.exec(
        select(TikTokDataValidationScope)
        .where(
            TikTokDataValidationScope.tenant_id == user.tenant_id,
            TikTokDataValidationScope.id == run.scope_id,
        )
        .with_for_update(read=True)
    ).first()
    if scope is None or scope.status != "active" or scope.revision != run.scope_revision:
        raise HistoryConflict("recorded_scope_stale")
    contracts = list(db.exec(
        select(TikTokFieldContract)
        .where(TikTokFieldContract.tenant_id == user.tenant_id)
        .order_by(TikTokFieldContract.field_code)
        .with_for_update(read=True)
    ).all())
    if {item.field_code for item in contracts} != set(FIELD_CODES):
        raise HistoryConflict("field_catalog_incomplete")
    if run.catalog_version != DATA_VALIDATION_CATALOG_VERSION or (
        compute_contract_digest(contracts) != run.contract_digest
    ):
        raise HistoryConflict("recorded_contract_stale")
    assignee = db.exec(select(User).where(
        User.tenant_id == user.tenant_id,
        User.id == request.assigned_bd_user_id,
        User.status == "active",
    )).first()
    if assignee is None:
        raise HistoryConflict("assignee_not_found")
    if assignee.business_role != "tiktok_bd_specialist":
        raise HistoryConflict("assignee_not_bd")

    dataset = request.dataset.model_dump(mode="json", exclude_unset=True)
    validate_recorded_dataset_shape(dataset)
    result = validate_data_validation_dataset(
        contracts=contracts,
        dataset=dataset,
        validation_clock=_aware(run.replay_as_of),
    )
    if result.status != "passed" or result.dataset_digest != run.dataset_digest:
        raise HistoryConflict("dataset_digest_mismatch")
    existing_batch = db.exec(select(TikTokHistoryBatch).where(
        TikTokHistoryBatch.tenant_id == user.tenant_id,
        TikTokHistoryBatch.recorded_run_id == run.id,
    )).first()
    if existing_batch is not None:
        if (existing_batch.source_kind != request.source_kind or
                existing_batch.assigned_bd_user_id != assignee.id):
            raise HistoryConflict("batch_metadata_conflict")
        return HistoryImportResult(
            batch_id=existing_batch.id, inserted_count=0, source_kind=existing_batch.source_kind,
        )

    batch = TikTokHistoryBatch(
        tenant_id=user.tenant_id,
        recorded_run_id=run.id,
        scope_id=scope.id,
        source_kind=request.source_kind,
        source_label=run.source_label or "recorded",
        assigned_bd_user_id=assignee.id,
        imported_by_user_id=user.id,
        dataset_digest=result.dataset_digest,
    )
    db.add(batch)
    inserted = 0
    for collection, (domain, key_name) in COLLECTIONS.items():
        for values in dataset[collection]:
            key = str(values[key_name])
            observed = datetime.fromisoformat(str(values["observed_at"]))
            observed = _aware(observed)
            digest = _digest(values)
            existing = db.exec(select(TikTokHistoryFact).where(
                TikTokHistoryFact.tenant_id == user.tenant_id,
                TikTokHistoryFact.scope_id == scope.id,
                TikTokHistoryFact.source_label == batch.source_label,
                TikTokHistoryFact.domain == domain,
                TikTokHistoryFact.business_key == key,
                TikTokHistoryFact.observed_at == observed,
            )).first()
            if existing is not None:
                if existing.fact_digest != digest:
                    raise HistoryConflict("fact_identity_conflict")
                continue
            db.add(TikTokHistoryFact(
                tenant_id=user.tenant_id,
                scope_id=scope.id,
                batch_id=batch.id,
                source_label=batch.source_label,
                domain=domain,
                business_key=key,
                observed_at=observed,
                values_json=values,
                fact_digest=digest,
            ))
            inserted += 1
    _metric_definitions(db, user.tenant_id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = db.exec(select(TikTokHistoryBatch).where(
            TikTokHistoryBatch.tenant_id == user.tenant_id,
            TikTokHistoryBatch.recorded_run_id == run.id,
        )).first()
        if concurrent is None or (
            concurrent.source_kind != request.source_kind
            or concurrent.assigned_bd_user_id != assignee.id
            or concurrent.dataset_digest != result.dataset_digest
        ):
            raise HistoryConflict("history_import_conflict") from None
        return HistoryImportResult(
            batch_id=concurrent.id, inserted_count=0, source_kind=concurrent.source_kind,
        )
    return HistoryImportResult(batch_id=batch.id, inserted_count=inserted, source_kind=batch.source_kind)


def record_reconciliation(
    db: Session,
    user: User,
    fact_id: str,
    request: ReconciliationRequest,
    *,
    now: datetime | None = None,
) -> ReconciliationRead:
    fact = db.exec(select(TikTokHistoryFact).where(
        TikTokHistoryFact.tenant_id == user.tenant_id,
        TikTokHistoryFact.id == fact_id,
    )).first()
    if fact is None:
        raise HistoryConflict("fact_not_found")
    batch = db.exec(select(TikTokHistoryBatch).where(
        TikTokHistoryBatch.tenant_id == user.tenant_id,
        TikTokHistoryBatch.id == fact.batch_id,
    )).one()
    if not (
        user.status == "active"
        and user.business_role == "tiktok_bd_specialist"
        and user.id == batch.assigned_bd_user_id
    ):
        raise HTTPException(status_code=403, detail="TikTok BD assignment required")
    row = TikTokHistoryReconciliation(
        tenant_id=user.tenant_id,
        fact_id=fact.id,
        verdict=request.verdict,
        reason=request.reason.strip(),
        reviewed_by_user_id=user.id,
        created_at=now or utc_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ReconciliationRead.model_validate(row, from_attributes=True)


def _review_snapshot(
    rows: list[TikTokHistoryFact],
    batches: dict[str, TikTokHistoryBatch],
    latest: dict[str, TikTokHistoryReconciliation],
) -> tuple[int, int, str]:
    latest_facts: dict[tuple[str, str, str], TikTokHistoryFact] = {}
    for row in sorted(rows, key=lambda item: (_aware(item.observed_at), item.id), reverse=True):
        if batches[row.batch_id].source_kind == "approved_redacted_history":
            latest_facts.setdefault((row.source_label, row.domain, row.business_key), row)
    eligible = list(latest_facts.values())
    accepted = [
        row for row in eligible
        if row.id in latest and latest[row.id].verdict in {"matched", "difference"}
    ]
    snapshot = [
        (row.id, latest[row.id].verdict, latest[row.id].reason)
        for row in sorted(eligible, key=lambda item: item.id)
        if row.id in latest
    ]
    return len(eligible), len(accepted), _digest(snapshot)


def confirm_history_reconciliation(
    db: Session,
    user: User,
    *,
    approval_ref: str,
) -> HistorySignoffRead:
    scope = db.exec(select(TikTokDataValidationScope).where(
        TikTokDataValidationScope.tenant_id == user.tenant_id,
        TikTokDataValidationScope.market == "US",
    ).with_for_update(read=True)).first()
    if scope is None or scope.status != "active" or scope.business_owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Pilot business owner required")
    if len(approval_ref.strip()) < 3:
        raise HistoryConflict("owner_approval_ref_required")
    rows = list(db.exec(select(TikTokHistoryFact).where(
        TikTokHistoryFact.tenant_id == user.tenant_id,
        TikTokHistoryFact.scope_id == scope.id,
    )).all())
    batches = {row.id: row for row in db.exec(select(TikTokHistoryBatch).where(
        TikTokHistoryBatch.tenant_id == user.tenant_id,
    )).all()}
    reviews = list(db.exec(select(TikTokHistoryReconciliation).where(
        TikTokHistoryReconciliation.tenant_id == user.tenant_id,
    ).order_by(TikTokHistoryReconciliation.created_at, TikTokHistoryReconciliation.id)).all())
    latest = {row.fact_id: row for row in reviews}
    total, accepted, digest = _review_snapshot(rows, batches, latest)
    if accepted < 30:
        raise HistoryConflict("thirty_reviews_required")
    if accepted != total:
        raise HistoryConflict("unresolved_reviews")
    signoff = TikTokHistorySignoff(
        tenant_id=user.tenant_id,
        scope_id=scope.id,
        scope_revision=scope.revision,
        review_digest=digest,
        reviewed_count=accepted,
        approval_ref=approval_ref.strip(),
        confirmed_by_user_id=user.id,
    )
    db.add(signoff)
    db.commit()
    db.refresh(signoff)
    return HistorySignoffRead.model_validate(signoff, from_attributes=True)


def get_history_workspace(
    db: Session,
    user: User,
    *,
    domain: str | None = None,
    creator_id: str | None = None,
    product_id: str | None = None,
    assigned_bd_user_id: str | None = None,
    observed_from: datetime | None = None,
    observed_until: datetime | None = None,
    page: int = 1,
    limit: int = 100,
) -> HistoryWorkspace:
    if page < 1 or limit < 1 or limit > 100 or domain not in {
        None, *(item[0] for item in COLLECTIONS.values())
    }:
        raise HTTPException(status_code=422, detail="Invalid history filter")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="Inactive user")
    if observed_from is not None and observed_from.utcoffset() is None:
        raise HTTPException(status_code=422, detail="Timezone required")
    if observed_until is not None and observed_until.utcoffset() is None:
        raise HTTPException(status_code=422, detail="Timezone required")
    if observed_from and observed_until and observed_from > observed_until:
        raise HTTPException(status_code=422, detail="Invalid history period")
    scope = db.exec(select(TikTokDataValidationScope).where(
        TikTokDataValidationScope.tenant_id == user.tenant_id,
        TikTokDataValidationScope.market == "US",
    )).first()
    if user.role != "admin" and user.business_role != "tiktok_bd_specialist" and (
        scope is None or scope.business_owner_user_id != user.id
    ):
        raise HTTPException(status_code=403, detail="TikTok pilot access required")
    rows = list(db.exec(select(TikTokHistoryFact).where(
        TikTokHistoryFact.tenant_id == user.tenant_id,
        TikTokHistoryFact.scope_id == scope.id if scope else "",
    ).order_by(TikTokHistoryFact.observed_at.desc(), TikTokHistoryFact.id)).all())
    batches = {row.id: row for row in db.exec(select(TikTokHistoryBatch).where(
        TikTokHistoryBatch.tenant_id == user.tenant_id,
    )).all()}
    reviews = list(db.exec(select(TikTokHistoryReconciliation).where(
        TikTokHistoryReconciliation.tenant_id == user.tenant_id,
    ).order_by(TikTokHistoryReconciliation.created_at, TikTokHistoryReconciliation.id)).all())
    latest = {row.fact_id: row for row in reviews}
    eligible_total, eligible, review_digest = _review_snapshot(rows, batches, latest)
    reviewed = sum(
        1 for row in rows
        if latest.get(row.id) is not None
        and latest[row.id].verdict in {"matched", "difference"}
    )
    filtered = [row for row in rows if (
        (domain is None or row.domain == domain)
        and (creator_id is None or row.values_json.get("creator_id") == creator_id)
        and (product_id is None or row.values_json.get("product_id") == product_id)
        and (assigned_bd_user_id is None or
             batches[row.batch_id].assigned_bd_user_id == assigned_bd_user_id)
        and (observed_from is None or _aware(row.observed_at) >= observed_from)
        and (observed_until is None or _aware(row.observed_at) <= observed_until)
    )]
    visible = filtered[(page - 1) * limit:page * limit]
    definitions = list(db.exec(select(TikTokHistoryMetricDefinition).where(
        TikTokHistoryMetricDefinition.tenant_id == user.tenant_id,
    ).order_by(TikTokHistoryMetricDefinition.code)).all())
    if not definitions:
        definitions = [TikTokHistoryMetricDefinition(
            tenant_id=user.tenant_id, code=code, label=label, formula=formula,
            unit=unit, numerator=numerator, denominator=denominator,
        ) for code, label, formula, unit, numerator, denominator in METRICS]
    metrics = _evaluate_metrics(filtered, definitions)
    signoff = db.exec(select(TikTokHistorySignoff).where(
        TikTokHistorySignoff.tenant_id == user.tenant_id,
        TikTokHistorySignoff.scope_id == scope.id if scope else "",
    ).order_by(TikTokHistorySignoff.created_at.desc(), TikTokHistorySignoff.id.desc())).first()
    bd_users = db.exec(select(User).where(
        User.tenant_id == user.tenant_id,
        User.status == "active",
        User.business_role == "tiktok_bd_specialist",
    ).order_by(User.username)).all()
    return HistoryWorkspace(
        tenant_id=user.tenant_id,
        total_count=len(filtered),
        reviewed_count=reviewed,
        eligible_reviewed_count=eligible,
        exit_ready=(
            scope is not None and scope.status == "active"
            and signoff is not None and eligible >= 30 and eligible == eligible_total
            and signoff.scope_revision == scope.revision
            and signoff.review_digest == review_digest
        ),
        can_confirm=(scope is not None and scope.status == "active"
                     and scope.business_owner_user_id == user.id),
        facts=[HistoryFactRead(
            id=row.id,
            tenant_id=row.tenant_id,
            domain=row.domain,
            business_key=row.business_key,
            observed_at=row.observed_at,
            source_label=row.source_label,
            source_kind=batches[row.batch_id].source_kind,
            assigned_bd_user_id=batches[row.batch_id].assigned_bd_user_id,
            values=row.values_json,
            latest_verdict=latest[row.id].verdict if row.id in latest else None,
        ) for row in visible],
        metrics=metrics,
        bd_options=([{"id": bd.id, "label": bd.username} for bd in bd_users]
                    if user.role == "admin" else []),
    )


def _evaluate_metrics(
    facts: list[TikTokHistoryFact],
    definitions: list[TikTokHistoryMetricDefinition],
) -> list[HistoryMetricRead]:
    latest_facts: dict[tuple[str, str], TikTokHistoryFact] = {}
    for fact in facts:
        latest_facts.setdefault((fact.domain, fact.business_key), fact)
    facts = list(latest_facts.values())
    counts = {domain: sum(row.domain == domain for row in facts) for domain, _ in COLLECTIONS.values()}
    delivered = sum(
        row.domain == "logistics" and row.values_json.get("status") == "delivered"
        for row in facts
    )
    views = sum(
        int(row.values_json.get("view_count") or 0) for row in facts if row.domain == "video"
    )
    likes = sum(
        int(row.values_json.get("like_count") or 0) for row in facts if row.domain == "video"
    )
    currencies = {str(row.values_json.get("currency")) for row in facts if row.domain == "gmv"}
    gmv_value: str | None = None
    gmv_reason: str | None = "gmv_missing"
    if len(currencies) > 1:
        gmv_reason = "currency_conflict"
    elif len(currencies) == 1:
        try:
            gmv_value = str(sum(
                Decimal(str(row.values_json["amount"]))
                for row in facts if row.domain == "gmv"
            ))
            gmv_reason = None
        except (InvalidOperation, KeyError):
            gmv_reason = "amount_invalid"
    values = {
        "sample_count": str(counts["sample"]) if counts["sample"] else None,
        "delivered_count": str(delivered) if counts["logistics"] else None,
        "video_views": str(views) if counts["video"] else None,
        "video_likes": str(likes) if counts["video"] else None,
        "order_count": str(counts["order"]) if counts["order"] else None,
        "gmv": gmv_value,
    }
    return [HistoryMetricRead(
        code=row.code,
        version=row.version,
        label=row.label,
        value=values.get(row.code),
        unit=next(iter(currencies)) if row.code == "gmv" and gmv_value else row.unit,
        reason=(gmv_reason if row.code == "gmv" else
                None if values.get(row.code) is not None else "source_missing"),
        formula=row.formula,
        timezone=row.timezone,
        window=row.window,
    ) for row in definitions]
