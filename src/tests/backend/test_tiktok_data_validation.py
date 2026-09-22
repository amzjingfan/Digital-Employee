from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import (
    BusinessResource,
    ExternalAuthorization,
    Tenant,
    TikTokCapabilityEvidence,
    TikTokDataValidationRun,
    TikTokDataValidationScope,
    TikTokFieldContract,
    User,
)
from app.tiktok.data_validation import (
    CAPABILITY_CATALOG,
    DATA_VALIDATION_CATALOG_VERSION,
    FIELD_CATALOG,
    MOCK_DATASET,
    MOCK_VALIDATION_CLOCK,
    PROVIDER_CATALOG,
    TikTokDataValidationConflict,
    TikTokDataValidationNotFound,
    bootstrap_data_validation_workspace,
    evaluate_data_validation_readiness,
    get_data_validation_workspace,
    run_mock_data_validation,
    update_capability_evidence,
    update_data_validation_scope,
    update_field_contract,
    validate_mock_dataset,
)
from app.tiktok.schema import (
    TikTokCapabilityEvidenceUpdate,
    TikTokDataValidationScopeUpdate,
    TikTokFieldContractUpdate,
    TikTokFieldSource,
)


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_tenant(db: Session, tenant_id: str) -> User:
    admin = User(
        id=f"admin_{tenant_id}",
        tenant_id=tenant_id,
        username=f"admin_{tenant_id}",
        role="admin",
        business_role="platform_admin",
        password_hash="disabled",
    )
    member = User(
        id=f"member_{tenant_id}",
        tenant_id=tenant_id,
        username=f"member_{tenant_id}",
        role="member",
        business_role="member",
        password_hash="disabled",
    )
    db.add(Tenant(id=tenant_id, name=tenant_id))
    db.add(admin)
    db.add(member)
    db.add(
        BusinessResource(
            id=f"store_{tenant_id}",
            tenant_id=tenant_id,
            resource_type="store",
            code=f"TT-US-{tenant_id}",
            name=f"TikTok Shop US {tenant_id}",
            created_by_user_id=admin.id,
            metadata_json={"platform": "tiktok", "market": "US"},
        )
    )
    db.commit()
    db.refresh(admin)
    return admin


def test_bootstrap_is_idempotent_and_does_not_overwrite_tenant_edits() -> None:
    with _session() as db:
        admin = _seed_tenant(db, "tenant_a")
        first = bootstrap_data_validation_workspace(db, admin)
        contract = db.exec(
            select(TikTokFieldContract).where(
                TikTokFieldContract.tenant_id == "tenant_a",
                TikTokFieldContract.field_code == "order.order_id",
            )
        ).one()
        contract.label = "租户自定义订单编号"
        db.add(contract)
        db.commit()

        second = bootstrap_data_validation_workspace(db, admin)

        assert DATA_VALIDATION_CATALOG_VERSION == "p3-b0.v1"
        assert first.created_field_count == 30
        assert first.created_evidence_count == 31
        assert second.created_field_count == 0
        assert second.created_evidence_count == 0
        assert db.get(TikTokFieldContract, contract.id).label == "租户自定义订单编号"


def test_workspace_read_is_tenant_scoped_even_when_codes_match() -> None:
    with _session() as db:
        admin_a = _seed_tenant(db, "tenant_a")
        admin_b = _seed_tenant(db, "tenant_b")
        bootstrap_data_validation_workspace(db, admin_a)
        bootstrap_data_validation_workspace(db, admin_b)

        workspace_a = get_data_validation_workspace(db, admin_a)

        assert workspace_a.tenant_id == "tenant_a"
        assert len(workspace_a.field_contracts) == 30
        assert len(workspace_a.capability_evidence) == 31
        assert {item.tenant_id for item in workspace_a.field_contracts} == {"tenant_a"}
        assert {option.id for option in workspace_a.store_options} == {"store_tenant_a"}
        assert {option.id for option in workspace_a.owner_options} == {
            "admin_tenant_a",
            "member_tenant_a",
        }


