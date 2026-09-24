from datetime import timedelta
from importlib import import_module

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from test_tiktok_creator_pool import NOW, _intake, _seed, _session

from app.db.models import SocialCreator, SocialCreatorEvidence, SocialPlatformIdentity
from app.tiktok.commission_preflight import CommissionScopeInput
from app.tiktok.creator_pool import claim_creator, set_creator_responsibilities

ORDER_A = "order:" + "a" * 32
ORDER_B = "order:" + "b" * 32
EVIDENCE = "evidence:" + "c" * 32


def _drafts():
    return import_module("app.tiktok.commission_drafts")


def _request(key: str, order: str = ORDER_A, development: int = 6000):
    return _drafts().CommissionDraftSaveRequest(
        idempotency_key=key, expected_pool_revision=3,
        rule_version="proposal-v1", rule_expires_at=NOW + timedelta(days=10),
        scopes=[CommissionScopeInput(
            order_refs=[order], development_bps=development,
            fulfillment_bps=2000, maintenance_bps=2000,
            calculation_evidence_ref=EVIDENCE,
        )],
    )


def _assigned(db, tenant: str = "tenant_a"):
    admin, supervisor, bd, other_bd, creator, identity = _seed(db, tenant)
    entry = _intake(db, supervisor, creator, identity)
    claimed = claim_creator(db, bd, entry.id, expected_revision=1, now=NOW)
    set_creator_responsibilities(
        db, supervisor, entry.id, expected_revision=claimed.revision,
        fulfillment_user_id=other_bd.id, maintenance_user_id=bd.id, now=NOW,
    )
    return admin, supervisor, bd, other_bd, entry


def test_save_retries_return_the_same_immutable_unapproved_draft() -> None:
    with _session() as db:
        _, supervisor, _, _, entry = _assigned(db)
        request = _request("1" * 32)
        first = _drafts().save_commission_draft(db, supervisor, entry.id, request, now=NOW)
        replay = _drafts().save_commission_draft(db, supervisor, entry.id, request, now=NOW)
        assert first.id == replay.id
        assert first.order_refs == [ORDER_A]
        assert first.owner_user_id is not None
        assert first.check_codes == ["rule_unapproved"]
        assert first.can_submit_financial_review is False
        assert len(_drafts().list_commission_drafts(db, supervisor, entry.id, now=NOW)) == 1


def test_overlapping_saved_proposals_remain_visible_but_not_approved() -> None:
    with _session() as db:
        _, supervisor, _, _, entry = _assigned(db)
        _drafts().save_commission_draft(db, supervisor, entry.id, _request("1" * 32), now=NOW)
        second = _drafts().save_commission_draft(
            db, supervisor, entry.id, _request("2" * 32), now=NOW,
        )
        assert "saved_order_overlap" in second.check_codes
        assert second.overlapping_order_refs == [ORDER_A]
        assert len(second.overlapping_draft_ids) == 1
        listed = _drafts().list_commission_drafts(db, supervisor, entry.id, now=NOW)
        assert len(listed) == 2
        assert all("saved_order_overlap" in draft.check_codes for draft in listed)
        assert all(not draft.can_submit_financial_review for draft in listed)


def test_overlap_is_tenant_wide_across_creators_but_not_across_tenants() -> None:
    with _session() as db:
        admin, supervisor, bd, other_bd, first_entry = _assigned(db)
        _, other_supervisor, _, _, foreign_entry = _assigned(db, "tenant_b")
        creator = SocialCreator(
            id="creator_second", tenant_id="tenant_a", canonical_name="Second creator",
            idempotency_key="creator-second", request_digest="sha256:test",
            created_by_user_id=admin.id,
        )
        identity = SocialPlatformIdentity(
            id="identity_second", tenant_id="tenant_a", creator_id=creator.id,
            platform="tiktok", provider_identity_id="provider_second",
            public_handle="second-creator", verified=True,
        )
        evidence = SocialCreatorEvidence(
            id="evidence_second", tenant_id="tenant_a", creator_id=creator.id,
            identity_id=identity.id, source_ref="source:second",
            data_rights_basis="user_provided", observed_at=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(days=30), idempotency_key="evidence-second",
            request_digest="sha256:test", created_by_user_id=admin.id,
        )
        db.add_all([creator, identity, evidence])
        db.commit()
        second_entry = _intake(db, supervisor, creator, identity)
        claimed = claim_creator(db, bd, second_entry.id, expected_revision=1, now=NOW)
        set_creator_responsibilities(
            db, supervisor, second_entry.id, expected_revision=claimed.revision,
            fulfillment_user_id=other_bd.id, maintenance_user_id=bd.id, now=NOW,
        )
        _drafts().save_commission_draft(
            db, other_supervisor, foreign_entry.id, _request("3" * 32), now=NOW,
        )
        first = _drafts().save_commission_draft(
            db, supervisor, first_entry.id, _request("1" * 32), now=NOW,
        )
        assert "saved_order_overlap" not in first.check_codes
        second = _drafts().save_commission_draft(
            db, supervisor, second_entry.id, _request("2" * 32), now=NOW,
        )
        assert "saved_order_overlap" in second.check_codes
        assert "saved_order_overlap" in _drafts().list_commission_drafts(
            db, supervisor, first_entry.id, now=NOW,
        )[0].check_codes


