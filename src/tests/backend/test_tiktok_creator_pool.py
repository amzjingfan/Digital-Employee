from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlmodel import Session, select
from test_tiktok_data_validation import _seed_tenant, _session

from app.db.models import (
    SocialCreator,
    SocialCreatorEvidence,
    SocialPlatformIdentity,
    TikTokCreatorPoolEntry,
    TikTokCreatorPoolEvent,
    User,
)
from app.tiktok.creator_pool import (
    CreatorPoolConflict,
    PoolIntakeRequest,
    approve_reflow,
    assign_creator,
    claim_creator,
    enter_creator_pool,
    get_creator_pool,
    propose_reflow,
    record_effective_follow_up,
)

NOW = datetime(2026, 9, 23, 9, tzinfo=UTC)
ACTION_REF = "evidence:" + "a" * 32
LATE_ACTION_REF = "evidence:" + "b" * 32


def _seed(db, tenant_id: str):
    admin = _seed_tenant(db, tenant_id)
    supervisor = User(
        id=f"supervisor_{tenant_id}", tenant_id=tenant_id, username="supervisor",
        role="member", business_role="operations_supervisor", password_hash="disabled",
    )
    other_bd = User(
        id=f"other_bd_{tenant_id}", tenant_id=tenant_id, username="other_bd",
        role="member", business_role="tiktok_bd_specialist", password_hash="disabled",
    )
    bd = db.get(User, f"member_{tenant_id}")
    assert bd is not None
    bd.business_role = "tiktok_bd_specialist"
    creator = SocialCreator(
        id=f"creator_{tenant_id}", tenant_id=tenant_id, canonical_name="Creator",
        idempotency_key=f"creator-{tenant_id}", request_digest="sha256:test",
        created_by_user_id=admin.id,
    )
    identity = SocialPlatformIdentity(
        id=f"identity_{tenant_id}", tenant_id=tenant_id, creator_id=creator.id,
        platform="tiktok", provider_identity_id=f"provider_{tenant_id}",
        public_handle="public-creator", verified=True,
    )
    evidence = SocialCreatorEvidence(
        id=f"evidence_{tenant_id}", tenant_id=tenant_id,
        creator_id=creator.id, identity_id=identity.id,
        source_ref="source:verified-identity", data_rights_basis="user_provided",
        observed_at=NOW - timedelta(days=1), expires_at=NOW + timedelta(days=30),
        idempotency_key=f"evidence-{tenant_id}", request_digest="sha256:test",
        created_by_user_id=admin.id,
    )
    db.add_all([bd, supervisor, other_bd, creator, identity, evidence])
    db.commit()
    return admin, supervisor, bd, other_bd, creator, identity


def _intake(db, supervisor, creator, identity):
    source_id = db.exec(select(SocialCreatorEvidence.id).where(
        SocialCreatorEvidence.tenant_id == supervisor.tenant_id,
        SocialCreatorEvidence.identity_id == identity.id,
    )).first()
    return enter_creator_pool(db, supervisor, PoolIntakeRequest(
        creator_id=creator.id, identity_id=identity.id,
        source_ref=source_id, sla_rule_version="pilot-v1",
        follow_up_window_hours=48,
    ), now=NOW)


def test_claim_is_single_owner_and_stale_revision_conflicts() -> None:
    with _session() as db:
        _, supervisor, bd, other_bd, creator, identity = _seed(db, "tenant_a")
        entry = _intake(db, supervisor, creator, identity)
        claimed = claim_creator(db, bd, entry.id, expected_revision=1, now=NOW)
        assert claimed.owner_user_id == bd.id
        assert claimed.revision == 2
        assert claimed.follow_up_due_at == NOW + timedelta(hours=48)
        with pytest.raises(CreatorPoolConflict) as stale:
            claim_creator(db, other_bd, entry.id, expected_revision=1, now=NOW)
        assert stale.value.current_owner_user_id == bd.id
        assert stale.value.revision == 2
        events = list(db.exec(select(TikTokCreatorPoolEvent)).all())
        assert len(events) == 2
        claim_event = next(event for event in events if event.event_type == "claimed")
        assert claim_event.previous_owner_user_id is None
        assert claim_event.new_owner_user_id == bd.id


def test_stale_session_cannot_take_a_claim_after_first_bd_commits() -> None:
    with _session() as db:
        _, supervisor, bd, other_bd, creator, identity = _seed(db, "tenant_a")
        entry = _intake(db, supervisor, creator, identity)
        with Session(db.bind) as competing:
            stale = competing.get(TikTokCreatorPoolEntry, entry.id)
            assert stale is not None and stale.revision == 1
            claim_creator(db, bd, entry.id, expected_revision=1, now=NOW)
            with pytest.raises(CreatorPoolConflict) as conflict:
                claim_creator(competing, other_bd, entry.id, expected_revision=1, now=NOW)
            assert conflict.value.current_owner_user_id == bd.id
            assert conflict.value.revision == 2


