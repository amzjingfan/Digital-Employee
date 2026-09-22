from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlmodel import Session, select

from app.db.models import (
    BusinessResource,
    ExternalAuthorization,
    TikTokCapabilityEvidence,
    TikTokDataValidationRun,
    TikTokDataValidationScope,
    TikTokFieldContract,
    User,
    utc_now,
)
from app.security.permissions import ensure_tenant_admin
from app.tiktok.recorded_validation import (
    ATTESTATION_VERSION,
    compute_contract_digest,
    normalize_recorded_dataset,
)
from app.tiktok.schema import (
    TikTokCapabilityEvidenceRead,
    TikTokCapabilityEvidenceUpdate,
    TikTokDataValidationBlocker,
    TikTokDataValidationBootstrapResponse,
    TikTokDataValidationCheck,
    TikTokDataValidationIssue,
    TikTokDataValidationOption,
    TikTokDataValidationReadiness,
    TikTokDataValidationRunRead,
    TikTokDataValidationScopeRead,
    TikTokDataValidationScopeUpdate,
    TikTokDataValidationWorkspace,
    TikTokFieldContractRead,
    TikTokFieldContractUpdate,
    TikTokFieldSource,
    TikTokMockValidationResult,
    TikTokRecordedValidationRequest,
)

DATA_VALIDATION_CATALOG_VERSION = "p3-b0.v1"
MOCK_VALIDATION_CLOCK = datetime(2026, 9, 22, 0, 0, tzinfo=UTC)
MOCK_DATASET: dict[str, list[dict[str, object]]] = {
    "samples": [
        {
            "application_id": "mock-application-001",
            "creator_id": "mock-creator-001",
            "product_id": "mock-product-001",
            "status": "approved",
            "applied_at": "2026-09-20T08:00:00Z",
            "fulfillment_due_at": "2026-09-25T08:00:00Z",
            "observed_at": "2026-09-21T23:00:00Z",
        }
    ],
    "orders": [
        {
            "order_id": "mock-order-001",
            "creator_id": "mock-creator-001",
            "product_id": "mock-product-001",
            "status": "completed",
            "created_at": "2026-09-20T09:00:00Z",
            "completed_at": "2026-09-21T09:00:00Z",
            "observed_at": "2026-09-21T23:00:00Z",
        }
    ],
    "logistics": [
        {
            "order_id": "mock-order-001",
            "tracking_number": "mock-tracking-001",
            "status": "delivered",
            "occurred_at": "2026-09-21T08:00:00Z",
            "observed_at": "2026-09-21T23:00:00Z",
        }
    ],
    "videos": [
        {
            "video_id": "mock-video-001",
            "creator_id": "mock-creator-001",
            "product_id": "mock-product-001",
            "published_at": "2026-09-20T10:00:00Z",
            "view_count": 100,
            "like_count": 10,
            "observed_at": "2026-09-21T23:00:00Z",
        }
    ],
    "attribution": [
        {
            "pid": "mock-pid-001",
            "order_id": "mock-order-001",
            "product_id": "mock-product-001",
            "window_start": "2026-09-19T00:00:00Z",
            "window_end": "2026-09-22T00:00:00Z",
            "observed_at": "2026-09-21T23:00:00Z",
        }
    ],
    "gmv": [
        {
            "order_id": "mock-order-001",
            "amount": "99.99",
            "currency": "USD",
            "occurred_at": "2026-09-21T09:00:00Z",
            "observed_at": "2026-09-21T23:00:00Z",
        }
    ],
}


class TikTokDataValidationNotFound(ValueError):
    """A catalog row or tenant-local reference was not found."""


class TikTokDataValidationConflict(ValueError):
    """An optimistic-concurrency revision no longer matches."""

FIELD_CODES = (
    "sample.application_id",
    "sample.creator_id",
    "sample.product_id",
    "sample.status",
    "sample.applied_at",
    "sample.fulfillment_due_at",
    "order.order_id",
    "order.creator_id",
    "order.product_id",
    "order.status",
    "order.created_at",
    "order.completed_at",
    "logistics.order_id",
    "logistics.tracking_number",
    "logistics.status",
    "logistics.occurred_at",
    "video.video_id",
    "video.creator_id",
    "video.product_id",
    "video.published_at",
    "video.view_count",
    "video.like_count",
    "attribution.pid",
    "attribution.order_id",
    "attribution.window_start",
    "attribution.window_end",
    "gmv.order_id",
    "gmv.amount",
    "gmv.currency",
    "gmv.occurred_at",
)

CAPABILITY_CODES = (
    "seller.shop.read",
    "seller.permissions.read",
    "seller.products.read",
    "seller.orders.read",
    "seller.logistics.read",
    "affiliate.samples.read",
    "affiliate.orders.read",
    "affiliate.gmv.read",
    "creator.profiles.read",
    "creator.videos.read",
    "partner.collaborations.read",
    "ads.campaigns.read",
    "ads.product_metrics.read",
    "ads.creative_metrics.read",
    "ads.attribution.read",
    "live.sessions.read",
    "live.products.read",
    "live.engagement.read",
    "live.gmv.read",
    "messaging.conversations.read",
    "messaging.suggestions.generate",
    "messaging.manual_send",
    "messaging.controlled_send",
    "customer_service.tickets.read",
    "customer_service.suggestions.generate",
    "customer_service.manual_send",
    "customer_service.controlled_send",
)

PROVIDER_CODES = (
    "provider.fastmoss",
    "provider.lingxing_erp",
    "provider.dami_ultra",
    "provider.feishu",
)

PROVIDER_LABELS = {
    "provider.fastmoss": "FastMoss",
    "provider.lingxing_erp": "领星 / ERP",
    "provider.dami_ultra": "达密 Ultra",
    "provider.feishu": "飞书",
}