def test_bootstrap_uses_only_mock_sources_and_unverified_evidence() -> None:
    with _session() as db:
        admin = _seed_tenant(db, "tenant_a")
        bootstrap_data_validation_workspace(db, admin)

        contracts = db.exec(
            select(TikTokFieldContract).where(TikTokFieldContract.tenant_id == "tenant_a")
        ).all()
        evidence = db.exec(
            select(TikTokCapabilityEvidence).where(
                TikTokCapabilityEvidence.tenant_id == "tenant_a"
            )
        ).all()

        assert len(contracts) == 30
        assert all(
            len(item.sources_json) == 1
            and item.sources_json[0]["source_type"] == "mock_fixture"
            and item.sources_json[0]["usage"] == "mock"
            and item.sources_json[0]["decision"] == "use"
            and item.sources_json[0]["authorization_state"] == "not_required"
            for item in contracts
        )
        assert len(evidence) == 31
        assert all(
            item.evidence_level == "E0"
            and item.evidence_type == "unverified"
            and item.status == "unverified"
            and item.checked_by_user_id is None
            and item.checked_at is None
            for item in evidence
        )


def _source(
    source_key: str,
    *,
    priority: int = 1,
    usage: str = "mock",
    decision: str = "use",
    authorization_state: str = "not_required",
) -> TikTokFieldSource:
    return TikTokFieldSource(
        source_key=source_key,
        source_type="mock_fixture" if usage == "mock" else "official_api",
        object_name="order",
        field_path="order.id",
        priority=priority,
        usage=usage,
        decision=decision,
        authorization_state=authorization_state,
    )


def _confirmed_contract(
    *, revision: int, owner_user_id: str = "admin_tenant_a"
) -> TikTokFieldContractUpdate:
    return TikTokFieldContractUpdate(
        revision=revision,
        owner_user_id=owner_user_id,
        business_key="order_id",
        freshness_sla_seconds=3600,
        missing_behavior="block_stage",
        status="confirmed",
        sources=[_source("mock.order.id")],
    )


def test_field_source_rejects_duplicate_priority_and_denied_use() -> None:
    with pytest.raises(ValidationError):
        TikTokFieldContractUpdate(
            revision=1,
            owner_user_id="admin_tenant_a",
            business_key="order_id",
            freshness_sla_seconds=3600,
            missing_behavior="block_stage",
            status="confirmed",
            sources=[
                _source("mock.order.id", priority=1, usage="mock"),
                _source("mock.order.id.copy", priority=1, usage="mock"),
            ],
        )
    with pytest.raises(ValidationError):
        TikTokFieldContractUpdate(
            revision=1,
            owner_user_id="admin_tenant_a",
            business_key="order_id",
            freshness_sla_seconds=3600,
            missing_behavior="block_stage",
            status="confirmed",
            sources=[
                _source(
                    "vendor.order.id",
                    usage="real",
                    decision="use",
                    authorization_state="denied",
                )
            ],
        )


def test_stale_revision_and_cross_tenant_references_do_not_mutate() -> None:
    with _session() as db:
        admin_a = _seed_tenant(db, "tenant_a")
        admin_b = _seed_tenant(db, "tenant_b")
        bootstrap_data_validation_workspace(db, admin_a)
        updated = update_field_contract(
            db, admin_a, "order.order_id", _confirmed_contract(revision=1)
        )
        assert updated.revision == 2
        with pytest.raises(TikTokDataValidationConflict, match="revision_conflict"):
            update_field_contract(
                db, admin_a, "order.order_id", _confirmed_contract(revision=1)
            )
        with pytest.raises(TikTokDataValidationNotFound, match="owner_not_found"):
            update_field_contract(
                db,
                admin_a,
                "order.order_id",
                _confirmed_contract(revision=2, owner_user_id=admin_b.id),
            )


