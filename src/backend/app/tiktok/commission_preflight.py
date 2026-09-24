"""Stateless internal checks; no commission or financial approval is recorded here."""

from __future__ import annotations

from datetime import datetime
from re import fullmatch

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel import Session

from app.db.models import User
from app.tiktok.creator_pool import _clock, _entry, _manager


class CommissionScopeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_refs: list[str] = Field(min_length=1, max_length=100)
    development_bps: int
    fulfillment_bps: int
    maintenance_bps: int
    calculation_evidence_ref: str

    @field_validator("order_refs")
    @classmethod
    def opaque_order_refs(cls, values: list[str]) -> list[str]:
        if any(fullmatch(r"order:[0-9a-f]{32}", value) is None for value in values):
            raise ValueError("opaque order references required")
        return values

    @field_validator("calculation_evidence_ref")
    @classmethod
    def opaque_evidence_ref(cls, value: str) -> str:
        if fullmatch(r"evidence:[0-9a-f]{32}", value) is None:
            raise ValueError("opaque calculation evidence required")
        return value


class CommissionPreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_version: str = Field(min_length=1, max_length=80)
    rule_expires_at: datetime
    scopes: list[CommissionScopeInput] = Field(min_length=1, max_length=20)

    @field_validator("rule_version")
    @classmethod
    def safe_version(cls, value: str) -> str:
        if fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) is None:
            raise ValueError("safe rule version required")
        return value

    @field_validator("rule_expires_at")
    @classmethod
    def aware_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timezone-aware rule expiry required")
        return value


class CommissionPreflightResult(BaseModel):
    check_codes: list[str]
    can_submit_financial_review: bool


def preflight_commission_draft(
    db: Session, user: User, entry_id: str, request: CommissionPreflightRequest, *,
    now: datetime | None = None,
) -> CommissionPreflightResult:
    _manager(user)
    entry = _entry(db, user, entry_id)
    checks: list[str] = []
    if (
        entry.state == "public" or entry.owner_user_id is None
        or entry.fulfillment_user_id is None or entry.maintenance_user_id is None
    ):
        checks.append("responsibilities_incomplete")
    if _clock(request.rule_expires_at) <= _clock(now):
        checks.append("rule_version_expired")

    seen_orders: set[str] = set()
    for scope in request.scopes:
        shares = (
            scope.development_bps, scope.fulfillment_bps, scope.maintenance_bps,
        )
        if (
            (any(share < 0 or share > 10000 for share in shares) or sum(shares) != 10000)
            and "commission_split_invalid" not in checks
        ):
            checks.append("commission_split_invalid")
        for order_ref in scope.order_refs:
            if order_ref in seen_orders and "order_scope_overlap" not in checks:
                checks.append("order_scope_overlap")
            seen_orders.add(order_ref)

    # User-supplied version metadata is never a trusted approved rule (PRD D6).
    checks.append("rule_unapproved")
    return CommissionPreflightResult(
        check_codes=checks, can_submit_financial_review=False,
    )