@dataclass(frozen=True)
class _FieldCatalogItem:
    code: str
    domain: str
    label: str
    data_type: str
    business_key: str
    missing_behavior: str = "block_stage"


@dataclass(frozen=True)
class _EvidenceCatalogItem:
    code: str
    entry_kind: str
    platform_domain: str
    action: str
    direction: str


def _field_data_type(code: str) -> str:
    leaf = code.rsplit(".", 1)[1]
    if leaf.endswith("_at") or leaf.startswith("window_"):
        return "datetime"
    if leaf in {"view_count", "like_count"}:
        return "integer"
    if leaf == "amount":
        return "decimal"
    if leaf == "status":
        return "enum"
    return "string"


def _field_business_key(code: str) -> str:
    domain, leaf = code.split(".", 1)
    if domain == "sample":
        return "application_id"
    if domain in {"order", "logistics", "gmv"}:
        return "order_id"
    if domain == "video":
        return "video_id"
    if domain == "attribution":
        return "pid"
    return leaf


FIELD_CATALOG = tuple(
    _FieldCatalogItem(
        code=code,
        domain=code.split(".", 1)[0],
        label=code,
        data_type=_field_data_type(code),
        business_key=_field_business_key(code),
    )
    for code in FIELD_CODES
)

_PLATFORM_DOMAINS = {
    "seller": "Seller",
    "affiliate": "Affiliate",
    "creator": "Creator/Partner",
    "partner": "Creator/Partner",
    "ads": "Ads/GMV Max",
    "live": "LIVE",
    "messaging": "Messaging",
    "customer_service": "Customer Service",
}

CAPABILITY_CATALOG = tuple(
    _EvidenceCatalogItem(
        code=code,
        entry_kind="capability",
        platform_domain=_PLATFORM_DOMAINS[code.split(".", 1)[0]],
        action=code.split(".", 1)[1],
        direction="read" if code.endswith(".read") else "write",
    )
    for code in CAPABILITY_CODES
)

PROVIDER_CATALOG = tuple(
    _EvidenceCatalogItem(
        code=code,
        entry_kind="provider_decision",
        platform_domain=PROVIDER_LABELS[code],
        action="integration_decision",
        direction="decision",
    )
    for code in PROVIDER_CODES
)

_FIELD_ORDER = {code: index for index, code in enumerate(FIELD_CODES)}
_EVIDENCE_ORDER = {
    code: index for index, code in enumerate((*CAPABILITY_CODES, *PROVIDER_CODES))
}


def bootstrap_data_validation_workspace(
    db: Session, user: User
) -> TikTokDataValidationBootstrapResponse:
    """Add missing versioned catalog rows without changing tenant edits."""

    ensure_tenant_admin(user.tenant_id, user)
    existing_fields = set(
        db.exec(
            select(TikTokFieldContract.field_code).where(
                TikTokFieldContract.tenant_id == user.tenant_id
            )
        ).all()
    )
    existing_evidence = set(
        db.exec(
            select(TikTokCapabilityEvidence.entry_code).where(
                TikTokCapabilityEvidence.tenant_id == user.tenant_id
            )
        ).all()
    )

    created_field_count = 0
    for item in FIELD_CATALOG:
        if item.code in existing_fields:
            continue
        source = TikTokFieldSource(
            source_key=f"mock.{item.code}",
            source_type="mock_fixture",
            object_name=item.domain,
            field_path=item.code,
            priority=1,
            usage="mock",
            decision="use",
            authorization_state="not_required",
        )
        db.add(
            TikTokFieldContract(
                tenant_id=user.tenant_id,
                field_code=item.code,
                domain=item.domain,
                label=item.label,
                data_type=item.data_type,
                business_key=item.business_key,
                missing_behavior=item.missing_behavior,
                sources_json=[source.model_dump(mode="json")],
            )
        )
        created_field_count += 1

    created_evidence_count = 0
    for item in (*CAPABILITY_CATALOG, *PROVIDER_CATALOG):
        if item.code in existing_evidence:
            continue
        db.add(
            TikTokCapabilityEvidence(
                tenant_id=user.tenant_id,
                entry_code=item.code,
                entry_kind=item.entry_kind,
                platform_domain=item.platform_domain,
                action=item.action,
                direction=item.direction,
            )
        )
        created_evidence_count += 1

    db.commit()
    return TikTokDataValidationBootstrapResponse(
        catalog_version=DATA_VALIDATION_CATALOG_VERSION,
        created_field_count=created_field_count,
        created_evidence_count=created_evidence_count,
    )


