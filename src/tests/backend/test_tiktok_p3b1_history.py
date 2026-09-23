from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlmodel import select
from test_tiktok_data_validation import (
    RECORDED_NOW,
    _fully_configured_workspace,
    _recorded_request,
    _session,
)

from app.db.models import (
    TikTokDataValidationScope,
    TikTokHistoryFact,
    User,
)
from app.tiktok.data_validation import run_recorded_data_validation
from app.tiktok.p3b1_history import (
    HistoryConflict,
    HistoryImportRequest,
    ReconciliationRequest,
    confirm_history_reconciliation,
    get_history_workspace,
    import_history,
    record_reconciliation,
)


def _recorded_batch(db, tenant_id: str):
    admin = _fully_configured_workspace(db, tenant_id)
    member = db.get(User, f"member_{tenant_id}")
    assert member is not None
    member.business_role = "tiktok_bd_specialist"
    db.add(member)
    db.commit()
    recorded = _recorded_request(tenant_id)
    run = run_recorded_data_validation(db, admin, recorded, now=RECORDED_NOW)
    assert run.status == "passed"
    return admin, recorded, run


def test_import_is_idempotent_and_tenant_scoped() -> None:
    with _session() as db:
        admin_a, recorded_a, run_a = _recorded_batch(db, "tenant_a")
        admin_b, recorded_b, run_b = _recorded_batch(db, "tenant_b")
        request_a = HistoryImportRequest(
            recorded_run_id=run_a.id,
            source_kind="synthetic",
            assigned_bd_user_id="member_tenant_a",
            dataset=recorded_a.dataset,
        )
        first = import_history(db, admin_a, request_a, now=RECORDED_NOW)
        second = import_history(db, admin_a, request_a, now=RECORDED_NOW)
        import_history(
            db,
            admin_b,
            HistoryImportRequest(
                recorded_run_id=run_b.id,
                source_kind="synthetic",
                assigned_bd_user_id="member_tenant_b",
                dataset=recorded_b.dataset,
            ),
            now=RECORDED_NOW,
        )

        assert first.batch_id == second.batch_id
        assert first.inserted_count == 6
        assert second.inserted_count == 0
        assert len(db.exec(select(TikTokHistoryFact)).all()) == 12
        workspace_a = get_history_workspace(db, admin_a)
        assert workspace_a.total_count == 6
        assert {fact.tenant_id for fact in workspace_a.facts} == {"tenant_a"}
        assert workspace_a.eligible_reviewed_count == 0
        assert [item["id"] for item in workspace_a.bd_options] == ["member_tenant_a"]


def test_import_rejects_cross_tenant_run_and_changed_dataset() -> None:
    with _session() as db:
        admin_a, recorded_a, run_a = _recorded_batch(db, "tenant_a")
        admin_b, _, _ = _recorded_batch(db, "tenant_b")
        request = HistoryImportRequest(
            recorded_run_id=run_a.id,
            source_kind="approved_redacted_history",
            assigned_bd_user_id="member_tenant_b",
            dataset=recorded_a.dataset,
        )
        with pytest.raises(HistoryConflict, match="recorded_run_not_found"):
            import_history(db, admin_b, request, now=RECORDED_NOW)
        request.assigned_bd_user_id = "member_tenant_a"
        changed = request.model_copy(deep=True)
        changed.dataset.orders[0].status = "changed"
        with pytest.raises(HistoryConflict, match="dataset_digest_mismatch"):
            import_history(db, admin_a, changed, now=RECORDED_NOW)


def test_reconciliation_is_append_only_and_synthetic_never_counts() -> None:
    with _session() as db:
        admin, recorded, run = _recorded_batch(db, "tenant_a")
        import_history(
            db,
            admin,
            HistoryImportRequest(
                recorded_run_id=run.id,
                source_kind="synthetic",
                assigned_bd_user_id="member_tenant_a",
                dataset=recorded.dataset,
            ),
            now=RECORDED_NOW,
        )
        fact = db.exec(
            select(TikTokHistoryFact).where(
                TikTokHistoryFact.tenant_id == "tenant_a",
                TikTokHistoryFact.domain == "sample",
            )
        ).one()
        member = db.get(User, "member_tenant_a")
        assert member is not None
        member.business_role = "tiktok_bd_specialist"
        db.add(member)
        db.commit()
        first = record_reconciliation(
            db,
            member,
            fact.id,
            ReconciliationRequest(verdict="matched", reason="已核对脱敏样品记录"),
            now=datetime(2026, 9, 29, tzinfo=UTC),
        )
        second = record_reconciliation(
            db,
            member,
            fact.id,
            ReconciliationRequest(verdict="needs_review", reason="需业务复核"),
            now=datetime(2026, 9, 29, 1, tzinfo=UTC),
        )

        assert first.id != second.id
        workspace = get_history_workspace(db, admin)
        assert workspace.reviewed_count == 0
        assert workspace.eligible_reviewed_count == 0
        assert next(row for row in workspace.facts if row.id == fact.id).latest_verdict == "needs_review"


