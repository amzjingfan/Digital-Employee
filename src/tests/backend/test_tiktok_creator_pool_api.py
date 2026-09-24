from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from test_tiktok_commission_drafts import _assigned, _request
from test_tiktok_creator_pool import _intake, _seed, _session

from app.api import tiktok as tiktok_api
from app.api.tiktok import (
    commission_draft_preflight,
    creator_pool_assign,
    creator_pool_claim,
    creator_pool_list,
    creator_pool_responsibilities,
)
from app.config import Settings
from app.security.authorization import authorize, default_policy_text
from app.security.policy_lifecycle import create_policy_draft, publish_policy
from app.tiktok.commission_preflight import CommissionPreflightRequest, CommissionScopeInput
from app.tiktok.creator_pool import (
    PoolAssignmentRequest,
    PoolResponsibilitiesRequest,
    PoolRevisionRequest,
)


def test_commission_preflight_route_allows_supervisor_or_admin_but_never_approves() -> None:
    with _session() as db:
        admin, supervisor, bd, _, creator, identity = _seed(db, "tenant_a")
        entry = _intake(db, supervisor, creator, identity)
        settings = Settings(_env_file=None, casbin_enabled=True)
        path = f"/api/enterprise/tiktok/commission-drafts/{entry.id}/preflight"
        assert authorize(settings, user=supervisor, object_path=path, action="POST").allowed
        assert authorize(settings, user=admin, object_path=path, action="POST").allowed
        assert not authorize(settings, user=bd, object_path=path, action="POST").allowed
        result = commission_draft_preflight(
            entry.id, CommissionPreflightRequest(
                rule_version="proposal-v1",
                rule_expires_at=datetime(2026, 9, 24, tzinfo=UTC) + timedelta(days=365),
                scopes=[CommissionScopeInput(
                    order_refs=["order:" + "a" * 32],
                    development_bps=6000, fulfillment_bps=2000, maintenance_bps=2000,
                    calculation_evidence_ref="evidence:" + "b" * 32,
                )],
            ), current_user=supervisor, db=db,
        )
        assert not result.can_submit_financial_review
        assert "rule_unapproved" in result.check_codes
        admin_result = commission_draft_preflight(
            entry.id, CommissionPreflightRequest(
                rule_version="proposal-v1",
                rule_expires_at=datetime(2027, 9, 24, tzinfo=UTC),
                scopes=[CommissionScopeInput(
                    order_refs=["order:" + "a" * 32],
                    development_bps=6000, fulfillment_bps=2000, maintenance_bps=2000,
                    calculation_evidence_ref="evidence:" + "b" * 32,
                )],
            ), current_user=admin, db=db,
        )
        assert "rule_unapproved" in admin_result.check_codes


def test_unapproved_draft_routes_are_supervisor_only_and_never_submit_finance() -> None:
    with _session() as db:
        admin, supervisor, bd, _, entry = _assigned(db)
        settings = Settings(_env_file=None, casbin_enabled=True)
        path = f"/api/enterprise/tiktok/commission-drafts/{entry.id}"
        assert authorize(settings, user=supervisor, object_path=path, action="POST").allowed
        assert authorize(settings, user=admin, object_path=path, action="GET").allowed
        saved = tiktok_api.commission_drafts_save(
            entry.id, _request("3" * 32), current_user=supervisor, db=db,
        )
        assert saved.check_codes == ["rule_unapproved"]
        assert tiktok_api.commission_drafts_list(
            entry.id, current_user=admin, db=db,
        )[0].id == saved.id
        with pytest.raises(HTTPException) as denied:
            tiktok_api.commission_drafts_list(entry.id, current_user=bd, db=db)
        assert denied.value.status_code == 403
        assert not any(
            route.path.endswith("/commission-drafts/{entry_id}/submit")
            for route in tiktok_api.router.routes
        )


def test_supervisor_and_admin_set_distinct_responsibilities_but_bd_cannot() -> None:
    with _session() as db:
        admin, supervisor, bd, other_bd, creator, identity = _seed(db, "tenant_a")
        entry = _intake(db, supervisor, creator, identity)
        creator_pool_claim(
            entry.id, PoolRevisionRequest(expected_revision=1), current_user=bd, db=db,
        )
        settings = Settings(_env_file=None, casbin_enabled=True)
        path = f"/api/enterprise/tiktok/creator-responsibilities/{entry.id}"
        assert authorize(settings, user=supervisor, object_path=path, action="POST").allowed
        assert authorize(settings, user=admin, object_path=path, action="POST").allowed
        assert not authorize(settings, user=bd, object_path=path, action="POST").allowed
        result = creator_pool_responsibilities(
            entry.id,
            PoolResponsibilitiesRequest(
                expected_revision=2, fulfillment_user_id=other_bd.id,
                maintenance_user_id=bd.id,
            ),
            current_user=supervisor, db=db,
        )
        assert result.fulfillment_user_id == other_bd.id
        assert result.maintenance_user_id == bd.id
        admin_change = creator_pool_responsibilities(
            entry.id,
            PoolResponsibilitiesRequest(
                expected_revision=3, fulfillment_user_id=bd.id,
                maintenance_user_id=other_bd.id,
            ),
            current_user=admin, db=db,
        )
        assert admin_change.fulfillment_user_id == bd.id