def test_scope_mutation_rejects_cross_tenant_store_and_member_writes() -> None:
    with _session() as db:
        admin_a = _seed_tenant(db, "tenant_a")
        _seed_tenant(db, "tenant_b")
        bootstrap_data_validation_workspace(db, admin_a)
        request = TikTokDataValidationScopeUpdate(
            revision=0,
            store_resource_id="store_tenant_b",
            creator_scope_summary="US pilot creators",
            business_owner_user_id="admin_tenant_a",
            data_owner_user_id="member_tenant_a",
            status="active",
        )
        with pytest.raises(TikTokDataValidationNotFound, match="store_not_found"):
            update_data_validation_scope(db, admin_a, request)

        member = db.get(User, "member_tenant_a")
        assert member is not None
        valid_scope = request.model_copy(update={"store_resource_id": "store_tenant_a"})
        with pytest.raises(HTTPException) as denied:
            update_data_validation_scope(db, member, valid_scope)
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException):
            update_field_contract(
                db, member, "order.order_id", _confirmed_contract(revision=1)
            )
        with pytest.raises(HTTPException):
            update_capability_evidence(
                db,
                member,
                "seller.shop.read",
                TikTokCapabilityEvidenceUpdate(
                    revision=1,
                    subject_key="global",
                    required_scope="shop.read",
                    evidence_level="E1",
                    evidence_type="official_docs",
                    status="verified",
                    summary="Documented capability",
                    evidence_ref="doc:shop-read",
                    checked_by_user_id=admin_a.id,
                    checked_at=datetime(2026, 9, 22, tzinfo=UTC),
                ),
            )


def test_unknown_catalog_code_and_provider_without_audit_details_are_rejected() -> None:
    with _session() as db:
        admin = _seed_tenant(db, "tenant_a")
        bootstrap_data_validation_workspace(db, admin)
        with pytest.raises(TikTokDataValidationNotFound, match="catalog_entry_not_found"):
            update_field_contract(db, admin, "order.unknown", _confirmed_contract(revision=1))
    with pytest.raises(ValidationError):
        TikTokCapabilityEvidenceUpdate(
            revision=1,
            subject_key="global",
            evidence_level="E1",
            evidence_type="official_docs",
            status="verified",
            decision="use",
            summary="",
            evidence_ref="contract:fastmoss",
        )


@pytest.mark.parametrize(
    ("level", "evidence_type"),
    (("E3", "mock"), ("E2", "official_docs"), ("E0", "sandbox")),
)
def test_evidence_level_type_combinations_are_strict(level: str, evidence_type: str) -> None:
    with pytest.raises(ValidationError):
        TikTokCapabilityEvidenceUpdate(
            revision=1,
            subject_key="seller-us",
            resource_id="store_tenant_a",
            required_scope="shop.read",
            evidence_level=level,
            evidence_type=evidence_type,
            status="verified",
            summary="Evidence summary",
            evidence_ref="evidence:1",
            checked_by_user_id="admin_tenant_a",
            checked_at=datetime(2026, 9, 22, tzinfo=UTC),
        )


def _configured_readiness_rows() -> tuple[
    TikTokDataValidationScope,
    list[TikTokFieldContract],
    list[TikTokCapabilityEvidence],
    TikTokDataValidationRun,
]:
    checked_at = datetime(2026, 9, 21, tzinfo=UTC)
    scope = TikTokDataValidationScope(
        tenant_id="tenant_a",
        market="US",
        store_resource_id="store_tenant_a",
        creator_scope_summary="US pilot creators",
        business_owner_user_id="admin_tenant_a",
        data_owner_user_id="member_tenant_a",
        status="active",
    )
    fields = [
        TikTokFieldContract(
            tenant_id="tenant_a",
            field_code=code,
            domain=code.split(".", 1)[0],
            label=code,
            data_type="string",
            owner_user_id="admin_tenant_a",
            business_key="record_id",
            freshness_sla_seconds=3600,
            missing_behavior="block_stage",
            sources_json=[_source(f"mock.{code}").model_dump(mode="json")],
            status="confirmed",
        )
        for code in (
            "sample.application_id",
            "sample.creator_id",
            "sample.product_id",
            "sample.status",
            "sample.applied_at",
            "sample.fulfillment_due_at",
            "order.order_id",
            "order.creator_id",
            "order.product_id",
            "order.status",
            "order.created_at",
            "order.completed_at",
            "logistics.order_id",
            "logistics.tracking_number",
            "logistics.status",
            "logistics.occurred_at",
            "video.video_id",
            "video.creator_id",
            "video.product_id",
            "video.published_at",
            "video.view_count",
            "video.like_count",
            "attribution.pid",
            "attribution.order_id",
            "attribution.window_start",
            "attribution.window_end",
            "gmv.order_id",
            "gmv.amount",
            "gmv.currency",
            "gmv.occurred_at",
        )
    ]
    from app.tiktok.data_validation import CAPABILITY_CATALOG, PROVIDER_CATALOG

    entries = [
        TikTokCapabilityEvidence(
            tenant_id="tenant_a",
            entry_code=item.code,
            entry_kind=item.entry_kind,
            platform_domain=item.platform_domain,
            action=item.action,
            direction=item.direction,
            evidence_level="E1",
            evidence_type="official_docs",
            status="blocked" if item.entry_kind == "capability" else "verified",
            decision="defer" if item.entry_kind == "provider_decision" else None,
            summary="Reviewed and recorded",
            evidence_ref="doc:review",
            checked_by_user_id="admin_tenant_a",
            checked_at=checked_at,
        )
        for item in (*CAPABILITY_CATALOG, *PROVIDER_CATALOG)
    ]
    run = TikTokDataValidationRun(
        tenant_id="tenant_a",
        catalog_version=DATA_VALIDATION_CATALOG_VERSION,
        dataset_digest="sha256:fixed",
        record_count=1,
        status="passed",
        started_by_user_id="admin_tenant_a",
    )
    return scope, fields, entries, run