def test_owner_cannot_confirm_with_fewer_than_thirty_eligible_reviews() -> None:
    with _session() as db:
        admin, recorded, run = _recorded_batch(db, "tenant_a")
        import_history(
            db,
            admin,
            HistoryImportRequest(
                recorded_run_id=run.id,
                source_kind="approved_redacted_history",
                assigned_bd_user_id="member_tenant_a",
                dataset=recorded.dataset,
            ),
            now=RECORDED_NOW,
        )
        fact = db.exec(select(TikTokHistoryFact).where(
            TikTokHistoryFact.tenant_id == "tenant_a"
        )).first()
        assert fact is not None
        member = db.get(User, "member_tenant_a")
        assert member is not None
        record_reconciliation(
            db,
            member,
            fact.id,
            ReconciliationRequest(verdict="matched", reason="业务事实已人工核对"),
        )
        with pytest.raises(HistoryConflict, match="thirty_reviews_required"):
            confirm_history_reconciliation(db, admin, approval_ref="approval:owner-001")


def test_owner_signoff_tracks_exact_review_snapshot_and_scope_state() -> None:
    with _session() as db:
        admin, recorded, run = _recorded_batch(db, "tenant_a")
        import_history(db, admin, HistoryImportRequest(
            recorded_run_id=run.id,
            source_kind="approved_redacted_history",
            assigned_bd_user_id="member_tenant_a",
            dataset=recorded.dataset,
        ), now=RECORDED_NOW)
        facts = list(db.exec(select(TikTokHistoryFact).where(
            TikTokHistoryFact.tenant_id == "tenant_a",
        )).all())
        exemplar = facts[0]
        for index in range(6, 30):
            db.add(TikTokHistoryFact(
                tenant_id=exemplar.tenant_id,
                scope_id=exemplar.scope_id,
                batch_id=exemplar.batch_id,
                source_label=exemplar.source_label,
                domain="sample",
                business_key=f"sample-{index}",
                observed_at=exemplar.observed_at,
                values_json={"application_id": f"sample-{index}"},
                fact_digest=f"test-{index}",
            ))
        db.commit()
        facts = list(db.exec(select(TikTokHistoryFact).where(
            TikTokHistoryFact.tenant_id == "tenant_a",
        )).all())
        member = db.get(User, "member_tenant_a")
        assert member is not None
        for fact in facts:
            record_reconciliation(db, member, fact.id, ReconciliationRequest(
                verdict="matched", reason="人工核对通过",
            ))
        signoff = confirm_history_reconciliation(db, admin, approval_ref="owner-review-001")
        assert signoff.reviewed_count == 30
        assert get_history_workspace(db, admin).exit_ready is True

        record_reconciliation(db, member, facts[0].id, ReconciliationRequest(
            verdict="needs_review", reason="待重新核对",
        ))
        assert get_history_workspace(db, admin).exit_ready is False

        record_reconciliation(db, member, facts[0].id, ReconciliationRequest(
            verdict="matched", reason="再次人工核对",
        ))
        confirm_history_reconciliation(db, admin, approval_ref="owner-review-002")
        scope = db.exec(select(TikTokDataValidationScope).where(
            TikTokDataValidationScope.tenant_id == "tenant_a",
        )).one()
        scope.revision += 1
        db.add(scope)
        db.commit()
        assert get_history_workspace(db, admin).exit_ready is False


def test_reconciliation_rejects_whitespace_reason() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ReconciliationRequest(verdict="matched", reason="    ")


def test_missing_metric_source_is_not_reported_as_zero() -> None:
    with _session() as db:
        admin = _fully_configured_workspace(db, "tenant_a")
        workspace = get_history_workspace(db, admin)
        assert len(workspace.metrics) == 6
        assert {item.value for item in workspace.metrics} == {None}
        assert next(item for item in workspace.metrics if item.code == "sample_count").reason == "source_missing"


