from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AdActionType = Literal[
    "none",
    "change_daily_budget",
    "change_ad_bid",
    "update_negative_keywords",
    "change_campaign_status",
]
ControlledAdActionType = Literal[
    "change_daily_budget",
    "change_ad_bid",
    "update_negative_keywords",
    "change_campaign_status",
]


class AdvertisingRecommendationCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    recommendation_key: str = Field(min_length=8, max_length=160)
    ad_account_resource_id: str = Field(min_length=1, max_length=128)
    store_resource_id: str | None = Field(default=None, max_length=128)
    campaign_id: str = Field(min_length=1, max_length=160)
    product_key: str = Field(min_length=1, max_length=160)
    spend: float = Field(ge=0, le=1_000_000_000)
    attributed_sales: float = Field(ge=0, le=1_000_000_000)
    impressions: int = Field(ge=0, le=10_000_000_000)
    clicks: int = Field(ge=0, le=10_000_000_000)
    orders: int = Field(ge=0, le=1_000_000_000)
    price: float = Field(gt=0, le=1_000_000)
    profit_per_order: float = Field(ge=-1_000_000, le=1_000_000)
    available_units: int = Field(ge=0, le=100_000_000)
    inbound_units: int = Field(default=0, ge=0, le=100_000_000)
    forecast_daily_sales: float = Field(gt=0, le=1_000_000)
    reserve_stock_units: int = Field(default=0, ge=0, le=100_000_000)
    minimum_days_of_cover: float = Field(default=21, ge=0, le=365)
    promotion_active: bool = False
    promotion_margin: float | None = Field(default=None, ge=-1, le=1)
    minimum_promotion_margin: float = Field(default=0.05, ge=-1, le=1)
    minimum_ctr: float = Field(default=0.003, ge=0, le=1)
    minimum_conversion_rate: float = Field(default=0.06, ge=0, le=1)
    proposed_action_type: AdActionType = "none"
    proposed_action_payload: dict[str, Any] = Field(default_factory=dict)
    recommendation_note: str = Field(min_length=4, max_length=2000)


class AdvertisingActionRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=0)
    summary: str = Field(min_length=8, max_length=500)


class AdvertisingRecommendationRead(BaseModel):
    id: str
    tenant_id: str
    recommendation_key: str
    ad_account_resource_id: str
    store_resource_id: str | None
    campaign_id: str
    product_key: str
    metrics: dict[str, Any]
    constraints: dict[str, Any]
    findings: list[dict[str, Any]]
    recommendation: dict[str, Any]
    proposed_action_type: str | None
    proposed_action_payload: dict[str, Any]
    risk_level: Literal["low", "medium", "high", "critical"]
    status: Literal[
        "ready",
        "blocked",
        "action_pending",
        "action_approved",
        "action_rejected",
    ]
    input_digest: str
    task_id: str
    linked_task_ids: list[str]
    approval_request_id: str | None
    approval_status: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class ExecutionAutomationPolicyUpsert(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=1, max_length=128)
    action_type: ControlledAdActionType
    status: Literal["active", "paused"] = "paused"
    rollout_percent: int = Field(default=0, ge=0, le=100)
    max_single_value: float = Field(default=0, ge=0, le=1_000_000_000)
    max_daily_value: float = Field(default=0, ge=0, le=1_000_000_000)
    max_risk_level: Literal["low", "medium"] = "low"
    approval_required: bool = True
    kill_switch_engaged: bool = True


class ExecutionAutomationPolicyRead(BaseModel):
    id: str
    tenant_id: str
    resource_id: str
    action_type: str
    status: Literal["active", "paused"]
    rollout_percent: int
    max_single_value: float
    max_daily_value: float
    max_risk_level: Literal["low", "medium"]
    approval_required: bool
    kill_switch_engaged: bool
    revision: int
    created_by_user_id: str
    updated_by_user_id: str
    created_at: datetime
    updated_at: datetime


class AutomationUsageRead(BaseModel):
    id: str
    policy_id: str
    policy_revision: int
    request_id: str
    action_type: str
    cohort_bucket: int
    quantitative_value: float
    usage_date: str
    decision: Literal["allowed", "blocked"]
    reason: str
    created_at: datetime


class AdvertisingEffectFollowUpRead(BaseModel):
    id: str
    execution_id: str
    request_id: str
    recommendation_id: str | None
    horizon_days: Literal[7, 14, 30]
    baseline: dict[str, Any]
    task_id: str
    status: Literal["pending", "completed", "cancelled"]
    due_at: datetime
    created_at: datetime


class AdvertisingOverview(BaseModel):
    recommendations_ready: int
    recommendations_blocked: int
    actions_waiting_approval: int
    effectiveness_reviews_pending: int
    automation_policies_active: int
    kill_switches_engaged: int


class PdcaSearchTermActionRead(BaseModel):
    id: str
    fact_id: str
    campaign_id: str
    ad_group_id: str
    search_term: str
    match_type: str
    action_type: Literal[
        "manual_review",
        "lower_bid",
        "convert_exact",
        "protect_scale",
        "observe",
    ]
    priority: Literal["critical", "high", "medium", "low"]
    must_do_score: int
    rationale: str
    evidence: dict[str, Any]
    thresholds: dict[str, Any]
    current_values: dict[str, Any]
    expected_effect: str
    risk_note: str
    verification_window_days: int
    execution_hint: str
    status: Literal["suggested"]
    external_execution_allowed: Literal[False]


class PdcaSearchTermRunRead(BaseModel):
    id: str
    tenant_id: str
    ad_account_resource_id: str
    store_resource_id: str | None
    source_type: Literal["amazon_search_term_csv"]
    source_label: Literal["local source file"]
    source_sha256: str
    input_digest: str
    mapping_version: str
    rule_version: str
    metric_definition_version: str
    mode: Literal["rules_only"]
    state: Literal["succeeded"]
    target_acos: str
    currency: str
    source_row_count: int
    fact_count: int
    action_count: int
    quality_score: int
    mapping: dict[str, str]
    summary: dict[str, Any]
    warnings: list[str]
    external_execution_allowed: Literal[False]
    top_actions: list[PdcaSearchTermActionRead]
    created_at: datetime
