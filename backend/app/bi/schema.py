from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator


class BiDailyCommerceFactInput(BaseModel):
    external_id: str = Field(min_length=1, max_length=160)
    source_version: str = Field(min_length=1, max_length=160)
    business_date: date
    brand_id: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=128)
    platform: str = Field(min_length=1, max_length=80)
    entity_type: Literal["store", "asin", "sku"] = "store"
    entity_id: str = Field(min_length=1, max_length=160)
    currency: str = Field(min_length=3, max_length=3)
    gross_sales: Decimal = Field(ge=0, max_digits=24, decimal_places=6)
    refund_amount: Decimal = Field(default=Decimal(0), ge=0, max_digits=24, decimal_places=6)
    ad_spend: Decimal = Field(default=Decimal(0), ge=0, max_digits=24, decimal_places=6)
    attributed_ad_sales: Decimal = Field(default=Decimal(0), ge=0, max_digits=24, decimal_places=6)
    impressions: int = Field(default=0, ge=0, le=10_000_000_000)
    clicks: int = Field(default=0, ge=0, le=10_000_000_000)
    orders: int = Field(default=0, ge=0, le=1_000_000_000)
    available_inventory: int = Field(default=0, ge=0, le=10_000_000_000)
    rolling_units_sold: int = Field(default=0, ge=0, le=10_000_000_000)
    rolling_window_days: int = Field(default=30, ge=1, le=365)
    source_observed_at: datetime

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        return normalized

    @field_validator("source_observed_at")
    @classmethod
    def require_observed_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("source_observed_at must include a timezone offset")
        return value


class BiIngestionBatchCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    source_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{1,127}$")
    window_start: datetime
    window_end: datetime
    business_timezone: str = Field(default="UTC", min_length=1, max_length=64)
    snapshot_mode: Literal["full_window", "incremental"] = "full_window"
    facts: list[BiDailyCommerceFactInput] = Field(default_factory=list, max_length=5000)
    expected_row_count: int | None = Field(default=None, ge=0, le=5_000_000)
    expected_gross_sales: Decimal | None = Field(
        default=None, ge=0, max_digits=24, decimal_places=6
    )
    expected_ad_spend: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=6)
    reconciliation_tolerance: Decimal = Field(
        default=Decimal("0.01"), ge=0, max_digits=24, decimal_places=6
    )

    @model_validator(mode="after")
    def validate_window(self) -> BiIngestionBatchCreate:
        for value, label in (
            (self.window_start, "window_start"),
            (self.window_end, "window_end"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{label} must include a timezone offset")
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        try:
            ZoneInfo(self.business_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("business_timezone is unknown") from exc
        return self


class BiQualityCheckRead(BaseModel):
    id: str
    check_code: str
    status: Literal["passed", "failed", "skipped"]
    severity: Literal["info", "warning", "error"]
    observed: dict[str, Any]
    expected: dict[str, Any]
    detail: str
    created_at: datetime


class BiIngestionBatchRead(BaseModel):
    id: str
    tenant_id: str
    source_key: str
    window_start: datetime
    window_end: datetime
    business_timezone: str
    snapshot_mode: Literal["full_window", "incremental"]
    input_digest: str
    status: Literal["pending", "succeeded", "rejected", "superseded"]
    quality_status: Literal["pending", "passed", "failed"]
    row_count: int
    accepted_count: int
    rejected_count: int
    expected_row_count: int | None
    expected_gross_sales: Decimal | None
    expected_ad_spend: Decimal | None
    actual_gross_sales: Decimal
    actual_ad_spend: Decimal
    reconciliation_tolerance: Decimal
    metric_definition_version: str
    latest_source_observed_at: datetime | None
    created_by_user_id: str
    created_at: datetime
    completed_at: datetime | None
    fact_count: int
    metric_count: int
    quality_checks: list[BiQualityCheckRead] = Field(default_factory=list)


class BiDailyMetricRead(BaseModel):
    id: str
    batch_id: str
    metric_definition_id: str
    metric_code: str
    metric_definition_version: str
    business_date: date
    source_key: str
    brand_id: str
    store_id: str
    platform: str
    entity_type: str
    entity_id: str
    currency: str
    value: Decimal | None
    null_reason: str | None
    freshness_status: Literal["fresh", "stale", "unknown"]
    latest_source_observed_at: datetime | None
    evidence: dict[str, Any]
    created_at: datetime


class BiDailyCommerceFactRead(BaseModel):
    id: str
    batch_id: str
    source_key: str
    external_id: str
    source_version: str
    content_digest: str
    replaces_fact_id: str | None
    is_current: bool
    business_date: date
    brand_id: str
    store_id: str
    platform: str
    entity_type: Literal["store", "asin", "sku"]
    entity_id: str
    currency: str
    gross_sales: Decimal
    refund_amount: Decimal
    ad_spend: Decimal
    attributed_ad_sales: Decimal
    impressions: int
    clicks: int
    orders: int
    available_inventory: int
    rolling_units_sold: int
    rolling_window_days: int
    source_observed_at: datetime
    created_at: datetime