def test_history_filters_and_metrics_use_latest_business_key_once() -> None:
    with _session() as db:
        admin, recorded, run = _recorded_batch(db, "tenant_a")
        import_history(db, admin, HistoryImportRequest(
            recorded_run_id=run.id, source_kind="synthetic",
            assigned_bd_user_id="member_tenant_a", dataset=recorded.dataset,
        ), now=RECORDED_NOW)
        baseline = get_history_workspace(db, admin)
        baseline_gmv = next(item.value for item in baseline.metrics if item.code == "gmv")
        original = db.exec(select(TikTokHistoryFact).where(
            TikTokHistoryFact.tenant_id == "tenant_a",
            TikTokHistoryFact.domain == "gmv",
        )).one()
        db.add(TikTokHistoryFact(
            tenant_id=original.tenant_id, scope_id=original.scope_id,
            batch_id=original.batch_id, source_label=original.source_label,
            domain="gmv", business_key=original.business_key,
            observed_at=datetime(2026, 9, 22, tzinfo=UTC),
            values_json=original.values_json, fact_digest="later-observation",
        ))
        db.commit()
        workspace = get_history_workspace(db, admin)
        assert next(item.value for item in workspace.metrics if item.code == "gmv") == baseline_gmv
        sample = get_history_workspace(db, admin, domain="sample", page=1, limit=1)
        assert sample.total_count == 1
        assert len(sample.facts) == 1
        assert next(item for item in sample.metrics if item.code == "gmv").value is None


def test_only_assigned_bd_can_review_and_unrelated_member_cannot_read() -> None:
    with _session() as db:
        admin, recorded, run = _recorded_batch(db, "tenant_a")
        import_history(db, admin, HistoryImportRequest(
            recorded_run_id=run.id, source_kind="synthetic",
            assigned_bd_user_id="member_tenant_a", dataset=recorded.dataset,
        ), now=RECORDED_NOW)
        fact = db.exec(select(TikTokHistoryFact).where(
            TikTokHistoryFact.tenant_id == "tenant_a",
        )).first()
        assert fact is not None
        with pytest.raises(HTTPException) as admin_denied:
            record_reconciliation(db, admin, fact.id, ReconciliationRequest(
                verdict="matched", reason="应由负责 BD 核对",
            ))
        assert admin_denied.value.status_code == 403
        member = db.get(User, "member_tenant_a")
        assert member is not None
        member.business_role = "member"
        db.add(member)
        db.commit()
        with pytest.raises(HTTPException) as read_denied:
            get_history_workspace(db, member)
        assert read_denied.value.status_code == 403


def test_thirty_observations_of_same_business_key_do_not_satisfy_review_gate() -> None:
    with _session() as db:
        admin, recorded, run = _recorded_batch(db, "tenant_a")
        import_history(db, admin, HistoryImportRequest(
            recorded_run_id=run.id, source_kind="approved_redacted_history",
            assigned_bd_user_id="member_tenant_a", dataset=recorded.dataset,
        ), now=RECORDED_NOW)
        exemplar = db.exec(select(TikTokHistoryFact).where(
            TikTokHistoryFact.tenant_id == "tenant_a",
            TikTokHistoryFact.domain == "sample",
        )).one()
        for index in range(1, 25):
            db.add(TikTokHistoryFact(
                tenant_id=exemplar.tenant_id, scope_id=exemplar.scope_id,
                batch_id=exemplar.batch_id, source_label=exemplar.source_label,
                domain=exemplar.domain, business_key=exemplar.business_key,
                observed_at=exemplar.observed_at + timedelta(minutes=index),
                values_json=exemplar.values_json, fact_digest=f"observation-{index}",
            ))
        db.commit()
        member = db.get(User, "member_tenant_a")
        assert member is not None
        for fact in db.exec(select(TikTokHistoryFact).where(
            TikTokHistoryFact.tenant_id == "tenant_a",
        )).all():
            record_reconciliation(db, member, fact.id, ReconciliationRequest(
                verdict="matched", reason="人工核对完成",
            ))
        workspace = get_history_workspace(db, admin)
        assert workspace.total_count == 30
        assert workspace.eligible_reviewed_count == 6
        with pytest.raises(HistoryConflict, match="thirty_reviews_required"):
            confirm_history_reconciliation(db, admin, approval_ref="owner-review-duplicate")
