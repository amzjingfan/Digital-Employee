from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ResourceType = Literal[
    "store",
    "carrier",
    "ad_account",
    "supplier",
    "creator_account",
    "partner_account",
    "social_account",
    "live_room",
]
ResourceStatus = Literal["active", "inactive", "archived"]
AccessLevel = Literal["viewer", "operator"]
HighRiskActionType = Literal[
    "issue_refund",
    "publish_listing",
    "change_routing_rule",
    "change_daily_budget",
    "change_ad_bid",
    "update_negative_keywords",
    "change_campaign_status",
    "publish_creative_asset",
    "issue_purchase_order",
]


class ResourceScopeInput(BaseModel):
    business_role: str = Field(min_length=1, max_length=80)
    access_level: AccessLevel = "operator"


class BusinessResourceCreate(BaseModel):
    tenant_id: str
    resource_type: ResourceType
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)
    scopes: list[ResourceScopeInput] = Field(default_factory=list)


class BusinessResourceUpdate(BaseModel):
    tenant_id: str
    name: str | None = Field(default=None, min_length=1, max_length=160)
    status: ResourceStatus | None = None
    metadata: dict[str, Any] | None = None
    scopes: list[ResourceScopeInput] | None = None


class BusinessResourceRead(BaseModel):
    id: str
    tenant_id: str
    resource_type: ResourceType
    code: str
    name: str
    status: ResourceStatus
    revision: int
    access_level: AccessLevel
    metadata: dict[str, Any]
    scopes: list[ResourceScopeInput]
    created_at: datetime
    updated_at: datetime


class HighRiskActionCreate(BaseModel):
    tenant_id: str
    resource_id: str
    action_type: HighRiskActionType
    summary: str = Field(min_length=8, max_length=500)
    payload: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    tenant_id: str
    reason: str = Field(min_length=2, max_length=500)


class HighRiskActionEventRead(BaseModel):
    event_type: str
    actor_user_id: str
    actor_business_role: str
    detail: dict[str, Any]
    occurred_at: datetime


class BusinessActionExecutionEventRead(BaseModel):
    phase: Literal["execution", "compensation", "reconciliation", "operator"]
    event_type: str
    attempt_no: int
    actor_type: str
    actor_id: str | None
    actor_business_role: str | None
    detail: dict[str, Any]
    occurred_at: datetime


class BusinessActionExecutionRead(BaseModel):
    id: str
    tenant_id: str
    request_id: str
    resource_id: str
    action_type: HighRiskActionType
    connector_type: str
    environment: Literal["sandbox", "live"]
    workflow_version: int
    approval_content_digest: str
    resource_snapshot_digest: str
    status: Literal[
        "queued",
        "running",
        "retry_wait",
        "succeeded",
        "failed",
        "compensation_requested",
        "compensating",
        "compensated",
        "compensation_failed",
        "manual_resolution_required",
    ]
    idempotency_key: str
    attempt_count: int
    compensation_attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None
    deadline_at: datetime | None
    external_operation_id: str | None
    receipt: dict[str, Any]
    last_error_code: str | None
    last_error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    compensated_at: datetime | None
    created_at: datetime
    updated_at: datetime
    events: list[BusinessActionExecutionEventRead] = Field(default_factory=list)


class ExecutionOperatorCommand(BaseModel):
    tenant_id: str
    reason: str = Field(min_length=4, max_length=500)


class ExecutionReconciliationReport(BaseModel):
    tenant_id: str
    observed_status: Literal["succeeded", "failed", "not_found", "unknown"]
    observed_idempotency_key: str = Field(min_length=8, max_length=160)
    external_operation_id: str | None = Field(default=None, max_length=240)
    receipt_digest: str | None = Field(default=None, max_length=160)
    note: str = Field(min_length=4, max_length=1000)


class HighRiskActionRead(BaseModel):
    id: str
    tenant_id: str
    resource_id: str
    resource_type: ResourceType
    resource_name: str
    action_type: HighRiskActionType
    summary: str
    payload: dict[str, Any]
    status: Literal["pending", "approved", "rejected", "cancelled", "invalidated"]
    content_digest: str
    resource_snapshot_digest: str
    requester_user_id: str
    requester_business_role: str
    decided_by_user_id: str | None
    decision_reason: str | None
    requested_at: datetime
    decided_at: datetime | None
    invalidated_at: datetime | None
    invalidation_reason: str | None
    events: list[HighRiskActionEventRead] = Field(default_factory=list)
    execution: BusinessActionExecutionRead | None = None