def test_cross_tenant_and_unverified_identity_are_rejected() -> None:
    with _session() as db:
        _, supervisor_a, bd_a, _, creator_a, identity_a = _seed(db, "tenant_a")
        _, supervisor_b, bd_b, _, creator_b, identity_b = _seed(db, "tenant_b")
        entry = _intake(db, supervisor_a, creator_a, identity_a)
        with pytest.raises(HTTPException) as hidden:
            claim_creator(db, bd_b, entry.id, expected_revision=1, now=NOW)
        assert hidden.value.status_code == 404
        identity_b.verified = False
        db.add(identity_b)
        db.commit()
        with pytest.raises(CreatorPoolConflict, match="verified_tiktok_identity_required"):
            _intake(db, supervisor_b, creator_b, identity_b)
        assert get_creator_pool(db, bd_a).entries[0].id == entry.id
        assert get_creator_pool(db, bd_b).entries == []


def test_intake_rejects_duplicate_creator_and_blank_rule_version() -> None:
    with _session() as db:
        _, supervisor, _, _, creator, identity = _seed(db, "tenant_a")
        source_id = db.exec(select(SocialCreatorEvidence.id)).first()
        with pytest.raises(CreatorPoolConflict, match="sla_rule_version_required"):
            enter_creator_pool(db, supervisor, PoolIntakeRequest(
                creator_id=creator.id, identity_id=identity.id,
                source_ref=source_id, sla_rule_version="  ",
                follow_up_window_hours=48,
            ), now=NOW)
        with pytest.raises(CreatorPoolConflict, match="source_evidence_mismatch"):
            enter_creator_pool(db, supervisor, PoolIntakeRequest(
                creator_id=creator.id, identity_id=identity.id,
                source_ref="A phone number: 123456789", sla_rule_version="pilot-v1",
                follow_up_window_hours=48,
            ), now=NOW)
        _intake(db, supervisor, creator, identity)
        with pytest.raises(CreatorPoolConflict, match="creator_already_in_pool"):
            _intake(db, supervisor, creator, identity)


def test_intake_rejects_stale_latest_identity_evidence() -> None:
    with _session() as db:
        _, supervisor, _, _, creator, identity = _seed(db, "tenant_a")
        db.add(SocialCreatorEvidence(
            id="latest_expired", tenant_id="tenant_a",
            creator_id=creator.id, identity_id=identity.id,
            source_ref="source:stale-identity", data_rights_basis="user_provided",
            observed_at=NOW, expires_at=NOW + timedelta(hours=1),
            idempotency_key="latest-expired", request_digest="sha256:test",
            created_by_user_id=supervisor.id,
        ))
        db.commit()
        with pytest.raises(CreatorPoolConflict, match="current_identity_evidence_required"):
            enter_creator_pool(db, supervisor, PoolIntakeRequest(
                creator_id=creator.id, identity_id=identity.id,
                source_ref="evidence_tenant_a", sla_rule_version="pilot-v1",
                follow_up_window_hours=48,
            ), now=NOW + timedelta(hours=2))


def test_effective_follow_up_requires_owner_and_evidence() -> None:
    with _session() as db:
        _, supervisor, bd, other_bd, creator, identity = _seed(db, "tenant_a")
        entry = _intake(db, supervisor, creator, identity)
        claimed = claim_creator(db, bd, entry.id, expected_revision=1, now=NOW)
        with pytest.raises(HTTPException) as denied:
            record_effective_follow_up(
                db, other_bd, entry.id, expected_revision=2,
                evidence_ref=ACTION_REF, now=NOW + timedelta(hours=1),
            )
        assert denied.value.status_code == 403
        with pytest.raises(CreatorPoolConflict, match="evidence_ref_required"):
            record_effective_follow_up(
                db, bd, entry.id, expected_revision=2, evidence_ref=" ", now=NOW,
            )
        followed = record_effective_follow_up(
            db, bd, entry.id, expected_revision=claimed.revision,
            evidence_ref=ACTION_REF, now=NOW + timedelta(hours=1),
        )
        assert followed.follow_up_due_at == NOW + timedelta(hours=49)
        with pytest.raises(CreatorPoolConflict, match="evidence_ref_required"):
            record_effective_follow_up(
                db, bd, entry.id, expected_revision=followed.revision,
                evidence_ref="Call me at 123456789", now=NOW + timedelta(hours=2),
            )


