from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ReportType = Literal["daily", "weekly"]
ReportStatus = Literal["draft", "confirmed", "rejected"]


class OperationsReportGenerate(BaseModel):
    tenant_id: str
    report_type: ReportType
    report_date: date | None = None
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)
    scope: dict[str, str] = Field(default_factory=dict)
    refresh: bool = False


class OperationsReportCommentCreate(BaseModel):
    tenant_id: str
    body: str = Field(min_length=2, max_length=1000)


class OperationsReportReview(BaseModel):
    tenant_id: str
    note: str = Field(min_length=2, max_length=1000)


class OperationsReportFollowUpCreate(BaseModel):
    tenant_id: str
    title: str = Field(min_length=4, max_length=200)
    owner_business_role: str = Field(min_length=1, max_length=80)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    due_at: datetime | None = None
    source_ids: list[str] = Field(default_factory=list, max_length=50)
    note: str = Field(default="", max_length=1000)


class OperationsReportSourceRead(BaseModel):
    id: str
    source_type: str
    source_id: str
    business_key: str
    severity: str
    label: str
    summary: str
    source_route: str
    occurred_at: datetime


class OperationsReportCommentRead(BaseModel):
    id: str
    action_type: str
    author_user_id: str
    author_business_role: str
    body: str
    detail: dict[str, Any]
    created_at: datetime


class OperationsReportRead(BaseModel):
    id: str
    tenant_id: str
    report_type: ReportType
    title: str
    status: ReportStatus
    timezone: str
    period_start: datetime
    period_end: datetime
    scope: dict[str, Any]
    metrics: dict[str, Any]
    sections: dict[str, Any]
    data_status: str
    source_count: int
    generated_by_user_id: str
    generated_at: datetime
    reviewed_by_user_id: str | None
    review_note: str | None
    reviewed_at: datetime | None
    updated_at: datetime
    sources: list[OperationsReportSourceRead] = Field(default_factory=list)
    comments: list[OperationsReportCommentRead] = Field(default_factory=list)

