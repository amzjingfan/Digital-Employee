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