def test_reflow_needs_supervisor_and_loses_race_to_owner_follow_up() -> None:
    with _session() as db:
        _, supervisor, bd, other_bd, creator, identity = _seed(db, "tenant_a")
        entry = _intake(db, supervisor, creator, identity)
        claim_creator(db, bd, entry.id, expected_revision=1, now=NOW)
        overdue = NOW + timedelta(hours=49)
        with pytest.raises(HTTPException) as denied:
            propose_reflow(db, other_bd, entry.id, expected_revision=2, now=overdue)
        assert denied.value.status_code == 403
        candidate = propose_reflow(db, supervisor, entry.id, expected_revision=2, now=overdue)
        assert candidate.state == "reflow_candidate"
        followed = record_effective_follow_up(
            db, bd, entry.id, expected_revision=3,
            evidence_ref=LATE_ACTION_REF, now=overdue,
        )
        assert followed.state == "claimed"
        with pytest.raises(CreatorPoolConflict):
            approve_reflow(db, supervisor, entry.id, expected_revision=3, now=overdue)
        candidate = propose_reflow(
            db, supervisor, entry.id, expected_revision=4,
            now=overdue + timedelta(hours=49),
        )
        public = approve_reflow(
            db, supervisor, entry.id, expected_revision=candidate.revision,
            now=overdue + timedelta(hours=49),
        )
        assert public.state == "public"
        assert public.owner_user_id is None


def test_supervisor_transfer_resets_due_time_and_records_both_owners() -> None:
    with _session() as db:
        _, supervisor, bd, other_bd, creator, identity = _seed(db, "tenant_a")
        entry = _intake(db, supervisor, creator, identity)
        claim_creator(db, bd, entry.id, expected_revision=1, now=NOW)
        changed = assign_creator(
            db, supervisor, entry.id, expected_revision=2,
            target_user_id=other_bd.id, reason="staff_change", now=NOW + timedelta(hours=4),
        )
        assert changed.owner_user_id == other_bd.id
        assert changed.state == "claimed"
        assert changed.follow_up_due_at == NOW + timedelta(hours=52)
        event = db.exec(select(TikTokCreatorPoolEvent).where(
            TikTokCreatorPoolEvent.event_type == "transferred",
        )).one()
        assert (event.previous_owner_user_id, event.new_owner_user_id) == (bd.id, other_bd.id)
        assert event.reason == "staff_change"
        with pytest.raises(HTTPException) as former_owner:
            record_effective_follow_up(
                db, bd, entry.id, expected_revision=3, evidence_ref=ACTION_REF, now=NOW,
            )
        assert former_owner.value.status_code == 403


def test_supervisor_release_ends_assignment_and_stale_transfer_cannot_win() -> None:
    with _session() as db:
        _, supervisor, bd, other_bd, creator, identity = _seed(db, "tenant_a")
        entry = _intake(db, supervisor, creator, identity)
        claim_creator(db, bd, entry.id, expected_revision=1, now=NOW)
        released = assign_creator(
            db, supervisor, entry.id, expected_revision=2,
            target_user_id=None, reason="manual_release", now=NOW,
        )
        assert (released.state, released.owner_user_id, released.follow_up_due_at) == (
            "public", None, None,
        )
        event = db.exec(select(TikTokCreatorPoolEvent).where(
            TikTokCreatorPoolEvent.event_type == "released",
        )).one()
        assert (event.previous_owner_user_id, event.new_owner_user_id) == (bd.id, None)
        with pytest.raises(CreatorPoolConflict) as stale:
            assign_creator(
                db, supervisor, entry.id, expected_revision=2,
                target_user_id=other_bd.id, reason="staff_change", now=NOW,
            )
        assert stale.value.revision == 3


def test_transfer_rejects_inactive_foreign_or_non_bd_targets_and_bad_reasons() -> None:
    with _session() as db:
        _, supervisor, bd, other_bd, creator, identity = _seed(db, "tenant_a")
        _, _, foreign_bd, _, _, _ = _seed(db, "tenant_b")
        entry = _intake(db, supervisor, creator, identity)
        claim_creator(db, bd, entry.id, expected_revision=1, now=NOW)
        for target in (foreign_bd.id, supervisor.id):
            with pytest.raises(CreatorPoolConflict, match="active_tenant_bd_required"):
                assign_creator(
                    db, supervisor, entry.id, expected_revision=2,
                    target_user_id=target, reason="staff_change", now=NOW,
                )
        with pytest.raises(CreatorPoolConflict, match="creator_already_assigned"):
            assign_creator(
                db, supervisor, entry.id, expected_revision=2,
                target_user_id=bd.id, reason="staff_change", now=NOW,
            )
        other_bd.status = "disabled"
        db.add(other_bd)
        db.commit()
        with pytest.raises(CreatorPoolConflict, match="active_tenant_bd_required"):
            assign_creator(
                db, supervisor, entry.id, expected_revision=2,
                target_user_id=other_bd.id, reason="staff_change", now=NOW,
            )
        with pytest.raises(CreatorPoolConflict, match="assignment_reason_invalid"):
            assign_creator(
                db, supervisor, entry.id, expected_revision=2,
                target_user_id=None, reason="staff_change", now=NOW,
            )
        with pytest.raises(HTTPException) as denied:
            assign_creator(
                db, bd, entry.id, expected_revision=2,
                target_user_id=None, reason="manual_release", now=NOW,
            )
        assert denied.value.status_code == 403