def test_configured_workspace_is_ready_but_mock_never_makes_real_data_ready() -> None:
    scope, contracts, entries, passed_run = _configured_readiness_rows()
    readiness = evaluate_data_validation_readiness(
        scope=scope,
        field_contracts=contracts,
        evidence=entries,
        latest_run=passed_run,
        active_authorizations=[],
        now=datetime(2026, 9, 22, tzinfo=UTC),
        has_recorded_or_real_validation=False,
    )
    assert readiness.workbench_ready is True
    assert readiness.real_data_ready is False
    assert "recorded_or_real_validation_missing" in {item.code for item in readiness.blockers}


def test_e3_is_action_specific_and_requires_matching_unexpired_authorization() -> None:
    scope, contracts, entries, passed_run = _configured_readiness_rows()
    shop = next(item for item in entries if item.entry_code == "seller.shop.read")
    shop.evidence_level = "E3"
    shop.evidence_type = "real_account"
    shop.status = "verified"
    shop.subject_key = "seller-us"
    shop.resource_id = "store_tenant_a"
    shop.required_scope = "shop.read"
    shop.valid_until = datetime(2026, 10, 1, tzinfo=UTC)
    authorization = ExternalAuthorization(
        tenant_id="tenant_a",
        authorization_type="seller",
        subject_id="seller-us",
        resource_id="store_tenant_a",
        scopes_json=["shop.read"],
        status="active",
        expires_at=datetime(2026, 10, 1, tzinfo=UTC),
    )

    readiness = evaluate_data_validation_readiness(
        scope=scope,
        field_contracts=contracts,
        evidence=entries,
        latest_run=passed_run,
        active_authorizations=[authorization],
        now=datetime(2026, 9, 22, tzinfo=UTC),
        has_recorded_or_real_validation=False,
    )
    blockers = {(item.code, item.target_code) for item in readiness.blockers}
    assert ("capability_e3_missing", "affiliate.orders.read") in blockers
    assert ("capability_e3_missing", "seller.shop.read") not in blockers

    shop.valid_until = datetime(2026, 9, 21, tzinfo=UTC)
    expired = evaluate_data_validation_readiness(
        scope=scope,
        field_contracts=contracts,
        evidence=entries,
        latest_run=passed_run,
        active_authorizations=[authorization],
        now=datetime(2026, 9, 22, tzinfo=UTC),
        has_recorded_or_real_validation=False,
    )
    assert ("capability_evidence_expired", "seller.shop.read") in {
        (item.code, item.target_code) for item in expired.blockers
    }


