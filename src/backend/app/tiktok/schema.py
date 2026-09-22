from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TikTokRoleRead(BaseModel):
    key: str
    label: str
    casdoor_group: str
    description: str


class OrganizationUnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_id: str | None = None
    unit_type: str
    code: str
    name: str
    status: str
    revision: int
    role_key: str | None = None


class TikTokResourceRead(BaseModel):
    id: str
    resource_type: str
    code: str
    name: str
    status: str
    market: str | None = None
    access_level: str


class TikTokAuthorizationRead(BaseModel):
    id: str
    authorization_type: str
    subject_id: str
    resource_id: str | None = None
    scopes: list[str] = Field(default_factory=list)
    status: str
    expires_at: datetime | None = None


class TikTokAuthorizationExchange(BaseModel):
    state: str = Field(min_length=20, max_length=200)
    code: str = Field(min_length=20, max_length=200)
    code_verifier: str = Field(min_length=43, max_length=128)


class TikTokOfficialAuthorizationStart(BaseModel):
    authorization_type: Literal["seller", "creator", "partner"] = "seller"
    market: Literal["US", "ROW"] = "ROW"
    scopes: list[str] = Field(min_length=1, max_length=30)
    return_to: str = Field(default="/enterprise/tiktok", max_length=200)


class TikTokShadowQualityRead(BaseModel):
    reviewed_count: int
    adopted_count: int
    needs_revision_count: int
    rejected_count: int
    guardrail_issue_count: int
    adoption_rate: float
    covered_sop_ids: list[str] = Field(default_factory=list)
    missing_sop_ids: list[str] = Field(default_factory=list)
    minimum_reviewed_count: int
    passed: bool


class TikTokShadowRunRead(BaseModel):
    id: str
    status: str
    started_at: datetime
    ends_at: datetime
    last_heartbeat_at: datetime
    observation_count: int
    error_count: int
    baseline: dict[str, Any]
    quality: TikTokShadowQualityRead


class TikTokShadowEvaluationCreate(BaseModel):
    task_id: str = Field(min_length=3, max_length=100)
    verdict: Literal["adopted", "needs_revision", "rejected"]
    issue_category: Literal[
        "none",
        "severe_miss",
        "unauthorized_access",
        "false_claim",
        "unapproved_external_write",
        "other",
    ] = "none"
    summary: str = Field(min_length=3, max_length=500)


class TikTokShadowEvaluationRead(BaseModel):
    shadow_run_id: str
    task_id: str
    verdict: Literal["adopted", "needs_revision", "rejected"]
    issue_category: str
    recorded_at: datetime
    quality: TikTokShadowQualityRead


class TikTokProductionGateRead(BaseModel):
    key: str
    label: str
    status: Literal["passed", "waiting", "blocked"]
    detail: str


class TikTokProductionReadiness(BaseModel):
    ready: bool
    evaluated_at: datetime
    gates: list[TikTokProductionGateRead] = Field(default_factory=list)


class TikTokAgentReleasePreflightItem(BaseModel):
    slug: str
    name: str
    business_role: str
    agent_id: str | None = None
    release_state: str | None = None
    ready: bool
    error: str | None = None
    snapshot_digest: str | None = None


class TikTokAgentReleasePreflight(BaseModel):
    tenant_id: str
    ready: bool
    evaluated_at: datetime
    items: list[TikTokAgentReleasePreflightItem] = Field(default_factory=list)


class TikTokAgentReleasePublishResult(BaseModel):
    tenant_id: str
    approval_reference: str
    published_count: int
    releases: list[dict[str, Any]] = Field(default_factory=list)


class TikTokAgentReleasePublishRequest(BaseModel):
    approval_reference: str = Field(min_length=3, max_length=200)


class TikTokM2MVerificationItem(BaseModel):
    agent_id: str | None = None
    application: str | None = None
    status: Literal["verified", "failed"]
    subject: str | None = None
    expires_at: datetime | None = None
    error_code: str | None = None


class TikTokM2MVerificationResponse(BaseModel):
    tenant_id: str
    verified_count: int
    failed_count: int
    items: list[TikTokM2MVerificationItem] = Field(default_factory=list)


class TikTokMockReplayRequest(BaseModel):
    persist: bool = False


class TikTokMockReplayExecutionItem(BaseModel):
    sop_id: str
    task_id: str
    status: str
    run_id: str | None = None
    run_status: str | None = None
    execution_snapshot_id: str | None = None
    snapshot_digest: str | None = None
    trace: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


