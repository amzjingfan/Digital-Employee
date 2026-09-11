from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AfterSalesStatus = Literal[
    "intake",
    "queried",
    "classified",
    "drafted",
    "waiting_approval",
    "needs_human",
    "closed",
    "rejected",
]
AfterSalesCategory = Literal[
    "pre_sale",
    "not_received",
    "damaged",
    "wrong_item",
    "return_refund",
    "usage",
    "complaint",
    "other",
]
RiskLevel = Literal["low", "medium", "high", "critical"]


class EvidenceCitation(BaseModel):
    source_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=240)
    version: str = Field(min_length=1, max_length=80)
    scope: str = Field(min_length=1, max_length=240)
    excerpt: str = Field(default="", max_length=1000)
    retrieved_at: datetime


class AfterSalesCaseCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    case_key: str = Field(min_length=8, max_length=160)
    store_resource_id: str = Field(min_length=1, max_length=128)
    platform: str = Field(min_length=2, max_length=80)
    marketplace_country: str = Field(min_length=2, max_length=80)
    language: str = Field(default="en", min_length=2, max_length=24)
    order_reference: str = Field(min_length=4, max_length=160)
    summary: str = Field(min_length=4, max_length=1000)


class AfterSalesQueryResult(BaseModel):
    tenant_id: str
    expected_version: int = Field(ge=0)
    order_snapshot: dict[str, Any]
    citations: list[EvidenceCitation] = Field(min_length=1, max_length=30)
    dependency_status: dict[str, Literal["healthy", "stale", "unavailable"]] = Field(
        default_factory=dict
    )
    observed_at: datetime


class AfterSalesClassification(BaseModel):
    tenant_id: str
    expected_version: int = Field(ge=0)
    category: AfterSalesCategory
    confidence: float = Field(ge=0, le=1)
    risk_level: RiskLevel = "medium"
    exception_flags: list[
        Literal[
            "order_absent",
            "identity_mismatch",
            "stale_logistics",
            "policy_conflict",
            "duplicate_claim",
            "deadline_near",
            "safety_risk",
            "privacy_risk",
            "reputation_risk",
            "dispute_risk",
        ]
    ] = Field(default_factory=list, max_length=20)
    note: str = Field(default="", max_length=1000)


class AfterSalesDraft(BaseModel):
    tenant_id: str
    expected_version: int = Field(ge=0)
    recommendation: dict[str, Any] = Field(default_factory=dict)
    reply_draft: str = Field(min_length=4, max_length=8000)
    requires_approval: bool = False
    refund_amount: float | None = Field(default=None, ge=0, le=1_000_000)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    approval_summary: str = Field(default="", max_length=500)


class HumanExceptionResolution(BaseModel):
    tenant_id: str
    expected_version: int = Field(ge=0)
    resolution_note: str = Field(min_length=4, max_length=2000)
    resume_status: Literal["classified", "drafted", "rejected"] = "classified"


class CaseFollowUp(BaseModel):
    owner_business_role: Literal[
        "listing_compliance_specialist",
        "logistics_exception_specialist",
        "procurement_specialist",
        "designer",
    ]
    title: str = Field(min_length=4, max_length=200)
    note: str = Field(default="", max_length=2000)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"


class AfterSalesClose(BaseModel):
    tenant_id: str
    expected_version: int = Field(ge=0)
    root_cause: str = Field(min_length=4, max_length=1000)
    outcome: str = Field(min_length=4, max_length=2000)
    follow_ups: list[CaseFollowUp] = Field(default_factory=list, max_length=12)


class BusinessTraceEventRead(BaseModel):
    id: str
    event_type: str
    actor_type: str
    actor_id: str | None
    actor_business_role: str | None
    from_status: str | None
    to_status: str | None
    detail: dict[str, Any]
    occurred_at: datetime


class AfterSalesCaseRead(BaseModel):
    id: str
    tenant_id: str
    case_key: str
    store_resource_id: str
    store_code: str
    platform: str
    marketplace_country: str
    language: str
    order_reference_masked: str
    status: AfterSalesStatus
    category: AfterSalesCategory | None
    risk_level: RiskLevel
    needs_human: bool
    human_reason: str | None
    task_id: str
    approval_request_id: str | None
    approval_status: str | None
    order_snapshot: dict[str, Any]
    citations: list[dict[str, Any]]
    recommendation: dict[str, Any]
    draft_reply: str | None
    root_cause: str | None
    follow_up_task_ids: list[str]
    version: int
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    events: list[BusinessTraceEventRead] = Field(default_factory=list)