@pytest.mark.parametrize(
    ("subject", "resource", "scope_name", "authorization", "expected_code"),
    (
        ("wrong", "store_tenant_a", "shop.read", True, "authorization_missing"),
        ("seller-us", "wrong-store", "shop.read", True, "capability_resource_mismatch"),
        ("seller-us", "store_tenant_a", "wrong.scope", True, "authorization_missing"),
        ("seller-us", "store_tenant_a", "shop.read", False, "authorization_missing"),
    ),
)
def test_real_gate_rejects_subject_resource_scope_and_authorization_mismatch(
    subject: str,
    resource: str,
    scope_name: str,
    authorization: bool,
    expected_code: str,
) -> None:
    scope, contracts, entries, passed_run = _configured_readiness_rows()
    shop = next(item for item in entries if item.entry_code == "seller.shop.read")
    shop.evidence_level = "E3"
    shop.evidence_type = "real_account"
    shop.status = "verified"
    shop.subject_key = subject
    shop.resource_id = resource
    shop.required_scope = scope_name
    shop.valid_until = datetime(2026, 10, 1, tzinfo=UTC)
    auth_rows = (
        [
            ExternalAuthorization(
                tenant_id="tenant_a",
                authorization_type="seller",
                subject_id="seller-us",
                resource_id="store_tenant_a",
                scopes_json=["shop.read"],
                status="active",
                expires_at=datetime(2026, 10, 1, tzinfo=UTC),
            )
        ]
        if authorization
        else []
    )
    readiness = evaluate_data_validation_readiness(
        scope=scope,
        field_contracts=contracts,
        evidence=entries,
        latest_run=passed_run,
        active_authorizations=auth_rows,
        now=datetime(2026, 9, 22, tzinfo=UTC),
        has_recorded_or_real_validation=False,
    )
    assert (expected_code, "seller.shop.read") in {
        (item.code, item.target_code) for item in readiness.blockers
    }


def _confirmed_field_contracts() -> list[TikTokFieldContract]:
    return [
        TikTokFieldContract(
            tenant_id="tenant_a",
            field_code=item.code,
            domain=item.domain,
            label=item.label,
            data_type=item.data_type,
            owner_user_id="admin_tenant_a",
            business_key=item.business_key,
            freshness_sla_seconds=86400 * 7,
            missing_behavior="block_stage",
            sources_json=[_source(f"mock.{item.code}").model_dump(mode="json")],
            status="confirmed",
        )
        for item in FIELD_CATALOG
    ]


def test_mock_validation_detects_required_quality_failures_without_raw_values() -> None:
    contracts = _confirmed_field_contracts()
    dataset = deepcopy(MOCK_DATASET)
    dataset["orders"].append(deepcopy(dataset["orders"][0]))
    dataset["gmv"][0].pop("currency")
    dataset["videos"][0]["product_id"] = "unknown-product"

    result = validate_mock_dataset(
        contracts=contracts,
        dataset=dataset,
        validation_clock=MOCK_VALIDATION_CLOCK,
    )

    codes = {issue.code for issue in result.issues}
    assert {"duplicate_business_key", "required_field_missing", "pid_product_conflict"} <= codes
    serialized = result.model_dump_json()
    assert "unknown-product" not in serialized
    assert "mock-order-001" not in serialized


def test_mock_validation_is_deterministic_for_same_catalog_and_fixture() -> None:
    first = validate_mock_dataset(
        contracts=_confirmed_field_contracts(),
        dataset=MOCK_DATASET,
        validation_clock=MOCK_VALIDATION_CLOCK,
    )
    second = validate_mock_dataset(
        contracts=_confirmed_field_contracts(),
        dataset=MOCK_DATASET,
        validation_clock=MOCK_VALIDATION_CLOCK,
    )
    assert first.status == "passed"
    assert first.dataset_digest == second.dataset_digest
    assert first.checks == second.checks
    assert first.issues == second.issues


@pytest.mark.parametrize(
    ("case", "expected_code"),
    (
        ("stale", "stale_record"),
        ("amount", "invalid_amount"),
        ("currency", "invalid_currency"),
        ("window", "inverted_attribution_window"),
        ("relationship", "broken_relationship"),
        ("missing_key", "business_key_missing"),
        ("denied_source", "selected_source_denied"),
    ),
)
def test_mock_validation_detects_each_guardrail(case: str, expected_code: str) -> None:
    contracts = _confirmed_field_contracts()
    dataset = deepcopy(MOCK_DATASET)
    if case == "stale":
        dataset["orders"][0]["observed_at"] = "2026-01-01T00:00:00Z"
    elif case == "amount":
        dataset["gmv"][0]["amount"] = "-1.00"
    elif case == "currency":
        dataset["gmv"][0]["currency"] = "usd"
    elif case == "window":
        dataset["attribution"][0]["window_start"] = "2026-09-23T00:00:00Z"
    elif case == "relationship":
        dataset["logistics"][0]["order_id"] = "missing-order"
    elif case == "missing_key":
        dataset["orders"][0].pop("order_id")
    else:
        contracts[0].sources_json.append(
            _source(
                "vendor.sample.application",
                usage="real",
                decision="use",
                authorization_state="denied",
            ).model_dump(mode="json")
        )

    result = validate_mock_dataset(
        contracts=contracts,
        dataset=dataset,
        validation_clock=MOCK_VALIDATION_CLOCK,
    )
    assert expected_code in {issue.code for issue in result.issues}