class TikTokMockReplayExecutionResponse(BaseModel):
    execution_mode: Literal["sandbox"] = "sandbox"
    processed_count: int
    items: list[TikTokMockReplayExecutionItem] = Field(default_factory=list)


class TikTokOverview(BaseModel):
    root: OrganizationUnitRead | None = None
    departments: list[OrganizationUnitRead] = Field(default_factory=list)
    roles: list[TikTokRoleRead] = Field(default_factory=list)
    resources: list[TikTokResourceRead] = Field(default_factory=list)
    authorizations: list[TikTokAuthorizationRead] = Field(default_factory=list)
    task_counts: dict[str, int] = Field(default_factory=dict)


class TikTokAssetBootstrapResponse(BaseModel):
    created_count: int
    skill_ids: list[str] = Field(default_factory=list)
    agent_ids: list[str] = Field(default_factory=list)
    knowledge_base_ids: list[str] = Field(default_factory=list)
    tool_ids: list[str] = Field(default_factory=list)


class TikTokBootstrapResponse(BaseModel):
    created_count: int
    root: OrganizationUnitRead
    departments: list[OrganizationUnitRead]
    roles: list[TikTokRoleRead]
    assets: TikTokAssetBootstrapResponse | None = None


class TikTokMembershipReconcileResponse(BaseModel):
    reconciled_count: int


class TikTokFieldSource(BaseModel):
    source_key: str = Field(min_length=1, max_length=120)
    source_type: Literal[
        "official_api", "approved_export", "internal_database", "vendor", "mock_fixture"
    ]
    object_name: str = Field(min_length=1, max_length=160)
    field_path: str = Field(min_length=1, max_length=240)
    priority: int = Field(ge=1)
    usage: Literal["mock", "real"]
    decision: Literal["use", "defer", "reject"]
    authorization_state: Literal["not_required", "unverified", "authorized", "denied"]


class TikTokDataValidationBlocker(BaseModel):
    code: str
    target_type: Literal["workspace", "scope", "field", "capability", "provider", "run"]
    target_code: str
    detail: str


class TikTokDataValidationReadiness(BaseModel):
    workbench_ready: bool
    real_data_ready: bool
    blockers: list[TikTokDataValidationBlocker] = Field(default_factory=list)


class TikTokDataValidationScopeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    market: str
    store_resource_id: str | None = None
    creator_scope_summary: str
    business_owner_user_id: str | None = None
    data_owner_user_id: str | None = None
    status: str
    revision: int
    created_at: datetime
    updated_at: datetime


class TikTokFieldContractRead(BaseModel):
    id: str
    tenant_id: str
    field_code: str
    domain: str
    label: str
    data_type: str
    required: bool
    owner_user_id: str | None = None
    business_key: str
    freshness_sla_seconds: int | None = None
    missing_behavior: str
    sources: list[TikTokFieldSource] = Field(default_factory=list)
    status: str
    revision: int
    created_at: datetime
    updated_at: datetime


class TikTokCapabilityEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    entry_code: str
    entry_kind: str
    platform_domain: str
    action: str
    direction: str
    subject_key: str
    resource_id: str | None = None
    required_scope: str
    endpoint_or_artifact: str
    api_version: str
    evidence_level: str
    evidence_type: str
    status: str
    decision: str | None = None
    summary: str
    evidence_ref: str
    checked_by_user_id: str | None = None
    checked_at: datetime | None = None
    valid_until: datetime | None = None
    revision: int
    created_at: datetime
    updated_at: datetime


class TikTokDataValidationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    mode: str
    catalog_version: str
    dataset_digest: str
    record_count: int
    status: str
    workbench_ready_snapshot: bool
    real_data_ready_snapshot: bool
    checks_json: list[dict[str, Any]]
    issues_json: list[dict[str, Any]]
    started_by_user_id: str
    created_at: datetime


class TikTokDataValidationOption(BaseModel):
    id: str
    label: str


class TikTokDataValidationBootstrapResponse(BaseModel):
    catalog_version: str
    created_field_count: int
    created_evidence_count: int


class TikTokDataValidationWorkspace(BaseModel):
    tenant_id: str
    catalog_version: str
    scope: TikTokDataValidationScopeRead | None = None
    field_contracts: list[TikTokFieldContractRead] = Field(default_factory=list)
    capability_evidence: list[TikTokCapabilityEvidenceRead] = Field(default_factory=list)
    recent_runs: list[TikTokDataValidationRunRead] = Field(default_factory=list)
    store_options: list[TikTokDataValidationOption] = Field(default_factory=list)
    owner_options: list[TikTokDataValidationOption] = Field(default_factory=list)
    readiness: TikTokDataValidationReadiness