LogisticsAnomalyType = Literal[
    "overdue",
    "no_first_scan",
    "stalled",
    "customs_hold",
    "delivery_dispute",
    "appointment_issue",
]


class LogisticsAnomalyInput(BaseModel):
    carrier_resource_id: str
    store_resource_id: str | None = None
    platform: str = Field(min_length=2, max_length=80)
    order_reference: str = Field(min_length=4, max_length=160)
    status_event_id: str = Field(min_length=1, max_length=200)
    shipment_status: str = Field(min_length=1, max_length=120)
    anomaly_type: LogisticsAnomalyType
    customer_impact: Literal["low", "medium", "high", "critical"] = "medium"
    deadline_at: datetime | None = None
    observed_at: datetime
    channel: str = Field(default="", max_length=120)
    warehouse: str = Field(default="", max_length=120)
    country: str = Field(default="", max_length=80)
    sku: str = Field(default="", max_length=120)
    batch: str = Field(default="", max_length=120)
    evidence: dict[str, Any] = Field(default_factory=dict)


class LogisticsAnomalyBatchCreate(BaseModel):
    tenant_id: str
    batch_key: str = Field(min_length=8, max_length=160)
    items: list[LogisticsAnomalyInput] = Field(min_length=1, max_length=200)


class LogisticsEscalation(BaseModel):
    tenant_id: str
    expected_version: int = Field(ge=0)
    targets: list[
        Literal[
            "after_sales_specialist",
            "procurement_specialist",
            "operations_supervisor",
        ]
    ] = Field(min_length=1, max_length=3)
    reason: str = Field(min_length=4, max_length=2000)


class LogisticsResolution(BaseModel):
    tenant_id: str
    expected_version: int = Field(ge=0)
    resolution: str = Field(min_length=4, max_length=2000)


class LogisticsAnomalyRead(BaseModel):
    id: str
    tenant_id: str
    fingerprint: str
    carrier_resource_id: str
    carrier_code: str
    store_resource_id: str | None
    platform: str
    order_reference_masked: str
    status_event_id: str
    shipment_status: str
    anomaly_type: LogisticsAnomalyType
    status: Literal["detected", "clustered", "escalated", "resolved"]
    severity: RiskLevel
    customer_impact: RiskLevel
    cluster_key: str
    dimensions: dict[str, Any]
    evidence: dict[str, Any]
    escalation_targets: list[str]
    follow_up_task_ids: list[str]
    task_id: str
    occurrence_count: int
    deadline_at: datetime | None
    first_observed_at: datetime
    last_observed_at: datetime
    resolution: str | None
    version: int
    updated_at: datetime
    events: list[BusinessTraceEventRead] = Field(default_factory=list)


class LogisticsAnomalyBatchRead(BaseModel):
    items: list[LogisticsAnomalyRead]
    created_count: int
    deduplicated_count: int


class IntegrationHealthReport(BaseModel):
    tenant_id: str
    dependency_key: str = Field(min_length=2, max_length=120)
    display_name: str = Field(min_length=2, max_length=160)
    domain: Literal[
        "orders", "payments", "shipping", "logistics", "knowledge", "approvals", "tasks"
    ]
    status: Literal["healthy", "degraded", "unavailable"]
    reason_code: str | None = Field(default=None, max_length=120)
    message: str = Field(default="", max_length=1000)
    recovery_hint: str = Field(default="", max_length=1000)
    source: Literal["operator", "health_check", "fault_injection"] = "operator"
    last_success_at: datetime | None = None
    observed_at: datetime
    stale_after_seconds: int = Field(default=900, ge=30, le=86_400)


class IntegrationHealthRead(BaseModel):
    id: str
    tenant_id: str
    dependency_key: str
    display_name: str
    domain: str
    status: Literal["healthy", "degraded", "unavailable"]
    effective_status: Literal["healthy", "degraded", "unavailable", "stale"]
    reason_code: str | None
    message: str
    recovery_hint: str
    source: str
    last_success_at: datetime | None
    observed_at: datetime
    stale_after_seconds: int
    version: int
    updated_at: datetime
    events: list[BusinessTraceEventRead] = Field(default_factory=list)


class CrossborderOverview(BaseModel):
    after_sales_open: int
    after_sales_needs_human: int
    logistics_open: int
    logistics_high_risk: int
    degraded_dependencies: int
    generated_at: datetime
