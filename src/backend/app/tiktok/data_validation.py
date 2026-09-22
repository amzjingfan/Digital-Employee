from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

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
from app.tiktok.schema import (
    TikTokCapabilityEvidenceRead,
    TikTokCapabilityEvidenceUpdate,
    TikTokDataValidationBlocker,
    TikTokDataValidationBootstrapResponse,
    TikTokDataValidationOption,
    TikTokDataValidationReadiness,
    TikTokDataValidationRunRead,
    TikTokDataValidationScopeRead,
    TikTokDataValidationScopeUpdate,
    TikTokDataValidationWorkspace,
    TikTokFieldContractRead,
    TikTokFieldContractUpdate,
    TikTokFieldSource,
)

DATA_VALIDATION_CATALOG_VERSION = "p3-b0.v1"


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
    latest_run: TikTokDataValidationRun | None,
    active_authorizations: Sequence[ExternalAuthorization],
    now: datetime,
    has_recorded_or_real_validation: bool,
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

    if latest_run is None:
        add(workbench_blockers, "mock_run_missing", "run", "latest", "尚无 Mock 校验运行。")
    elif (
        latest_run.status != "passed"
        or latest_run.catalog_version != DATA_VALIDATION_CATALOG_VERSION
        or not latest_run.dataset_digest.startswith("sha256:")
    ):
        add(
            workbench_blockers,
            "mock_run_not_current_or_failed",
            "run",
            latest_run.id,
            "最近 Mock 运行未通过当前目录版本。",
        )

    if not has_recorded_or_real_validation:
        add(
            real_blockers,
            "recorded_or_real_validation_missing",
            "workspace",
            DATA_VALIDATION_CATALOG_VERSION,
            "尚无真实数据或经批准的脱敏录制回放验证。",
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
            .order_by(TikTokDataValidationRun.created_at.desc())
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
    latest_run = run_rows[0] if run_rows else None
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
            latest_run=latest_run,
            active_authorizations=authorization_rows,
            now=utc_now(),
            has_recorded_or_real_validation=False,
        ),
    )