def _fully_configured_workspace(db: Session, tenant_id: str) -> User:
    admin = _seed_tenant(db, tenant_id)
    bootstrap_data_validation_workspace(db, admin)
    update_data_validation_scope(
        db,
        admin,
        TikTokDataValidationScopeUpdate(
            revision=0,
            store_resource_id=f"store_{tenant_id}",
            creator_scope_summary="US pilot creators",
            business_owner_user_id=f"admin_{tenant_id}",
            data_owner_user_id=f"member_{tenant_id}",
            status="active",
        ),
    )
    for item in FIELD_CATALOG:
        update_field_contract(
            db,
            admin,
            item.code,
            TikTokFieldContractUpdate(
                revision=1,
                owner_user_id=admin.id,
                business_key=item.business_key,
                freshness_sla_seconds=86400 * 7,
                missing_behavior="block_stage",
                sources=[_source(f"mock.{item.code}")],
                status="confirmed",
            ),
        )
    checked_at = datetime(2026, 9, 21, tzinfo=UTC)
    for item in CAPABILITY_CATALOG:
        update_capability_evidence(
            db,
            admin,
            item.code,
            TikTokCapabilityEvidenceUpdate(
                revision=1,
                subject_key="global",
                evidence_level="E1",
                evidence_type="official_docs",
                status="blocked",
                summary="Reviewed and unavailable for the pilot",
                evidence_ref="doc:review",
                checked_by_user_id=admin.id,
                checked_at=checked_at,
            ),
        )
    for item in PROVIDER_CATALOG:
        update_capability_evidence(
            db,
            admin,
            item.code,
            TikTokCapabilityEvidenceUpdate(
                revision=1,
                subject_key="global",
                evidence_level="E1",
                evidence_type="contract",
                status="verified",
                decision="defer",
                summary="Reviewed and deferred",
                evidence_ref="contract:review",
                checked_by_user_id=admin.id,
                checked_at=checked_at,
            ),
        )
    return admin


def test_mock_runs_are_appended_and_never_mark_real_data_ready() -> None:
    with _session() as db:
        admin = _fully_configured_workspace(db, "tenant_a")
        first = run_mock_data_validation(db, admin)
        second = run_mock_data_validation(db, admin)
        runs = db.exec(
            select(TikTokDataValidationRun)
            .where(TikTokDataValidationRun.tenant_id == "tenant_a")
            .order_by(TikTokDataValidationRun.created_at)
        ).all()
        assert len(runs) == 2
        assert first.dataset_digest == second.dataset_digest
        assert first.status == second.status == "passed"
        assert first.real_data_ready_snapshot is False
        assert second.real_data_ready_snapshot is False
        serialized = json.dumps(
            [{"checks": row.checks_json, "issues": row.issues_json} for row in runs],
            ensure_ascii=False,
        )
        assert "mock-order-001" not in serialized
        assert "mock-creator-001" not in serialized
        assert get_data_validation_workspace(db, admin).readiness.workbench_ready is True


def test_member_cannot_insert_mock_run() -> None:
    with _session() as db:
        _fully_configured_workspace(db, "tenant_a")
        member = db.get(User, "member_tenant_a")
        assert member is not None
        before = len(db.exec(select(TikTokDataValidationRun)).all())
        with pytest.raises(HTTPException) as denied:
            run_mock_data_validation(db, member)
        assert denied.value.status_code == 403
        assert len(db.exec(select(TikTokDataValidationRun)).all()) == before
