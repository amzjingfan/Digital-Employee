from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high", "critical"]
GateStatus = Literal["pass", "warn", "block"]


class RuleSourceReference(BaseModel):
    source_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=240)
    url: str = Field(default="", max_length=1000)
    retrieved_at: datetime


class ListingRuleSetCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    platform: str = Field(min_length=2, max_length=80)
    marketplace: str = Field(min_length=2, max_length=80)
    category: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    rules: dict[str, Any] = Field(default_factory=dict)
    source_references: list[RuleSourceReference] = Field(min_length=1, max_length=30)
    effective_at: datetime
    expires_at: datetime | None = None


class ListingRuleSetPublish(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    expected_digest: str = Field(min_length=8, max_length=160)
    review_note: str = Field(min_length=4, max_length=1000)


class ListingRuleSetRead(BaseModel):
    id: str
    tenant_id: str
    platform: str
    marketplace: str
    category: str
    version: str
    status: Literal["draft", "published", "retired"]
    rules: dict[str, Any]
    content_digest: str
    source_references: list[dict[str, Any]]
    effective_at: datetime
    expires_at: datetime | None
    created_by_user_id: str
    reviewed_by_user_id: str | None
    reviewed_at: datetime | None
    created_at: datetime


class ListingComplianceRun(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    check_key: str = Field(min_length=8, max_length=160)
    store_resource_id: str = Field(min_length=1, max_length=128)
    product_key: str = Field(min_length=1, max_length=160)
    sku: str = Field(min_length=1, max_length=120)
    language: str = Field(min_length=2, max_length=24)
    rule_set_id: str = Field(min_length=1, max_length=128)
    sku_fact_version: str = Field(min_length=1, max_length=80)
    sku_facts: dict[str, Any]
    content: dict[str, Any]
    asset_version_ids: list[str] = Field(default_factory=list, max_length=50)


class ComplianceFindingRead(BaseModel):
    location: str
    risk: RiskLevel
    rule: str
    evidence: str
    suggestion: str
    gate: GateStatus


class ListingComplianceCheckRead(BaseModel):
    id: str
    tenant_id: str
    check_key: str
    store_resource_id: str
    product_key: str
    sku: str
    language: str
    rule_set_id: str
    rule_version: str
    rule_digest: str
    sku_fact_version: str
    sku_facts: dict[str, Any]
    content: dict[str, Any]
    asset_version_ids: list[str]
    findings: list[ComplianceFindingRead]
    gate_status: GateStatus
    input_digest: str
    task_id: str
    created_by_user_id: str
    created_at: datetime


class CreativeBriefCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    brief_key: str = Field(min_length=8, max_length=160)
    store_resource_id: str = Field(min_length=1, max_length=128)
    product_key: str = Field(min_length=1, max_length=160)
    language: str = Field(min_length=2, max_length=24)
    dimensions: dict[str, Any]
    selling_points: list[str] = Field(min_length=1, max_length=20)
    scenes: list[str] = Field(min_length=1, max_length=20)
    required_assets: list[str] = Field(min_length=1, max_length=30)
    constraints: dict[str, Any] = Field(default_factory=dict)
    fact_snapshot: dict[str, Any] = Field(default_factory=dict)
    brand_snapshot: dict[str, Any] = Field(default_factory=dict)
    platform_spec_snapshot: dict[str, Any] = Field(default_factory=dict)
    due_at: datetime | None = None


class CreativeBriefRead(BaseModel):
    id: str
    tenant_id: str
    brief_key: str
    store_resource_id: str
    product_key: str
    language: str
    dimensions: dict[str, Any]
    selling_points: list[str]
    scenes: list[str]
    required_assets: list[str]
    constraints: dict[str, Any]
    fact_snapshot: dict[str, Any]
    brand_snapshot: dict[str, Any]
    platform_spec_snapshot: dict[str, Any]
    snapshot_digest: str
    status: Literal["open", "in_progress", "completed", "cancelled"]
    task_id: str
    due_at: datetime | None
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


class CreativeAssetVersionCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    asset_key: str = Field(min_length=4, max_length=160)
    brief_id: str = Field(min_length=1, max_length=128)
    parent_version_id: str | None = Field(default=None, max_length=128)
    asset_type: Literal[
        "main_image",
        "secondary_image",
        "a_plus",
        "brand_story",
        "video",
        "ad_creative",
        "packaging",
    ]
    file_reference: str = Field(min_length=4, max_length=1000)
    file_digest: str = Field(min_length=8, max_length=160)
    provenance: dict[str, Any]
    generation_parameters: dict[str, Any] = Field(default_factory=dict)
    checks: dict[str, Any]
    contains_sensitive_claims: bool = False


class CreativeAssetUploadRead(BaseModel):
    """Server-authoritative manifest returned after a creative file is staged."""

    upload_id: str
    filename: str
    content_type: str
    size: int
    file_reference: str
    file_digest: str
    media_metadata: dict[str, Any] = Field(default_factory=dict)


class CreativeAssetReview(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    decision: Literal["approved", "rejected"]
    note: str = Field(min_length=4, max_length=1000)


QCStatus = Literal["pass", "fail", "unknown", "not_applicable"]


class DesignQCFindingRead(BaseModel):
    check_key: str
    status: QCStatus
    severity: Literal["P0", "P1", "P2", "info"]
    rule: str
    evidence: str
    checker_version: str


class DesignQCRun(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    asset_version_id: str = Field(min_length=1, max_length=128)
    checker_version: str = Field(default="joukir-design-qc-v1", min_length=1, max_length=80)


class DesignQCReportRead(BaseModel):
    id: str
    tenant_id: str
    asset_version_id: str
    asset_digest: str
    brief_id: str
    store_resource_id: str
    snapshot_digest: str
    checker_version: str
    overall_status: QCStatus
    findings: list[DesignQCFindingRead]
    input_digest: str
    created_by_user_id: str
    created_at: datetime


EvidenceType = Literal["facts", "brand", "platform_spec"]
EvidenceStatus = Literal["draft", "verified", "expired", "revoked"]


class CreativeEvidenceSyncItem(BaseModel):
    evidence_type: EvidenceType
    source_ref: str = Field(min_length=1, max_length=240)
    version: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any]
    status: EvidenceStatus = "verified"
    effective_at: datetime
    expires_at: datetime | None = None


class CreativeEvidenceSyncRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    records: list[CreativeEvidenceSyncItem] = Field(min_length=1, max_length=100)


class CreativeEvidenceRead(BaseModel):
    id: str
    tenant_id: str
    evidence_type: EvidenceType
    source_ref: str
    version: str
    payload: dict[str, Any]
    content_digest: str
    status: EvidenceStatus
    effective_at: datetime
    expires_at: datetime | None
    synced_at: datetime
    sync_error: str | None
    created_by_user_id: str
    updated_at: datetime


class CreativeDeliveryChecklistCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    brief_id: str = Field(min_length=1, max_length=128)
    asset_version_ids: list[str] = Field(min_length=1, max_length=50)


class CreativeDeliveryChecklistRead(BaseModel):
    id: str
    tenant_id: str
    brief_id: str
    store_resource_id: str
    product_key: str
    asset_version_ids: list[str]
    qc_report_ids: list[str]
    checklist: list[dict[str, Any]]
    blockers: list[dict[str, Any]]
    delivery_digest: str
    status: Literal["blocked", "ready", "delivered", "failed"]
    created_by_user_id: str
    delivered_at: datetime | None
    created_at: datetime


class CreativeGenerationSubmit(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    brief_id: str = Field(min_length=1, max_length=128)
    provider_key: str = Field(min_length=1, max_length=80)
    idempotency_key: str = Field(min_length=8, max_length=180)
    instructions: dict[str, Any] = Field(default_factory=dict)


class CreativeGenerationRead(BaseModel):
    id: str
    tenant_id: str
    brief_id: str
    provider_key: str
    idempotency_key: str
    status: Literal["queued", "submitted", "succeeded", "failed", "cancelled"]
    request: dict[str, Any]
    response: dict[str, Any]
    external_request_id: str | None
    error_code: str | None
    error_message: str | None
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


class CreativeAssetVersionRead(BaseModel):
    id: str
    tenant_id: str
    asset_key: str
    version: int
    brief_id: str
    parent_version_id: str | None
    store_resource_id: str
    product_key: str
    asset_type: str
    file_reference: str
    file_digest: str
    provenance: dict[str, Any]
    generation_parameters: dict[str, Any]
    checks: dict[str, Any]
    required_human_approval: bool
    status: Literal["draft", "pending_review", "approved", "rejected"]
    creator_user_id: str
    reviewed_by_user_id: str | None
    review_note: str | None
    reviewed_at: datetime | None
    created_at: datetime


class ProcurementRecommendationCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    recommendation_key: str = Field(min_length=8, max_length=160)
    supplier_resource_id: str = Field(min_length=1, max_length=128)
    store_resource_id: str | None = Field(default=None, max_length=128)
    product_key: str = Field(min_length=1, max_length=160)
    sku: str = Field(min_length=1, max_length=120)
    forecast_daily_sales: float = Field(ge=0, le=1_000_000)
    planning_horizon_days: int = Field(ge=1, le=365)
    available_units: int = Field(ge=0, le=100_000_000)
    inbound_units: int = Field(ge=0, le=100_000_000)
    safety_stock_units: int = Field(ge=0, le=100_000_000)
    promotion_units: int = Field(default=0, ge=0, le=100_000_000)
    advertising_lift_units: int = Field(default=0, ge=0, le=100_000_000)
    moq: int = Field(ge=1, le=100_000_000)
    lead_time_days: int = Field(ge=0, le=730)
    quote_unit_cost: float = Field(ge=0, le=1_000_000)
    freight_unit_cost: float = Field(default=0, ge=0, le=1_000_000)
    duty_unit_cost: float = Field(default=0, ge=0, le=1_000_000)
    quote_observed_at: datetime
    qc_failure_rate: float = Field(default=0, ge=0, le=1)
    cash_budget: float = Field(ge=0, le=1_000_000_000)
    currency: str = Field(min_length=3, max_length=3)


class ProcurementRecommendationReview(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    decision: Literal["reviewed", "rejected"]
    note: str = Field(min_length=4, max_length=1000)


class ProcurementRecommendationRead(BaseModel):
    id: str
    tenant_id: str
    recommendation_key: str
    supplier_resource_id: str
    store_resource_id: str | None
    product_key: str
    sku: str
    input_snapshot: dict[str, Any]
    formula: str
    recommended_quantity: int
    estimated_landed_cost: float
    lead_time_days: int
    risk_level: RiskLevel
    risk_reasons: list[str]
    status: Literal["draft", "reviewed", "rejected"]
    task_id: str
    created_by_user_id: str
    reviewed_by_user_id: str | None
    review_note: str | None
    reviewed_at: datetime | None
    created_at: datetime


class ProductLaunchGateCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    launch_key: str = Field(min_length=8, max_length=160)
    store_resource_id: str = Field(min_length=1, max_length=128)
    supplier_resource_id: str = Field(min_length=1, max_length=128)
    product_key: str = Field(min_length=1, max_length=160)
    sku: str = Field(min_length=1, max_length=120)
    sku_fact_version: str = Field(min_length=1, max_length=80)
    bom_version: str = Field(min_length=1, max_length=80)
    packaging_version: str = Field(min_length=1, max_length=80)
    certification_ids: list[str] = Field(default_factory=list, max_length=50)
    listing_check_id: str = Field(min_length=1, max_length=128)
    asset_version_ids: list[str] = Field(min_length=1, max_length=50)
    procurement_recommendation_id: str = Field(min_length=1, max_length=128)
    supplier_lead_time_confirmed: bool = False


class ProductLaunchSubmit(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=0)
    listing_id: str = Field(min_length=1, max_length=160)
    marketplace: str = Field(min_length=2, max_length=80)
    product_type: str = Field(min_length=1, max_length=160)
    attributes: dict[str, Any]
    summary: str = Field(min_length=8, max_length=500)


class ProductLaunchGateRead(BaseModel):
    id: str
    tenant_id: str
    launch_key: str
    store_resource_id: str
    supplier_resource_id: str
    product_key: str
    sku: str
    sku_fact_version: str
    bom_version: str
    packaging_version: str
    certification_ids: list[str]
    supplier_lead_time_confirmed: bool
    listing_check_id: str
    asset_version_ids: list[str]
    procurement_recommendation_id: str
    blockers: list[dict[str, Any]]
    evidence_digest: str
    status: Literal["blocked", "ready", "waiting_approval", "approved", "rejected"]
    approval_request_id: str | None
    approval_status: str | None
    task_id: str
    version: int
    created_at: datetime
    updated_at: datetime


class ProductQualityIssueRead(BaseModel):
    id: str
    tenant_id: str
    source_case_id: str
    store_resource_id: str
    product_key: str
    category: str
    root_cause: str
    task_ids: list[str]
    status: Literal["open", "investigating", "resolved"]
    created_at: datetime
    updated_at: datetime


class ProductLifecycleOverview(BaseModel):
    published_rule_sets: int
    blocked_listing_checks: int
    creative_assets_waiting_review: int
    procurement_recommendations_waiting_review: int
    launch_gates_blocked: int
    launch_gates_waiting_approval: int
    open_quality_issues: int
