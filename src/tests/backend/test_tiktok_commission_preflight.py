from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from test_tiktok_creator_pool import NOW, _intake, _seed, _session

from app.tiktok.commission_preflight import (
    CommissionPreflightRequest,
    CommissionScopeInput,
    preflight_commission_draft,
)
from app.tiktok.creator_pool import claim_creator, set_creator_responsibilities

ORDER_A = "order:" + "a" * 32
ORDER_B = "order:" + "b" * 32
EVIDENCE = "evidence:" + "c" * 32


def _request(*, expires_at: datetime, duplicate: bool = False,
             split: int = 10000) -> CommissionPreflightRequest:
    scopes = [CommissionScopeInput(
        order_refs=[ORDER_A], development_bps=split - 4000,
        fulfillment_bps=2000, maintenance_bps=2000,
        calculation_evidence_ref=EVIDENCE,
    )]
    if duplicate:
        scopes.append(CommissionScopeInput(
            order_refs=[ORDER_A, ORDER_B], development_bps=6000,
            fulfillment_bps=2000, maintenance_bps=2000,
            calculation_evidence_ref=EVIDENCE,
        ))
    return CommissionPreflightRequest(
        rule_version="proposed-v1", rule_expires_at=expires_at, scopes=scopes,
    )


def test_preflight_reports_split_scope_expiry_and_unapproved_rule() -> None:
    with _session() as db:
        _, supervisor, bd, other_bd, creator, identity = _seed(db, "tenant_a")
        entry = _intake(db, supervisor, creator, identity)
        claimed = claim_creator(db, bd, entry.id, expected_revision=1, now=NOW)
        set_creator_responsibilities(
            db, supervisor, entry.id, expected_revision=claimed.revision,
            fulfillment_user_id=other_bd.id, maintenance_user_id=bd.id, now=NOW,
        )
        result = preflight_commission_draft(
            db, supervisor, entry.id,
            _request(expires_at=NOW - timedelta(seconds=1), duplicate=True, split=9000),
            now=NOW,
        )
        assert set(result.check_codes) == {
            "commission_split_invalid", "order_scope_overlap",
            "rule_version_expired", "rule_unapproved",
        }
        assert not result.can_submit_financial_review
        clean = preflight_commission_draft(
            db, supervisor, entry.id, _request(expires_at=NOW + timedelta(days=1)),
            now=NOW,
        )
        assert clean.check_codes == ["rule_unapproved"]


def test_preflight_requires_manager_and_complete_distinct_responsibilities() -> None:
    with _session() as db:
        _, supervisor, bd, _, creator, identity = _seed(db, "tenant_a")
        _, foreign_supervisor, _, _, _, _ = _seed(db, "tenant_b")
        entry = _intake(db, supervisor, creator, identity)
        claim_creator(db, bd, entry.id, expected_revision=1, now=NOW)
        request = _request(expires_at=NOW + timedelta(days=1))
        with pytest.raises(HTTPException) as denied:
            preflight_commission_draft(db, bd, entry.id, request, now=NOW)
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException) as hidden:
            preflight_commission_draft(db, foreign_supervisor, entry.id, request, now=NOW)
        assert hidden.value.status_code == 404
        result = preflight_commission_draft(db, supervisor, entry.id, request, now=NOW)
        assert "responsibilities_incomplete" in result.check_codes


def test_preflight_rejects_non_opaque_order_or_naive_expiry() -> None:
    with pytest.raises(ValueError):
        CommissionScopeInput(
            order_refs=["customer@example.com"], development_bps=6000,
            fulfillment_bps=2000, maintenance_bps=2000,
            calculation_evidence_ref=EVIDENCE,
        )
    with pytest.raises(ValueError):
        _request(expires_at=NOW.replace(tzinfo=None))
