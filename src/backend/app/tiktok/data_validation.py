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
    TikTokDataValidationBlocker,
    TikTokDataValidationBootstrapResponse,
    TikTokDataValidationOption,
    TikTokDataValidationReadiness,
    TikTokDataValidationRunRead,
    TikTokDataValidationScopeRead,
    TikTokDataValidationWorkspace,
    TikTokFieldContractRead,
    TikTokFieldSource,
)

DATA_VALIDATION_CATALOG_VERSION = "p3-b0.v1"

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
                TikTokCapabilityEvidence.tenant_id == user.tenant_id,
                TikTokCapabilityEvidence.subject_key == "global",
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
    """Return a conservative baseline; Task 3 adds the complete gate rules."""

    del scope, latest_run, active_authorizations, now, has_recorded_or_real_validation
    if len(field_contracts) != len(FIELD_CATALOG) or len(evidence) != len(
        CAPABILITY_CATALOG + PROVIDER_CATALOG
    ):
        blockers = [
            TikTokDataValidationBlocker(
                code="catalog_not_bootstrapped",
                target_type="workspace",
                target_code=DATA_VALIDATION_CATALOG_VERSION,
                detail="数据验证目录尚未完整初始化。",
            )
        ]
    else:
        blockers = [
            TikTokDataValidationBlocker(
                code="workspace_configuration_incomplete",
                target_type="workspace",
                target_code=DATA_VALIDATION_CATALOG_VERSION,
                detail="范围、字段与证据仍需配置。",
            )
        ]
    return TikTokDataValidationReadiness(
        workbench_ready=False,
        real_data_ready=False,
        blockers=blockers,
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
