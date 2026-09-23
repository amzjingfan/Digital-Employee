import pytest
from fastapi import HTTPException
from test_tiktok_creator_pool import _intake, _seed, _session

from app.api.tiktok import creator_pool_claim, creator_pool_list
from app.config import Settings
from app.security.authorization import authorize
from app.tiktok.creator_pool import PoolRevisionRequest


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
