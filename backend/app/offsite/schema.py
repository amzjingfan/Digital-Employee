from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ChannelAssetType = Literal[
    "facebook_group",
    "deal_site",
    "creator",
    "media_outlet",
    "author",
    "affiliate",
    "community",
]
ChannelLifecycleStatus = Literal[
    "discovered",
    "candidate",
    "verifying",
    "verified",
    "piloting",
    "active",
    "needs_review",
    "paused",
    "rejected",
    "archived",
]
ChannelTier = Literal["unassigned", "tier_1", "tier_2", "tier_3"]
EvidenceType = Literal[
    "identity",
    "audience_fit",
    "activity",
    "administrator",
    "terms",
    "fees",
    "contact_basis",
    "authenticity",
    "compliance",
    "current_role",
    "historical_result",
    "other",
]
EvidenceClass = Literal["observed_fact", "source_claim", "human_judgment"]
EvidenceSourceType = Literal[
    "public_web",
    "authorized_api",
    "authorized_import",
    "business_record",
    "human_observation",
]


class OffsiteChannelAssetCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    brand_key: str = Field(
        min_length=2,
        max_length=80,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    store_resource_id: str = Field(min_length=1, max_length=128)
    asset_type: ChannelAssetType
    canonical_name: str = Field(min_length=2, max_length=240)
    stable_external_ref: str = Field(min_length=2, max_length=1000)
    region: str = Field(min_length=2, max_length=24)
    language: str = Field(min_length=2, max_length=24)
    categories: list[str] = Field(default_factory=list, max_length=20)


class OffsiteChannelEvidenceCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    evidence_type: EvidenceType
    evidence_class: EvidenceClass
    value: dict[str, Any] = Field(default_factory=dict)
    source_type: EvidenceSourceType
    source_record_id: str = Field(min_length=1, max_length=500)
    ingestion_batch_id: str | None = Field(default=None, min_length=1, max_length=160)
    captured_at: datetime
    expires_at: datetime
    confidence: float = Field(ge=0, le=1)
    rule_version: str = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_evidence_window(self) -> OffsiteChannelEvidenceCreate:
        if self.captured_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("captured_at and expires_at must include a timezone")
        if self.expires_at <= self.captured_at:
            raise ValueError("expires_at must be later than captured_at")
        return self


class OffsiteChannelReview(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=0)
    lifecycle_status: ChannelLifecycleStatus
    tier: ChannelTier = "unassigned"
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    reason: str = Field(min_length=8, max_length=1000)


class OffsiteChannelEventRead(BaseModel):
    id: str
    tenant_id: str
    brand_key: str
    asset_id: str
    event_type: str
    actor_type: str
    actor_id: str | None
    actor_business_role: str | None
    from_status: str | None
    to_status: str | None
    detail: dict[str, Any]
    occurred_at: datetime


class OffsiteChannelEvidenceRead(BaseModel):
    id: str
    tenant_id: str
    brand_key: str
    asset_id: str
    evidence_type: EvidenceType
    evidence_class: EvidenceClass
    value: dict[str, Any]
    source_type: EvidenceSourceType
    source_record_id: str
    ingestion_batch_id: str | None
    captured_at: datetime
    expires_at: datetime
    confidence: float
    collector_type: str
    collector_id: str
    rule_version: str
    raw_hash: str
    freshness_status: Literal["fresh", "expired"]
    created_at: datetime


class OffsiteExecutionGuardRead(BaseModel):
    status: Literal["blocked", "eligible_for_proposal"]
    reasons: list[str] = Field(default_factory=list)
    evaluated_at: datetime


class OffsiteChannelAssetRead(BaseModel):
    id: str
    tenant_id: str
    brand_key: str
    store_resource_id: str
    store_code: str
    asset_type: ChannelAssetType
    canonical_name: str
    stable_external_ref: str
    region: str
    language: str
    categories: list[str]
    tier: ChannelTier
    lifecycle_status: ChannelLifecycleStatus
    effective_lifecycle_status: ChannelLifecycleStatus
    owner_user_id: str
    required_evidence_types: list[EvidenceType]
    missing_required_evidence: list[EvidenceType]
    expired_required_evidence: list[EvidenceType]
    freshness_status: Literal["fresh", "stale", "missing"]
    execution_guard: OffsiteExecutionGuardRead
    last_verified_at: datetime | None
    reviewed_by_user_id: str | None
    review_reason: str | None
    reviewed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    evidence: list[OffsiteChannelEvidenceRead] = Field(default_factory=list)
    events: list[OffsiteChannelEventRead] = Field(default_factory=list)
