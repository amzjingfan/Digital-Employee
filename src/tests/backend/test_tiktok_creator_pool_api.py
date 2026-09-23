import pytest
from fastapi import HTTPException
from test_tiktok_creator_pool import _intake, _seed, _session

from app.api.tiktok import creator_pool_assign, creator_pool_claim, creator_pool_list
from app.config import Settings
from app.security.authorization import authorize, default_policy_text
from app.security.policy_lifecycle import create_policy_draft, publish_policy
from app.tiktok.creator_pool import PoolAssignmentRequest, PoolRevisionRequest


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