def evaluate_data_validation_readiness(
    *,
    scope: TikTokDataValidationScope | None,
    field_contracts: Sequence[TikTokFieldContract],
    evidence: Sequence[TikTokCapabilityEvidence],
    latest_mock_run: TikTokDataValidationRun | None,
    latest_recorded_run: TikTokDataValidationRun | None,
    current_contract_digest: str,
    active_authorizations: Sequence[ExternalAuthorization],
    now: datetime,
) -> TikTokDataValidationReadiness:
    """Evaluate configuration and real-data gates without inferring cross-action evidence."""

    workbench_blockers: list[TikTokDataValidationBlocker] = []
    real_blockers: list[TikTokDataValidationBlocker] = []

    def add(
        collection: list[TikTokDataValidationBlocker],
        code: str,
        target_type: str,
        target_code: str,
        detail: str,
    ) -> None:
        collection.append(
            TikTokDataValidationBlocker(
                code=code,
                target_type=target_type,
                target_code=target_code,
                detail=detail,
            )
        )

    fields_by_code = {row.field_code: row for row in field_contracts}
    evidence_by_code = {row.entry_code: row for row in evidence}
    catalog_complete = set(fields_by_code) >= set(FIELD_CODES) and set(evidence_by_code) >= {
        *CAPABILITY_CODES,
        *PROVIDER_CODES,
    }
    if not catalog_complete:
        add(
            workbench_blockers,
            "catalog_not_bootstrapped",
            "workspace",
            DATA_VALIDATION_CATALOG_VERSION,
            "数据验证目录尚未完整初始化。",
        )

    if scope is None:
        add(workbench_blockers, "scope_missing", "scope", "US", "尚未配置 US 试点范围。")
    else:
        if scope.status != "active":
            add(
                workbench_blockers,
                "scope_not_active",
                "scope",
                "US",
                "US 试点范围必须处于 active。",
            )
        for value, code, detail in (
            (scope.store_resource_id, "scope_store_missing", "试点店铺未配置。"),
            (
                scope.creator_scope_summary.strip(),
                "scope_creator_summary_missing",
                "达人范围说明未配置。",
            ),
            (
                scope.business_owner_user_id,
                "scope_business_owner_missing",
                "业务 Owner 未配置。",
            ),
            (
                scope.data_owner_user_id,
                "scope_data_owner_missing",
                "数据 Owner 未配置。",
            ),
        ):
            if not value:
                add(workbench_blockers, code, "scope", "US", detail)

    for code in FIELD_CODES:
        row = fields_by_code.get(code)
        if row is None:
            add(
                workbench_blockers,
                "field_contract_missing",
                "field",
                code,
                "必需字段契约不存在。",
            )
            continue
        if not row.required:
            continue
        if row.status != "confirmed":
            add(workbench_blockers, "field_not_confirmed", "field", code, "字段尚未确认。")
        if not row.owner_user_id:
            add(workbench_blockers, "field_owner_missing", "field", code, "字段 Owner 缺失。")
        if not row.business_key.strip():
            add(
                workbench_blockers,
                "field_business_key_missing",
                "field",
                code,
                "字段业务键缺失。",
            )
        if row.freshness_sla_seconds is None or row.freshness_sla_seconds <= 0:
            add(
                workbench_blockers,
                "field_freshness_missing",
                "field",
                code,
                "字段新鲜度上限缺失。",
            )
        if row.missing_behavior == "unknown":
            add(
                workbench_blockers,
                "field_missing_behavior_unknown",
                "field",
                code,
                "字段缺失处理尚未确定。",
            )
        sources = [TikTokFieldSource.model_validate(item) for item in row.sources_json]
        if not any(
            source.usage == "mock"
            and source.decision == "use"
            and source.authorization_state == "not_required"
            for source in sources
        ):
            add(
                workbench_blockers,
                "field_mock_source_missing",
                "field",
                code,
                "字段缺少可用 Mock 来源。",
            )
        if not any(
            source.usage == "real"
            and source.decision == "use"
            and source.authorization_state == "authorized"
            for source in sources
        ):
            add(
                real_blockers,
                "field_real_source_missing",
                "field",
                code,
                "字段缺少已授权真实来源。",
            )

    for item in CAPABILITY_CATALOG:
        row = evidence_by_code.get(item.code)
        if row is None:
            add(
                workbench_blockers,
                "capability_evidence_missing",
                "capability",
                item.code,
                "能力盘点条目不存在。",
            )
            continue
        if row.status not in {"verified", "blocked", "not_applicable"}:
            add(
                workbench_blockers,
                "capability_conclusion_missing",
                "capability",
                item.code,
                "能力尚无明确结论。",
            )
        if not row.summary.strip() or not row.checked_by_user_id or row.checked_at is None:
            add(
                workbench_blockers,
                "capability_audit_missing",
                "capability",
                item.code,
                "能力结论缺少摘要、检查人或检查时间。",
            )
        if item.direction != "read" or row.status == "not_applicable":
            continue
        if row.status != "verified" or row.evidence_level != "E3" or row.evidence_type != "real_account":
            add(
                real_blockers,
                "capability_e3_missing",
                "capability",
                item.code,
                "目标读取动作缺少独立 E3 真实账号证据。",
            )
            continue
        if row.valid_until is not None and _time_at_or_before(row.valid_until, now):
            add(
                real_blockers,
                "capability_evidence_expired",
                "capability",
                item.code,
                "目标动作 E3 证据已过期。",
            )
            continue
        if scope is None or row.resource_id != scope.store_resource_id:
            add(
                real_blockers,
                "capability_resource_mismatch",
                "capability",
                item.code,
                "目标动作证据未绑定当前 US 试点店铺。",
            )
            continue
        authorization = next(
            (
                candidate
                for candidate in active_authorizations
                if candidate.status == "active"
                and candidate.subject_id == row.subject_key
                and candidate.resource_id == row.resource_id
                and row.required_scope
                and row.required_scope in candidate.scopes_json
                and (
                    candidate.expires_at is None
                    or not _time_at_or_before(candidate.expires_at, now)
                )
            ),
            None,
        )
        if authorization is None:
            add(
                real_blockers,
                "authorization_missing",
                "capability",
                item.code,
                "目标动作缺少匹配主体、资产和 scope 的有效授权。",
            )

    for item in PROVIDER_CATALOG:
        row = evidence_by_code.get(item.code)
        if row is None:
            add(
                workbench_blockers,
                "provider_decision_missing",
                "provider",
                item.code,
                "供应商接入决定不存在。",
            )
            continue
        if (
            row.decision not in {"use", "defer", "reject"}
            or not row.summary.strip()
            or not row.checked_by_user_id
            or row.checked_at is None
        ):
            add(
                workbench_blockers,
                "provider_decision_incomplete",
                "provider",
                item.code,
                "供应商决定缺少结论、理由、检查人或检查时间。",
            )

    if latest_mock_run is None:
        add(workbench_blockers, "mock_run_missing", "run", "latest", "尚无 Mock 校验运行。")
    elif (
        latest_mock_run.status != "passed"
        or latest_mock_run.catalog_version != DATA_VALIDATION_CATALOG_VERSION
        or not latest_mock_run.dataset_digest.startswith("sha256:")
    ):
        add(
            workbench_blockers,
            "mock_run_not_current_or_failed",
            "run",
            latest_mock_run.id,
            "最近 Mock 运行未通过当前目录版本。",
        )

    if latest_recorded_run is None:
        add(
            real_blockers,
            "recorded_or_real_validation_missing",
            "workspace",
            DATA_VALIDATION_CATALOG_VERSION,
            "尚无真实数据或经批准的脱敏录制回放验证。",
        )
    else:
        recorded_target = latest_recorded_run.id
        if latest_recorded_run.status != "passed":
            add(
                real_blockers,
                "latest_recorded_validation_failed",
                "run",
                recorded_target,
                "最近录制回放验证未通过。",
            )
        if (
            scope is None
            or latest_recorded_run.scope_id != scope.id
            or latest_recorded_run.scope_revision != scope.revision
        ):
            add(
                real_blockers,
                "recorded_validation_scope_stale",
                "run",
                recorded_target,
                "录制回放验证所用范围已变化。",
            )
        if latest_recorded_run.contract_digest != current_contract_digest:
            add(
                real_blockers,
                "recorded_validation_contract_stale",
                "run",
                recorded_target,
                "录制回放验证所用字段契约已变化。",
            )
        if (
            latest_recorded_run.approval_valid_until is None
            or _time_at_or_before(latest_recorded_run.approval_valid_until, now)
        ):
            add(
                real_blockers,
                "recorded_validation_approval_expired",
                "run",
                recorded_target,
                "录制回放审批已失效。",
            )
        if latest_recorded_run.catalog_version != DATA_VALIDATION_CATALOG_VERSION:
            add(
                real_blockers,
                "recorded_validation_catalog_stale",
                "run",
                recorded_target,
                "录制回放验证所用目录版本已变化。",
            )

    workbench_ready = not workbench_blockers
    blockers = _deduplicate_and_sort_blockers([*workbench_blockers, *real_blockers])
    return TikTokDataValidationReadiness(
        workbench_ready=workbench_ready,
        real_data_ready=workbench_ready and not real_blockers,
        blockers=blockers,
    )


