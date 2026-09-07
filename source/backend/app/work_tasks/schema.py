from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

TaskPriority = Literal["low", "normal", "high", "urgent"]
TaskRisk = Literal["low", "medium", "high", "critical"]
TaskStatus = Literal[
    "pending",
    "in_progress",
    "waiting_input",
    "review",
    "completed",
    "failed",
    "cancelled",
    "archived",
]


class WorkTaskCreate(BaseModel):
    tenant_id: str
    idempotency_key: str = Field(min_length=8, max_length=160)
    title: str = Field(min_length=4, max_length=200)
    description: str = Field(default="", max_length=2000)
    owner_business_role: str = Field(min_length=1, max_length=80)
    priority: TaskPriority = "normal"
    risk_level: TaskRisk = "medium"
    due_at: datetime | None = None
    scope: dict[str, str] = Field(default_factory=dict)


class WorkTaskBatchItem(BaseModel):
    item_key: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=4, max_length=200)
    description: str = Field(default="", max_length=2000)
    owner_business_role: str = Field(min_length=1, max_length=80)
    priority: TaskPriority = "normal"
    risk_level: Literal["low", "medium"] = "low"
    due_at: datetime | None = None
    scope: dict[str, str] = Field(default_factory=dict)


class WorkTaskBatchCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    batch_idempotency_key: str = Field(min_length=8, max_length=120)
    read_only_patrol: Literal[True] = True
    items: list[WorkTaskBatchItem] = Field(min_length=1, max_length=100)


class WorkTaskTransition(BaseModel):
    tenant_id: str
    action: Literal[
        "start",
        "request_input",
        "resume",
        "request_review",
        "complete",
        "rework",
        "fail",
        "retry",
        "cancel",
        "archive",
        "takeover",
        "return_to_agent",
    ]
    expected_version: int = Field(ge=0)
    note: str = Field(default="", max_length=1000)


class ReportEvidenceReference(BaseModel):
    source_type: str
    source_id: str
    severity: str = "info"
    label: str
    summary: str
    source_route: str
    occurred_at: datetime


class ReportFollowUpCommand(BaseModel):
    tenant_id: str
    report_id: str
    title: str
    note: str = ""
    owner_business_role: str
    priority: TaskPriority
    due_at: datetime | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    evidence: list[ReportEvidenceReference] = Field(default_factory=list)
    created_by_user_id: str
    created_by_business_role: str


class WorkTaskEvidenceRead(BaseModel):
    id: str
    source_type: str
    source_id: str
    severity: str
    label: str
    summary: str
    source_route: str
    occurred_at: datetime


class WorkTaskEventRead(BaseModel):
    id: str
    event_type: str
    actor_type: str
    actor_id: str | None
    actor_business_role: str | None
    from_status: str | None
    to_status: str | None
    detail: dict[str, Any]
    created_at: datetime


class WorkTaskRunRead(BaseModel):
    id: str
    attempt_no: int
    generation: int
    agent_id: str
    session_id: str
    service_identity_id: str | None
    execution_snapshot_id: str | None
    snapshot_digest: str | None
    execution_snapshot: dict[str, Any] | None = None
    status: Literal["running", "succeeded", "retrying", "failed", "cancelled", "stale"]
    execution_mode: Literal["sandbox", "live"]
    result_summary: str | None
    error_code: str | None
    error_message: str | None
    trace: dict[str, Any]
    started_at: datetime
    finished_at: datetime | None


class WorkTaskRead(BaseModel):
    id: str
    tenant_id: str
    source_type: str
    source_id: str | None
    source_report_id: str | None
    title: str
    description: str | None
    owner_business_role: str
    owner_role_label: str
    assignee_agent_id: str | None
    assignee_agent_name: str | None
    priority: TaskPriority
    risk_level: TaskRisk
    status: TaskStatus
    control_mode: Literal["agent", "human"]
    cancel_requested: bool
    execution_generation: int
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None
    lease_expires_at: datetime | None
    latest_session_id: str | None
    taken_over_by_user_id: str | None
    taken_over_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None
    result_summary: str | None
    scope: dict[str, Any]
    due_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    evidence: list[WorkTaskEvidenceRead] = Field(default_factory=list)
    events: list[WorkTaskEventRead] = Field(default_factory=list)
    runs: list[WorkTaskRunRead] = Field(default_factory=list)


class WorkTaskQueueSummary(BaseModel):
    business_role: str
    label: str
    pending: int
    in_progress: int
    waiting_input: int
    review: int
    overdue: int
    total_open: int


class WorkTaskListResponse(BaseModel):
    items: list[WorkTaskRead]
    queues: list[WorkTaskQueueSummary]


class WorkTaskBatchResponse(BaseModel):
    items: list[WorkTaskRead]
    created_count: int
    existing_count: int