def test_bd_claim_route_and_casbin_are_narrowly_scoped() -> None:
    with _session() as db:
        _, supervisor, bd, _, creator, identity = _seed(db, "tenant_a")
        entry = _intake(db, supervisor, creator, identity)
        settings = Settings(_env_file=None, casbin_enabled=True)
        claim_path = f"/api/enterprise/tiktok/creator-claims/{entry.id}"
        assert authorize(settings, user=bd, object_path=claim_path, action="POST").allowed
        assert not authorize(settings, user=bd, object_path="/api/enterprise/tiktok/creator-pool",
                             action="POST").allowed
        assert not authorize(settings, user=bd,
                             object_path=f"/api/enterprise/tiktok/creator-reflow-approvals/{entry.id}",
                             action="POST").allowed
        claimed = creator_pool_claim(
            entry.id, PoolRevisionRequest(expected_revision=1), current_user=bd, db=db,
        )
        assert claimed.owner_user_id == bd.id
        assert len(creator_pool_list(current_user=bd, db=db).entries) == 1
        with pytest.raises(HTTPException) as conflict:
            creator_pool_claim(
                entry.id, PoolRevisionRequest(expected_revision=1), current_user=bd, db=db,
            )
        assert conflict.value.status_code == 409
        assert conflict.value.detail["revision"] == 2


def test_published_tenant_policy_needs_a_reviewed_successor_for_claims() -> None:
    with _session() as db:
        admin, _, bd, _, _, _ = _seed(db, "tenant_a")
        settings = Settings(_env_file=None, casbin_enabled=True)
        current = default_policy_text(settings)
        grants = (
            "p, tiktok_bd_specialist, *, /api/enterprise/tiktok/creator-claims/*, POST, allow",
            "p, tiktok_bd_specialist, *, /api/enterprise/tiktok/creator-follow-ups/*, POST, allow",
        )
        assert all(grant in current for grant in grants)
        previous = current
        for grant in grants:
            previous = previous.replace(grant + "\n", "")
        first = create_policy_draft(
            db, settings, tenant_id=admin.tenant_id, actor=admin,
            description="Previous tenant policy", policy_text=previous,
        )
        publish_policy(
            db, settings, tenant_id=admin.tenant_id, release_id=first.id,
            actor=admin, reason="Synthetic policy baseline",
        )
        claim_path = "/api/enterprise/tiktok/creator-claims/pool_1"
        assert not authorize(settings, user=bd, object_path=claim_path, action="POST", db=db).allowed

        successor = create_policy_draft(
            db, settings, tenant_id=admin.tenant_id, actor=admin,
            description="Creator claim grants", policy_text=current,
        )
        publish_policy(
            db, settings, tenant_id=admin.tenant_id, release_id=successor.id,
            actor=admin, reason="Reviewed creator claim rollout",
        )
        assert authorize(settings, user=bd, object_path=claim_path, action="POST", db=db).allowed


def test_supervisor_assignment_route_excludes_bd_and_lists_active_targets() -> None:
    with _session() as db:
        _, supervisor, bd, other_bd, creator, identity = _seed(db, "tenant_a")
        entry = _intake(db, supervisor, creator, identity)
        settings = Settings(_env_file=None, casbin_enabled=True)
        path = f"/api/enterprise/tiktok/creator-assignments/{entry.id}"
        assert authorize(settings, user=supervisor, object_path=path, action="POST").allowed
        assert not authorize(settings, user=bd, object_path=path, action="POST").allowed
        manager_workspace = creator_pool_list(current_user=supervisor, db=db)
        assert {candidate.id for candidate in manager_workspace.assignable_bds} == {
            bd.id, other_bd.id,
        }
        assert creator_pool_list(current_user=bd, db=db).assignable_bds == []
        creator_pool_claim(
            entry.id, PoolRevisionRequest(expected_revision=1), current_user=bd, db=db,
        )
        changed = creator_pool_assign(
            entry.id,
            PoolAssignmentRequest(
                expected_revision=2, target_user_id=other_bd.id, reason="staff_change",
            ),
            current_user=supervisor, db=db,
        )
        assert changed.owner_user_id == other_bd.id