def _time_at_or_before(value: datetime, now: datetime) -> bool:
    if value.tzinfo is None and now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    elif value.tzinfo is not None and now.tzinfo is None:
        value = value.replace(tzinfo=None)
    return value <= now


def _deduplicate_and_sort_blockers(
    blockers: Sequence[TikTokDataValidationBlocker],
) -> list[TikTokDataValidationBlocker]:
    unique = {
        (item.code, item.target_type, item.target_code): item
        for item in blockers
    }
    target_order = {
        **{code: index for index, code in enumerate(FIELD_CODES)},
        **{
            code: len(FIELD_CODES) + index
            for index, code in enumerate((*CAPABILITY_CODES, *PROVIDER_CODES))
        },
    }
    return sorted(
        unique.values(),
        key=lambda item: (
            target_order.get(item.target_code, -1),
            item.target_type,
            item.code,
        ),
    )


def _field_read(row: TikTokFieldContract) -> TikTokFieldContractRead:
    return TikTokFieldContractRead(
        id=row.id,
        tenant_id=row.tenant_id,
        field_code=row.field_code,
        domain=row.domain,
        label=row.label,
        data_type=row.data_type,
        required=row.required,
        owner_user_id=row.owner_user_id,
        business_key=row.business_key,
        freshness_sla_seconds=row.freshness_sla_seconds,
        missing_behavior=row.missing_behavior,
        sources=[TikTokFieldSource.model_validate(item) for item in row.sources_json],
        status=row.status,
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def update_data_validation_scope(
    db: Session,
    user: User,
    request: TikTokDataValidationScopeUpdate,
) -> TikTokDataValidationScopeRead:
    """Create or revise the current tenant's US pilot scope."""

    ensure_tenant_admin(user.tenant_id, user)
    store = db.exec(
        select(BusinessResource).where(
            BusinessResource.tenant_id == user.tenant_id,
            BusinessResource.id == request.store_resource_id,
            BusinessResource.resource_type == "store",
            BusinessResource.status == "active",
        )
    ).first()
    if (
        store is None
        or store.metadata_json.get("platform") != "tiktok"
        or store.metadata_json.get("market") != "US"
    ):
        raise TikTokDataValidationNotFound("store_not_found")
    _require_active_tenant_user(db, user.tenant_id, request.business_owner_user_id, "owner")
    _require_active_tenant_user(db, user.tenant_id, request.data_owner_user_id, "owner")

    row = db.exec(
        select(TikTokDataValidationScope).where(
            TikTokDataValidationScope.tenant_id == user.tenant_id,
            TikTokDataValidationScope.market == "US",
        )
    ).first()
    if row is None:
        if request.revision != 0:
            raise TikTokDataValidationConflict("revision_conflict")
        row = TikTokDataValidationScope(tenant_id=user.tenant_id, market="US")
    else:
        if request.revision != row.revision or request.revision == 0:
            raise TikTokDataValidationConflict("revision_conflict")
        row.revision += 1

    row.store_resource_id = request.store_resource_id
    row.creator_scope_summary = request.creator_scope_summary.strip()
    row.business_owner_user_id = request.business_owner_user_id
    row.data_owner_user_id = request.data_owner_user_id
    row.status = request.status
    row.updated_at = utc_now()
    db.add(row)
    db.commit()
    db.refresh(row)
    return TikTokDataValidationScopeRead.model_validate(row)


def update_field_contract(
    db: Session,
    user: User,
    field_code: str,
    request: TikTokFieldContractUpdate,
) -> TikTokFieldContractRead:
    """Revise one fixed catalog field with optimistic concurrency."""

    ensure_tenant_admin(user.tenant_id, user)
    row = db.exec(
        select(TikTokFieldContract).where(
            TikTokFieldContract.tenant_id == user.tenant_id,
            TikTokFieldContract.field_code == field_code,
        )
    ).first()
    if row is None or field_code not in _FIELD_ORDER:
        raise TikTokDataValidationNotFound("catalog_entry_not_found")
    _require_active_tenant_user(db, user.tenant_id, request.owner_user_id, "owner")
    if request.revision != row.revision:
        raise TikTokDataValidationConflict("revision_conflict")

    row.owner_user_id = request.owner_user_id
    row.business_key = request.business_key.strip()
    row.freshness_sla_seconds = request.freshness_sla_seconds
    row.missing_behavior = request.missing_behavior
    row.sources_json = [source.model_dump(mode="json") for source in request.sources]
    row.status = request.status
    row.revision += 1
    row.updated_at = utc_now()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _field_read(row)


def update_capability_evidence(
    db: Session,
    user: User,
    entry_code: str,
    request: TikTokCapabilityEvidenceUpdate,
) -> TikTokCapabilityEvidenceRead:
    """Revise one action-specific evidence or provider-decision row."""

    ensure_tenant_admin(user.tenant_id, user)
    row = db.exec(
        select(TikTokCapabilityEvidence).where(
            TikTokCapabilityEvidence.tenant_id == user.tenant_id,
            TikTokCapabilityEvidence.entry_code == entry_code,
        )
    ).first()
    if row is None or entry_code not in _EVIDENCE_ORDER:
        raise TikTokDataValidationNotFound("catalog_entry_not_found")
    if request.resource_id is not None:
        resource = db.exec(
            select(BusinessResource).where(
                BusinessResource.tenant_id == user.tenant_id,
                BusinessResource.id == request.resource_id,
                BusinessResource.status == "active",
            )
        ).first()
        if resource is None:
            raise TikTokDataValidationNotFound("store_not_found")
    if request.checked_by_user_id is not None:
        _require_active_tenant_user(
            db,
            user.tenant_id,
            request.checked_by_user_id,
            "checker",
        )
    if request.revision != row.revision:
        raise TikTokDataValidationConflict("revision_conflict")
    if row.entry_kind == "provider_decision" and (
        request.decision is None
        or not request.summary.strip()
        or request.checked_by_user_id is None
        or request.checked_at is None
    ):
        raise TikTokDataValidationConflict("provider_decision_incomplete")
    if row.entry_kind == "capability" and request.decision is not None:
        raise TikTokDataValidationConflict("capability_decision_not_allowed")

    row.subject_key = request.subject_key
    row.resource_id = request.resource_id
    row.required_scope = request.required_scope.strip()
    row.endpoint_or_artifact = request.endpoint_or_artifact.strip()
    row.api_version = request.api_version.strip()
    row.evidence_level = request.evidence_level
    row.evidence_type = request.evidence_type
    row.status = request.status
    row.decision = request.decision
    row.summary = request.summary.strip()
    row.evidence_ref = request.evidence_ref.strip()
    row.checked_by_user_id = request.checked_by_user_id
    row.checked_at = request.checked_at
    row.valid_until = request.valid_until
    row.revision += 1
    row.updated_at = utc_now()
    db.add(row)
    db.commit()
    db.refresh(row)
    return TikTokCapabilityEvidenceRead.model_validate(row)


def _require_active_tenant_user(
    db: Session,
    tenant_id: str,
    user_id: str,
    kind: str,
) -> User:
    row = db.exec(
        select(User).where(
            User.tenant_id == tenant_id,
            User.id == user_id,
            User.status == "active",
        )
    ).first()
    if row is None:
        code = "checker_not_found" if kind == "checker" else "owner_not_found"
        raise TikTokDataValidationNotFound(code)
    return row


def validate_data_validation_dataset(
    *,
    contracts: Sequence[TikTokFieldContract],
    dataset: Mapping[str, list[dict[str, object]]],
    validation_clock: datetime,
) -> TikTokMockValidationResult:
    """Validate normalized records without returning any source value."""

    canonical = json.dumps(
        {"catalog_version": DATA_VALIDATION_CATALOG_VERSION, "dataset": dataset},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
    issues: list[TikTokDataValidationIssue] = []
    checks: list[TikTokDataValidationCheck] = []
    collection_by_domain = {
        "sample": "samples",
        "order": "orders",
        "logistics": "logistics",
        "video": "videos",
        "attribution": "attribution",
        "gmv": "gmv",
    }

    def add_issue(code: str, field_code: str, detail: str) -> None:
        issues.append(
            TikTokDataValidationIssue(
                code=code,
                field_code=field_code,
                severity="error",
                detail=detail,
            )
        )

    def finish_check(code: str, start: int, checked_count: int) -> None:
        checks.append(
            TikTokDataValidationCheck(
                code=code,
                passed=len(issues) == start,
                checked_count=checked_count,
            )
        )

    start = len(issues)
    required_checked = 0
    required_domains = {
        contract.domain
        for contract in contracts
        if contract.required and contract.status != "not_applicable"
    }
    for domain in sorted(required_domains):
        collection = collection_by_domain.get(domain)
        if collection is not None and not dataset.get(collection):
            add_issue(
                "required_collection_empty",
                f"{domain}.*",
                "必需数据集合为空。",
            )
    for contract in contracts:
        records = dataset.get(collection_by_domain.get(contract.domain, ""), [])
        for record in records:
            required_checked += 1
            value = record.get(contract.field_code.split(".", 1)[1])
            if contract.required and (value is None or value == ""):
                add_issue(
                    "required_field_missing",
                    contract.field_code,
                    "必需字段缺失。",
                )
            elif value is not None and not _value_matches_type(value, contract.data_type):
                add_issue("invalid_field_type", contract.field_code, "字段类型不符合契约。")
    finish_check("required_and_type", start, required_checked)

    start = len(issues)
    uniqueness_checked = 0
    seen_domain_keys: set[tuple[str, str]] = set()
    for contract in contracts:
        identity = (contract.domain, contract.business_key)
        if identity in seen_domain_keys or not contract.business_key:
            continue
        seen_domain_keys.add(identity)
        records = dataset.get(collection_by_domain.get(contract.domain, ""), [])
        seen_values: set[object] = set()
        for record in records:
            uniqueness_checked += 1
            value = record.get(contract.business_key)
            if value is None or value == "":
                add_issue(
                    "business_key_missing",
                    f"{contract.domain}.{contract.business_key}",
                    "记录业务键缺失。",
                )
            elif value in seen_values:
                add_issue(
                    "duplicate_business_key",
                    f"{contract.domain}.{contract.business_key}",
                    "记录业务键重复。",
                )
            else:
                seen_values.add(value)
    finish_check("business_key_uniqueness", start, uniqueness_checked)

    start = len(issues)
    order_ids = {record.get("order_id") for record in dataset.get("orders", [])}
    relationship_checked = 0
    for collection in ("logistics", "attribution", "gmv"):
        for record in dataset.get(collection, []):
            relationship_checked += 1
            if record.get("order_id") not in order_ids:
                add_issue(
                    "broken_relationship",
                    f"{collection}.order_id",
                    "关联订单不存在。",
                )
    finish_check("relationships", start, relationship_checked)

    start = len(issues)
    amount_checked = 0
    for record in dataset.get("gmv", []):
        amount_checked += 1
        amount = record.get("amount")
        try:
            if amount is None or Decimal(str(amount)) < 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            add_issue("invalid_amount", "gmv.amount", "GMV 金额必须是非负十进制数。")
        currency = record.get("currency")
        if not isinstance(currency, str) or len(currency) != 3 or currency.upper() != currency:
            add_issue("invalid_currency", "gmv.currency", "币种必须是三位大写代码。")
    finish_check("amount_and_currency", start, amount_checked)

    start = len(issues)
    window_checked = 0
    for record in dataset.get("attribution", []):
        window_checked += 1
        window_start = _parse_datetime(record.get("window_start"))
        window_end = _parse_datetime(record.get("window_end"))
        if window_start is None or window_end is None or window_end <= window_start:
            add_issue(
                "inverted_attribution_window",
                "attribution.window_end",
                "归因窗口结束时间必须晚于开始时间。",
            )
    finish_check("time_windows", start, window_checked)

    start = len(issues)
    freshness_checked = 0
    sla_by_domain = {
        domain: min(
            row.freshness_sla_seconds
            for row in contracts
            if row.domain == domain and row.freshness_sla_seconds is not None
        )
        for domain in collection_by_domain
        if any(row.domain == domain and row.freshness_sla_seconds for row in contracts)
    }
    for domain, collection in collection_by_domain.items():
        sla = sla_by_domain.get(domain)
        if sla is None:
            continue
        for record in dataset.get(collection, []):
            freshness_checked += 1
            observed_at = _parse_datetime(record.get("observed_at"))
            if observed_at is None or (validation_clock - observed_at).total_seconds() > sla:
                add_issue("stale_record", f"{domain}.observed_at", "记录超过字段新鲜度上限。")
    finish_check("freshness", start, freshness_checked)

    start = len(issues)
    known_products = {
        record.get("product_id")
        for collection in ("samples", "orders", "attribution")
        for record in dataset.get(collection, [])
        if record.get("product_id")
    }
    pid_products: dict[object, object] = {}
    pid_checked = 0
    for record in dataset.get("attribution", []):
        pid_checked += 1
        pid = record.get("pid")
        product = record.get("product_id")
        if pid in pid_products and pid_products[pid] != product:
            add_issue(
                "pid_product_conflict",
                "attribution.pid",
                "同一 PID 对应多个商品。",
            )
        pid_products[pid] = product
    for record in dataset.get("videos", []):
        pid_checked += 1
        if record.get("product_id") not in known_products:
            add_issue(
                "pid_product_conflict",
                "video.product_id",
                "视频商品无法与 PID/商品范围关联。",
            )
    finish_check("pid_product_consistency", start, pid_checked)

    start = len(issues)
    source_checked = 0
    for contract in contracts:
        for source in contract.sources_json:
            source_checked += 1
            if source.get("decision") == "use" and source.get("authorization_state") == "denied":
                add_issue(
                    "selected_source_denied",
                    contract.field_code,
                    "被拒绝的来源不能作为选定来源。",
                )
    finish_check("selected_source_authorization", start, source_checked)

    unique_issues = {
        (item.code, item.field_code): item
        for item in issues
    }
    sorted_issues = sorted(unique_issues.values(), key=lambda item: (item.code, item.field_code))
    return TikTokMockValidationResult(
        catalog_version=DATA_VALIDATION_CATALOG_VERSION,
        dataset_digest=digest,
        record_count=sum(len(records) for records in dataset.values()),
        status="failed" if sorted_issues else "passed",
        checks=checks,
        issues=sorted_issues,
    )


def validate_mock_dataset(
    *,
    contracts: Sequence[TikTokFieldContract],
    dataset: Mapping[str, list[dict[str, object]]],
    validation_clock: datetime,
) -> TikTokMockValidationResult:
    """Compatibility wrapper for callers of the original Mock validator."""

    return validate_data_validation_dataset(
        contracts=contracts,
        dataset=dataset,
        validation_clock=validation_clock,
    )


def _value_matches_type(value: object, data_type: str) -> bool:
    if data_type in {"string", "enum"}:
        return isinstance(value, str)
    if data_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if data_type == "boolean":
        return isinstance(value, bool)
    if data_type == "decimal":
        try:
            Decimal(str(value))
        except (InvalidOperation, ValueError):
            return False
        return True
    if data_type == "datetime":
        return _parse_datetime(value) is not None
    return False


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def run_mock_data_validation(db: Session, user: User) -> TikTokDataValidationRunRead:
    """Run the fixed fixture and append one secret-free audit summary."""

    ensure_tenant_admin(user.tenant_id, user)
    contracts = list(
        db.exec(
            select(TikTokFieldContract).where(
                TikTokFieldContract.tenant_id == user.tenant_id
            )
        ).all()
    )
    if {row.field_code for row in contracts} != set(FIELD_CODES):
        raise TikTokDataValidationNotFound("catalog_entry_not_found")
    result = validate_data_validation_dataset(
        contracts=contracts,
        dataset=MOCK_DATASET,
        validation_clock=MOCK_VALIDATION_CLOCK,
    )
    scope = db.exec(
        select(TikTokDataValidationScope).where(
            TikTokDataValidationScope.tenant_id == user.tenant_id,
            TikTokDataValidationScope.market == "US",
        )
    ).first()
    evidence = list(
        db.exec(
            select(TikTokCapabilityEvidence).where(
                TikTokCapabilityEvidence.tenant_id == user.tenant_id
            )
        ).all()
    )
    authorizations = list(
        db.exec(
            select(ExternalAuthorization).where(
                ExternalAuthorization.tenant_id == user.tenant_id,
                ExternalAuthorization.status == "active",
            )
        ).all()
    )
    run = TikTokDataValidationRun(
        tenant_id=user.tenant_id,
        mode="mock",
        catalog_version=DATA_VALIDATION_CATALOG_VERSION,
        dataset_digest=result.dataset_digest,
        record_count=result.record_count,
        status=result.status,
        checks_json=[item.model_dump(mode="json") for item in result.checks],
        issues_json=[item.model_dump(mode="json") for item in result.issues],
        started_by_user_id=user.id,
    )
    latest_recorded_run = _latest_validation_run(db, user.tenant_id, "recorded")
    readiness = evaluate_data_validation_readiness(
        scope=scope,
        field_contracts=contracts,
        evidence=evidence,
        latest_mock_run=run,
        latest_recorded_run=latest_recorded_run,
        current_contract_digest=compute_contract_digest(contracts),
        active_authorizations=authorizations,
        now=MOCK_VALIDATION_CLOCK,
    )
    run.workbench_ready_snapshot = readiness.workbench_ready
    run.real_data_ready_snapshot = False
    if run.real_data_ready_snapshot:
        raise AssertionError("mock run cannot mark real data ready")
    db.add(run)
    db.commit()
    db.refresh(run)
    return TikTokDataValidationRunRead.model_validate(run)


def _latest_validation_run(
    db: Session, tenant_id: str, mode: str
) -> TikTokDataValidationRun | None:
    return db.exec(
        select(TikTokDataValidationRun)
        .where(
            TikTokDataValidationRun.tenant_id == tenant_id,
            TikTokDataValidationRun.mode == mode,
        )
        .order_by(
            TikTokDataValidationRun.created_at.desc(),
            TikTokDataValidationRun.id.desc(),
        )
    ).first()


def _validate_recorded_approval_times(
    request: TikTokRecordedValidationRequest, now: datetime
) -> None:
    ordered = (
        request.data_period_start,
        request.data_period_end,
        request.replay_as_of,
        request.approved_at,
        request.approval_valid_until,
    )
    if any(value.tzinfo is None or value.utcoffset() is None for value in ordered):
        raise TikTokDataValidationConflict("recorded_timezone_required")
    normalized = tuple(value.astimezone(UTC) for value in ordered)
    if not (
        normalized[0]
        <= normalized[1]
        <= normalized[2]
        <= normalized[3]
        < normalized[4]
    ):
        raise TikTokDataValidationConflict("recorded_time_order_invalid")
    normalized_now = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
    if normalized[3] > normalized_now:
        raise TikTokDataValidationConflict("recorded_approval_not_started")
    if normalized[4] <= normalized_now:
        raise TikTokDataValidationConflict("recorded_approval_expired")


def run_recorded_data_validation(
    db: Session,
    user: User,
    request: TikTokRecordedValidationRequest,
    *,
    now: datetime | None = None,
) -> TikTokDataValidationRunRead:
    """Run one approved replay and persist only its audit summary."""

    ensure_tenant_admin(user.tenant_id, user)
    validation_now = now or utc_now()
    scope = db.exec(
        select(TikTokDataValidationScope).where(
            TikTokDataValidationScope.tenant_id == user.tenant_id,
            TikTokDataValidationScope.market == "US",
        )
    ).first()
    if scope is None:
        raise TikTokDataValidationNotFound("scope_not_found")
    if scope.status != "active":
        raise TikTokDataValidationConflict("scope_not_active")
    if scope.revision != request.scope_revision:
        raise TikTokDataValidationConflict("scope_revision_conflict")

    contracts = list(
        db.exec(
            select(TikTokFieldContract).where(
                TikTokFieldContract.tenant_id == user.tenant_id
            )
        ).all()
    )
    if {row.field_code for row in contracts} != set(FIELD_CODES):
        raise TikTokDataValidationNotFound("catalog_entry_not_found")

    approver = db.exec(
        select(User).where(
            User.tenant_id == user.tenant_id,
            User.id == request.approved_by_user_id,
            User.status == "active",
        )
    ).first()
    if approver is None:
        raise TikTokDataValidationNotFound("approver_not_found")
    if approver.id == user.id:
        raise TikTokDataValidationConflict("approval_separation_required")
    _validate_recorded_approval_times(request, validation_now)

    contract_digest = compute_contract_digest(contracts)
    dataset = normalize_recorded_dataset(request)
    result = validate_data_validation_dataset(
        contracts=contracts,
        dataset=dataset,
        validation_clock=request.replay_as_of,
    )
    evidence = list(
        db.exec(
            select(TikTokCapabilityEvidence).where(
                TikTokCapabilityEvidence.tenant_id == user.tenant_id
            )
        ).all()
    )
    authorizations = list(
        db.exec(
            select(ExternalAuthorization).where(
                ExternalAuthorization.tenant_id == user.tenant_id,
                ExternalAuthorization.status == "active",
            )
        ).all()
    )
    latest_mock_run = _latest_validation_run(db, user.tenant_id, "mock")
    run = TikTokDataValidationRun(
        tenant_id=user.tenant_id,
        mode="recorded",
        catalog_version=DATA_VALIDATION_CATALOG_VERSION,
        dataset_digest=result.dataset_digest,
        record_count=result.record_count,
        status=result.status,
        checks_json=[item.model_dump(mode="json") for item in result.checks],
        issues_json=[item.model_dump(mode="json") for item in result.issues],
        started_by_user_id=user.id,
        source_label=request.source_label,
        approval_ref=request.approval_ref,
        approved_by_user_id=approver.id,
        approved_at=request.approved_at,
        approval_valid_until=request.approval_valid_until,
        data_period_start=request.data_period_start,
        data_period_end=request.data_period_end,
        replay_as_of=request.replay_as_of,
        scope_id=scope.id,
        scope_revision=scope.revision,
        contract_digest=contract_digest,
        attestation_version=ATTESTATION_VERSION,
    )
    readiness = evaluate_data_validation_readiness(
        scope=scope,
        field_contracts=contracts,
        evidence=evidence,
        latest_mock_run=latest_mock_run,
        latest_recorded_run=run,
        current_contract_digest=contract_digest,
        active_authorizations=authorizations,
        now=validation_now,
    )
    run.workbench_ready_snapshot = readiness.workbench_ready
    run.real_data_ready_snapshot = readiness.real_data_ready
    db.add(run)
    db.commit()
    db.refresh(run)
    return TikTokDataValidationRunRead.model_validate(run)


def get_data_validation_workspace(db: Session, user: User) -> TikTokDataValidationWorkspace:
    """Read a secret-free validation workspace scoped only by the current tenant."""

    tenant_id = user.tenant_id
    scope_row = db.exec(
        select(TikTokDataValidationScope).where(
            TikTokDataValidationScope.tenant_id == tenant_id,
            TikTokDataValidationScope.market == "US",
        )
    ).first()
    field_rows = list(
        db.exec(
            select(TikTokFieldContract).where(TikTokFieldContract.tenant_id == tenant_id)
        ).all()
    )
    evidence_rows = list(
        db.exec(
            select(TikTokCapabilityEvidence).where(
                TikTokCapabilityEvidence.tenant_id == tenant_id
            )
        ).all()
    )
    run_rows = list(
        db.exec(
            select(TikTokDataValidationRun)
            .where(TikTokDataValidationRun.tenant_id == tenant_id)
            .order_by(
                TikTokDataValidationRun.created_at.desc(),
                TikTokDataValidationRun.id.desc(),
            )
            .limit(20)
        ).all()
    )
    authorization_rows = list(
        db.exec(
            select(ExternalAuthorization).where(
                ExternalAuthorization.tenant_id == tenant_id,
                ExternalAuthorization.status == "active",
            )
        ).all()
    )
    store_rows = list(
        db.exec(
            select(BusinessResource).where(
                BusinessResource.tenant_id == tenant_id,
                BusinessResource.resource_type == "store",
                BusinessResource.status == "active",
            )
        ).all()
    )
    owner_rows = list(
        db.exec(
            select(User)
            .where(User.tenant_id == tenant_id, User.status == "active")
            .order_by(User.username)
        ).all()
    )

    field_rows.sort(key=lambda row: _FIELD_ORDER.get(row.field_code, len(_FIELD_ORDER)))
    evidence_rows.sort(
        key=lambda row: _EVIDENCE_ORDER.get(row.entry_code, len(_EVIDENCE_ORDER))
    )
    stores = [
        row
        for row in store_rows
        if row.metadata_json.get("platform") == "tiktok"
        and row.metadata_json.get("market") == "US"
    ]
    latest_mock_run = _latest_validation_run(db, tenant_id, "mock")
    latest_recorded_run = _latest_validation_run(db, tenant_id, "recorded")
    return TikTokDataValidationWorkspace(
        tenant_id=tenant_id,
        catalog_version=DATA_VALIDATION_CATALOG_VERSION,
        scope=(
            TikTokDataValidationScopeRead.model_validate(scope_row) if scope_row else None
        ),
        field_contracts=[_field_read(row) for row in field_rows],
        capability_evidence=[
            TikTokCapabilityEvidenceRead.model_validate(row) for row in evidence_rows
        ],
        recent_runs=[TikTokDataValidationRunRead.model_validate(row) for row in run_rows],
        store_options=[
            TikTokDataValidationOption(id=row.id, label=row.name)
            for row in sorted(stores, key=lambda item: item.name)
        ],
        owner_options=[
            TikTokDataValidationOption(id=row.id, label=row.display_name or row.username)
            for row in owner_rows
        ],
        readiness=evaluate_data_validation_readiness(
            scope=scope_row,
            field_contracts=field_rows,
            evidence=evidence_rows,
            latest_mock_run=latest_mock_run,
            latest_recorded_run=latest_recorded_run,
            current_contract_digest=compute_contract_digest(field_rows),
            active_authorizations=authorization_rows,
            now=utc_now(),
        ),
    )
