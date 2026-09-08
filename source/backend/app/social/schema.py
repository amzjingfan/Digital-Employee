from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SocialPlatform = Literal["tiktok", "instagram", "youtube", "facebook", "pinterest", "x"]
DataRightsBasis = Literal["contract_authorized", "public_business", "user_provided"]
ContactBasis = Literal["none", "contract_authorized", "public_business"]
_EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_SECRET_QUERY_KEYS = {"access_token", "api_key", "credential", "password", "secret", "token"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SocialCreatorEvidenceInput(StrictModel):
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    language_code: str | None = Field(default=None, min_length=2, max_length=16)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    followers_count: int = Field(default=0, ge=0, le=2_000_000_000)
    engagement_rate_bps: int = Field(default=0, ge=0, le=10_000)
    audience_country_code: str | None = Field(default=None, min_length=2, max_length=2)
    estimated_cost_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    quality_score: int = Field(default=0, ge=0, le=100)
    source_ref: str = Field(min_length=3, max_length=500)
    data_rights_basis: DataRightsBasis
    contact_basis: ContactBasis = "none"
    observed_at: datetime
    expires_at: datetime

    @field_validator("country_code", "audience_country_code", mode="before")
    @classmethod
    def normalize_country(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("language_code", "category", "source_ref", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("source_ref")
    @classmethod
    def reject_sensitive_source_ref(cls, value: str) -> str:
        if _EMAIL_RE.search(value):
            raise ValueError("source_ref cannot contain a contact address")
        parsed = urlsplit(value)
        query_keys = {part.partition("=")[0].casefold() for part in parsed.query.split("&") if part}
        if query_keys.intersection(_SECRET_QUERY_KEYS):
            raise ValueError("source_ref cannot contain credentials")
        return value

    @model_validator(mode="after")
    def validate_evidence_window(self) -> SocialCreatorEvidenceInput:
        if self.observed_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("observed_at and expires_at must include a timezone")
        if self.expires_at <= self.observed_at:
            raise ValueError("expires_at must be later than observed_at")
        if (self.estimated_cost_minor is None) != (self.currency is None):
            raise ValueError("estimated_cost_minor and currency must be supplied together")
        if self.contact_basis != "none" and self.data_rights_basis == "user_provided":
            raise ValueError("contact use requires contract or public-business evidence")
        return self


class SocialIdentityCreate(StrictModel):
    platform: SocialPlatform
    provider_identity_id: str = Field(min_length=1, max_length=200)
    public_handle: str = Field(min_length=1, max_length=200)
    profile_url: str | None = Field(default=None, max_length=500)
    verified: bool = False

    @field_validator("provider_identity_id", "public_handle", "profile_url", mode="before")
    @classmethod
    def normalize_identity_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("public_handle")
    @classmethod
    def reject_contact_handle(cls, value: str) -> str:
        if _EMAIL_RE.fullmatch(value):
            raise ValueError("public_handle cannot be a contact address")
        return value

    @field_validator("profile_url")
    @classmethod
    def validate_profile_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("profile_url must be a public HTTPS URL without credentials")
        return value


class SocialCreatorCreate(StrictModel):
    canonical_name: str = Field(min_length=1, max_length=200)
    identity: SocialIdentityCreate
    evidence: SocialCreatorEvidenceInput

    @field_validator("canonical_name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class SocialAudienceFilters(StrictModel):
    platform: SocialPlatform | None = None
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    language_code: str | None = Field(default=None, min_length=2, max_length=16)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    min_followers: int | None = Field(default=None, ge=0)
    max_followers: int | None = Field(default=None, ge=0)
    min_engagement_rate_bps: int | None = Field(default=None, ge=0, le=10_000)
    audience_country_code: str | None = Field(default=None, min_length=2, max_length=2)
    max_estimated_cost_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    min_quality_score: int | None = Field(default=None, ge=0, le=100)
    require_contactable: bool = False
    include_stale: bool = False

    @field_validator("country_code", "audience_country_code", mode="before")
    @classmethod
    def normalize_filter_country(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_filter_currency(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("language_code", "category", mode="before")
    @classmethod
    def normalize_filter_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_filter_ranges(self) -> SocialAudienceFilters:
        if (
            self.min_followers is not None
            and self.max_followers is not None
            and self.min_followers > self.max_followers
        ):
            raise ValueError("min_followers cannot exceed max_followers")
        if (self.max_estimated_cost_minor is None) != (self.currency is None):
            raise ValueError("cost filtering requires both max_estimated_cost_minor and currency")
        return self


class SocialAudienceCreate(StrictModel):
    brand_id: str = Field(min_length=1, max_length=200)
    filters: SocialAudienceFilters = Field(default_factory=SocialAudienceFilters)


class SocialCreatorEvidenceRead(StrictModel):
    id: str
    creator_id: str
    identity_id: str
    country_code: str | None
    language_code: str | None
    category: str | None
    followers_count: int
    engagement_rate_bps: int
    audience_country_code: str | None
    estimated_cost_minor: int | None
    currency: str | None
    quality_score: int
    source_ref: str
    data_rights_basis: DataRightsBasis
    contact_basis: ContactBasis
    observed_at: datetime
    expires_at: datetime
    stale: bool
    created_at: datetime


class SocialIdentityRead(StrictModel):
    id: str
    platform: SocialPlatform
    provider_identity_id: str
    public_handle: str
    profile_url: str | None
    verified: bool
    status: Literal["active", "needs_review", "archived"]
    latest_evidence: SocialCreatorEvidenceRead | None


class SocialCreatorRead(StrictModel):
    id: str
    canonical_name: str
    status: Literal["active", "needs_review", "archived"]
    identities: list[SocialIdentityRead]
    created_at: datetime
    updated_at: datetime


class SocialAudienceRead(StrictModel):
    id: str
    brand_id: str
    status: Literal["frozen"]
    filters: SocialAudienceFilters
    creator_ids: list[str]
    identity_ids: list[str]
    evidence_ids: list[str]
    creator_count: int
    audience_hash: str
    created_by_user_id: str
    created_at: datetime