def test_postgres_overlap_candidate_query_uses_exact_indexable_refs() -> None:
    statement = _drafts()._indexed_order_refs_query("tenant_a", [ORDER_A, ORDER_B])
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "tiktok_commission_draft_order_refs" in sql
    assert "order_ref IN" in sql
    assert "tenant_id" in sql
    assert "?|" not in sql
    assert compiled.params["tenant_id_1"] == "tenant_a"
    assert compiled.params["order_ref_1"] == [ORDER_A, ORDER_B]


def test_empty_pool_history_does_not_scan_tenant_proposals(monkeypatch) -> None:
    with _session() as db:
        _, supervisor, _, _, entry = _assigned(db)
        queries: list[str] = []
        original_exec = db.exec

        def capture(statement, *args, **kwargs):
            sql = str(statement.compile(dialect=postgresql.dialect()))
            if "tiktok_commission_drafts" in sql:
                queries.append(sql)
            return original_exec(statement, *args, **kwargs)

        monkeypatch.setattr(db, "exec", capture)
        assert _drafts().list_commission_drafts(db, supervisor, entry.id, now=NOW) == []
        assert len(queries) == 1
        assert "tiktok_commission_drafts.pool_id" in queries[0].split("WHERE", 1)[1]


def test_stale_responsibilities_are_reported_without_rewriting_snapshot() -> None:
    with _session() as db:
        _, supervisor, bd, other_bd, entry = _assigned(db)
        saved = _drafts().save_commission_draft(
            db, supervisor, entry.id, _request("1" * 32), now=NOW,
        )
        set_creator_responsibilities(
            db, supervisor, entry.id, expected_revision=3,
            fulfillment_user_id=bd.id, maintenance_user_id=other_bd.id, now=NOW,
        )
        current = _drafts().list_commission_drafts(db, supervisor, entry.id, now=NOW)[0]
        assert "responsibilities_changed" in current.check_codes
        assert current.fulfillment_user_id == saved.fulfillment_user_id == other_bd.id


def test_save_requires_current_pool_revision_and_locks_its_snapshot(monkeypatch) -> None:
    with _session() as db:
        _, supervisor, bd, other_bd, entry = _assigned(db)
        queries: list[str] = []
        original_exec = db.exec

        def capture(statement, *args, **kwargs):
            sql = str(statement.compile(dialect=postgresql.dialect()))
            if "tiktok_creator_pool" in sql and "FOR UPDATE" in sql:
                queries.append(sql)
            return original_exec(statement, *args, **kwargs)

        monkeypatch.setattr(db, "exec", capture)
        request = _request("1" * 32)
        saved = _drafts().save_commission_draft(db, supervisor, entry.id, request, now=NOW)
        assert queries and all(sql.rstrip().endswith("FOR UPDATE") for sql in queries)
        set_creator_responsibilities(
            db, supervisor, entry.id, expected_revision=3,
            fulfillment_user_id=bd.id, maintenance_user_id=other_bd.id, now=NOW,
        )
        with pytest.raises(_drafts().CommissionDraftConflict, match="creator_pool_stale"):
            _drafts().save_commission_draft(
                db, supervisor, entry.id, _request("2" * 32), now=NOW,
            )
        replay = _drafts().save_commission_draft(db, supervisor, entry.id, request, now=NOW)
        assert replay.id == saved.id
        assert "responsibilities_changed" in replay.check_codes


def test_rejects_invalid_structure_and_changed_idempotency_payload() -> None:
    with _session() as db:
        _, supervisor, _, _, entry = _assigned(db)
        with pytest.raises(_drafts().CommissionDraftConflict, match="commission_split_invalid"):
            _drafts().save_commission_draft(
                db, supervisor, entry.id, _request("1" * 32, development=5000), now=NOW,
            )
        _drafts().save_commission_draft(db, supervisor, entry.id, _request("1" * 32), now=NOW)
        with pytest.raises(_drafts().CommissionDraftConflict, match="idempotency_key_reused"):
            _drafts().save_commission_draft(
                db, supervisor, entry.id, _request("1" * 32, order=ORDER_B), now=NOW,
            )


def test_bd_is_denied_and_foreign_tenant_draft_is_hidden() -> None:
    with _session() as db:
        _, supervisor, bd, _, entry = _assigned(db)
        _, foreign_supervisor, _, _, _ = _assigned(db, "tenant_b")
        _drafts().save_commission_draft(db, supervisor, entry.id, _request("1" * 32), now=NOW)
        with pytest.raises(HTTPException) as denied:
            _drafts().list_commission_drafts(db, bd, entry.id, now=NOW)
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException) as hidden:
            _drafts().list_commission_drafts(db, foreign_supervisor, entry.id, now=NOW)
        assert hidden.value.status_code == 404
