from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.api.advertising as advertising_api
from app.advertising.pdca_service import (
    create_pdca_search_term_run,
    list_pdca_search_term_runs,
)
from app.advertising.schema import (
    AdvertisingActionRequest,
    AdvertisingRecommendationCreate,
    ExecutionAutomationPolicyUpsert,
)
from app.advertising.service import (
    advertising_overview,
    create_advertising_recommendation,
    list_advertising_effect_followups,
    list_automation_usage,
    request_advertising_action,
    upsert_execution_automation_policy,
)
from app.business_execution.service import reconcile_execution
from app.business_execution.worker import run_execution_cycle
from app.business_resources.schema import (
    BusinessResourceCreate,
    ExecutionReconciliationReport,
)
from app.business_resources.service import create_resource, decide_action_request
from app.config import get_settings
from app.db import get_session
from app.db.models import (
    AdvertisingEffectFollowUp,
    BusinessActionExecution,
    HighRiskActionRequest,
    PdcaAction,
    PdcaFactSearchTerm,
    PdcaSearchTermRun,
    Tenant,
    User,
    WorkTask,
)
from app.security.auth import create_access_token


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _user(user_id: str, role: str, *, tenant_id: str = "tenant_demo") -> User:
    return User(
        id=user_id,
        tenant_id=tenant_id,
        username=user_id,
        role="member",
        business_role=role,
        password_hash="disabled",
    )


@pytest.fixture
def setup():
    engine = _engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        users = {
            "advertising": _user("advertising", "advertising_inspection_specialist"),
            "supervisor": _user("supervisor", "operations_supervisor"),
            "listing": _user("listing", "listing_compliance_specialist"),
            "designer": _user("designer", "designer"),
            "procurement": _user("procurement", "procurement_specialist"),
            "other": _user("other", "operations_supervisor", tenant_id="tenant_other"),
        }
        db.add_all(
            [
                Tenant(id="tenant_demo", name="Demo"),
                Tenant(id="tenant_other", name="Other"),
                *users.values(),
            ]
        )
        db.commit()
        account = create_resource(
            db,
            request=BusinessResourceCreate(
                tenant_id="tenant_demo",
                resource_type="ad_account",
                code="ADS-US",
                name="Amazon Ads US",
            ),
            user=users["supervisor"],
        )
        store = create_resource(
            db,
            request=BusinessResourceCreate(
                tenant_id="tenant_demo",
                resource_type="store",
                code="AMZ-US",
                name="Amazon US",
            ),
            user=users["supervisor"],
        )
        yield engine, db, users, {"account": account.id, "store": store.id}


def _request(
    resources: dict[str, str],
    *,
    key: str,
    campaign_id: str = "CAMPAIGN-1001",
    low_inventory: bool = False,
) -> AdvertisingRecommendationCreate:
    return AdvertisingRecommendationCreate(
        tenant_id="tenant_demo",
        recommendation_key=key,
        ad_account_resource_id=resources["account"],
        store_resource_id=resources["store"],
        campaign_id=campaign_id,
        product_key="PRODUCT-1001",
        spend=120,
        attributed_sales=600,
        impressions=100_000,
        clicks=250,
        orders=10,
        price=40,
        profit_per_order=12,
        available_units=100 if low_inventory else 1000,
        inbound_units=0,
        forecast_daily_sales=10,
        reserve_stock_units=50,
        minimum_days_of_cover=21,
        promotion_active=False,
        minimum_ctr=0.003,
        minimum_conversion_rate=0.06,
        proposed_action_type="change_daily_budget",
        proposed_action_payload={
            "daily_budget": 50,
            "previous_daily_budget": 40,
            "currency": "USD",
        },
        recommendation_note="Reduce spend volatility while preserving profitable traffic.",
    )


def _search_term_csv(*, extra_spend: str = "0") -> bytes:
    return (
        "Date,Campaign Name,Campaign ID,Ad Group Name,Ad Group ID,Targeting,Match Type,"
        "Customer Search Term,Impressions,Clicks,Spend,Sales,Orders\n"
        "2026-09-01,Synthetic Campaign,CAMPAIGN-1,Synthetic Group,ADGROUP-1,"
        "synthetic target,Broad,synthetic query,100,5,5.000001,0,0\n"
        "2026-09-02,Synthetic Campaign,CAMPAIGN-1,Synthetic Group,ADGROUP-1,"
        "synthetic target,Broad,SYNTHETIC   QUERY,120,4,5.000002,0,0\n"
        "2026-09-02,Synthetic Campaign,CAMPAIGN-1,Synthetic Group,ADGROUP-2,"
        f"winner target,Phrase,synthetic winner,200,10,{Decimal(10) + Decimal(extra_spend)},"
        "100,2\n"
    ).encode()


def _renamed_grain_csv() -> bytes:
    return (
        "Date,Campaign Name,Campaign ID,Ad Group Name,Ad Group ID,Targeting,Match Type,"
        "Customer Search Term,Impressions,Clicks,Spend,Sales,Orders\n"
        "2026-09-01,Old Name,CAMPAIGN-1,Old Group,ADGROUP-1,synthetic target,Broad,"
        "synthetic query,10,1,1,0,0\n"
        "2026-09-02,New Name,CAMPAIGN-1,New Group,ADGROUP-1,synthetic target,Broad,"
        "synthetic query,20,2,2,0,0\n"
    ).encode()


def _duplicate_orders_header_csv() -> bytes:
    lines = _search_term_csv().decode().splitlines()
    return ("\n".join([f"{lines[0]},Orders", *(f"{line},999" for line in lines[1:])])).encode()


def test_ad_inspection_blocks_inventory_and_routes_cross_role_tasks(setup) -> None:
    _, db, users, resources = setup
    recommendation = create_advertising_recommendation(
        db,
        request=_request(resources, key="AD-REC-BLOCK-001", low_inventory=True),
        user=users["advertising"],
    )
    assert recommendation.status == "blocked"
    assert recommendation.metrics["acos"] == 0.2
    assert recommendation.metrics["break_even_acos"] == 0.3
    assert {item["code"] for item in recommendation.findings} >= {
        "inventory_cover_below_minimum",
        "ctr_below_minimum",
        "conversion_below_minimum",
    }
    roles = {
        db.get(WorkTask, task_id).owner_business_role for task_id in recommendation.linked_task_ids
    }
    assert roles == {"designer", "listing_compliance_specialist", "procurement_specialist"}
    with pytest.raises(HTTPException) as blocked_action:
        request_advertising_action(
            db,
            recommendation_id=recommendation.id,
            request=AdvertisingActionRequest(
                tenant_id="tenant_demo",
                expected_version=recommendation.version,
                summary="Blocked inventory must prevent this budget action",
            ),
            user=users["advertising"],
        )
    assert blocked_action.value.status_code == 409
    assert db.exec(select(HighRiskActionRequest)).all() == []


def test_ad_action_requires_approval_then_creates_7_14_30_day_reviews(setup) -> None:
    engine, db, users, resources = setup
    recommendation = create_advertising_recommendation(
        db,
        request=_request(resources, key="AD-REC-READY-001"),
        user=users["advertising"],
    )
    assert recommendation.status == "ready"
    requested = request_advertising_action(
        db,
        recommendation_id=recommendation.id,
        request=AdvertisingActionRequest(
            tenant_id="tenant_demo",
            expected_version=recommendation.version,
            summary="Change CAMPAIGN-1001 daily budget after independent review",
        ),
        user=users["advertising"],
    )
    assert requested.status == "action_pending"
    assert db.exec(select(BusinessActionExecution)).all() == []
    approved = decide_action_request(
        db,
        tenant_id="tenant_demo",
        request_id=requested.approval_request_id,
        decision="approved",
        reason="Profit, price, inventory and promotion constraints reviewed.",
        user=users["supervisor"],
    )
    assert approved.status == "approved"
    execution = db.exec(select(BusinessActionExecution)).one()
    assert execution.status == "queued"
    assert run_execution_cycle(db_engine=engine, settings=get_settings()) == 1
    db.expire_all()
    execution = db.get(BusinessActionExecution, execution.id)
    assert execution.status == "succeeded"
    followups = list_advertising_effect_followups(
        db, tenant_id="tenant_demo", user=users["advertising"]
    )
    assert [item.horizon_days for item in followups] == [7, 14, 30]
    assert all(item.baseline["acos"] == 0.2 for item in followups)
    assert len(db.exec(select(AdvertisingEffectFollowUp)).all()) == 3
    assert (
        advertising_overview(
            db, tenant_id="tenant_demo", user=users["advertising"]
        ).actions_waiting_approval
        == 0
    )


def test_automation_policy_enforces_kill_switch_limits_and_approval(setup) -> None:
    _, db, users, resources = setup
    with pytest.raises(HTTPException) as bypass:
        upsert_execution_automation_policy(
            db,
            request=ExecutionAutomationPolicyUpsert(
                tenant_id="tenant_demo",
                resource_id=resources["account"],
                action_type="change_daily_budget",
                status="active",
                rollout_percent=100,
                max_single_value=100,
                max_daily_value=200,
                max_risk_level="medium",
                approval_required=False,
                kill_switch_engaged=False,
            ),
            user=users["supervisor"],
        )
    assert bypass.value.status_code == 422

    policy = upsert_execution_automation_policy(
        db,
        request=ExecutionAutomationPolicyUpsert(
            tenant_id="tenant_demo",
            resource_id=resources["account"],
            action_type="change_daily_budget",
            status="active",
            rollout_percent=100,
            max_single_value=100,
            max_daily_value=200,
            max_risk_level="medium",
            approval_required=True,
            kill_switch_engaged=True,
        ),
        user=users["supervisor"],
    )
    recommendation = create_advertising_recommendation(
        db,
        request=_request(resources, key="AD-REC-KILL-001"),
        user=users["advertising"],
    )
    requested = request_advertising_action(
        db,
        recommendation_id=recommendation.id,
        request=AdvertisingActionRequest(
            tenant_id="tenant_demo",
            expected_version=recommendation.version,
            summary="Approved action remains stopped by the emergency kill switch",
        ),
        user=users["advertising"],
    )
    decide_action_request(
        db,
        tenant_id="tenant_demo",
        request_id=requested.approval_request_id,
        decision="approved",
        reason="Independent approval does not override the kill switch.",
        user=users["supervisor"],
    )
    execution = db.exec(select(BusinessActionExecution)).one()
    assert execution.status == "manual_resolution_required"
    assert execution.last_error_code == "automation_policy_blocked"
    usage = list_automation_usage(db, tenant_id="tenant_demo", user=users["supervisor"])
    assert usage[0].decision == "blocked"
    assert usage[0].reason == "kill_switch_engaged"
    assert usage[0].policy_revision == policy.revision


def test_active_policy_allows_first_approved_action_then_enforces_daily_limit(setup) -> None:
    _, db, users, resources = setup
    upsert_execution_automation_policy(
        db,
        request=ExecutionAutomationPolicyUpsert(
            tenant_id="tenant_demo",
            resource_id=resources["account"],
            action_type="change_daily_budget",
            status="active",
            rollout_percent=100,
            max_single_value=60,
            max_daily_value=75,
            max_risk_level="medium",
            approval_required=True,
            kill_switch_engaged=False,
        ),
        user=users["supervisor"],
    )

    execution_statuses = []
    for sequence in (1, 2):
        recommendation = create_advertising_recommendation(
            db,
            request=_request(
                resources,
                key=f"AD-REC-LIMIT-00{sequence}",
                campaign_id=f"CAMPAIGN-LIMIT-{sequence}",
            ),
            user=users["advertising"],
        )
        requested = request_advertising_action(
            db,
            recommendation_id=recommendation.id,
            request=AdvertisingActionRequest(
                tenant_id="tenant_demo",
                expected_version=recommendation.version,
                summary=f"Approve bounded budget action number {sequence}",
            ),
            user=users["advertising"],
        )
        decide_action_request(
            db,
            tenant_id="tenant_demo",
            request_id=requested.approval_request_id,
            decision="approved",
            reason="Independent reviewer confirmed the bounded action evidence.",
            user=users["supervisor"],
        )
        execution = db.exec(
            select(BusinessActionExecution).where(
                BusinessActionExecution.request_id == requested.approval_request_id
            )
        ).one()
        execution_statuses.append(execution.status)

    assert execution_statuses == ["queued", "manual_resolution_required"]
    decisions = list_automation_usage(db, tenant_id="tenant_demo", user=users["supervisor"])
    assert [(item.decision, item.reason) for item in reversed(decisions)] == [
        ("allowed", "allowed"),
        ("blocked", "daily_action_limit_exceeded"),
    ]


def test_reconciliation_fails_closed_on_idempotency_mismatch(setup) -> None:
    _, db, users, resources = setup
    recommendation = create_advertising_recommendation(
        db,
        request=_request(resources, key="AD-REC-RECON-001"),
        user=users["advertising"],
    )
    requested = request_advertising_action(
        db,
        recommendation_id=recommendation.id,
        request=AdvertisingActionRequest(
            tenant_id="tenant_demo",
            expected_version=recommendation.version,
            summary="Submit a controlled budget change for reconciliation testing",
        ),
        user=users["advertising"],
    )
    decide_action_request(
        db,
        tenant_id="tenant_demo",
        request_id=requested.approval_request_id,
        decision="approved",
        reason="Constraint evidence reviewed.",
        user=users["supervisor"],
    )
    execution = db.exec(select(BusinessActionExecution)).one()
    reconciled = reconcile_execution(
        db,
        execution_id=execution.id,
        report=ExecutionReconciliationReport(
            tenant_id="tenant_demo",
            observed_status="succeeded",
            observed_idempotency_key="wrong-idempotency-key",
            external_operation_id="remote-123",
            receipt_digest="sha256:receipt",
            note="Adapter observation intentionally contains a mismatched key.",
        ),
        user=users["supervisor"],
    )
    assert reconciled.status == "manual_resolution_required"
    assert reconciled.last_error_code == "reconciliation_identity_mismatch"
    assert reconciled.events[-1].event_type == "reconciliation_mismatch"


def test_advertising_bola_is_rejected(setup) -> None:
    _, db, users, resources = setup
    with pytest.raises(HTTPException) as other_tenant:
        create_advertising_recommendation(
            db,
            request=_request(resources, key="AD-REC-BOLA-001"),
            user=users["other"],
        )
    assert other_tenant.value.status_code == 403


def test_pdca_csv_aggregates_decimal_facts_and_creates_advice_only_actions(setup) -> None:
    _, db, users, resources = setup
    result = create_pdca_search_term_run(
        db,
        tenant_id="tenant_demo",
        ad_account_resource_id=resources["account"],
        store_resource_id=resources["store"],
        idempotency_key="pdca-contract-001",
        filename="synthetic-search-terms.csv",
        content_type="text/csv",
        data=_search_term_csv(),
        target_acos=Decimal("0.30"),
        currency="USD",
        user=users["advertising"],
    )

    assert result.mode == "rules_only"
    assert result.attempt == 1
    assert result.external_execution_allowed is False
    assert result.source_label == "local source file"
    assert result.source_row_count == 3
    assert result.fact_count == 2
    assert result.action_count == 2
    assert result.summary["spend"] == "20.000003"
    assert result.summary["sales"] == "100"
    assert result.summary["acos"] == {"value": "0.2", "reason": None}
    assert {item.action_type for item in result.top_actions} == {
        "manual_review",
        "convert_exact",
    }
    assert all(item.external_execution_allowed is False for item in result.top_actions)
    assert all("did not execute a write" in item.execution_hint for item in result.top_actions)

    facts = db.exec(select(PdcaFactSearchTerm)).all()
    zero_order = next(item for item in facts if item.search_term_norm == "synthetic query")
    assert zero_order.clicks == 9
    assert zero_order.spend == Decimal("10.000003")
    assert zero_order.source_row_refs_json == [2, 3]
    assert zero_order.metric_snapshot_json["acos"] == {
        "value": None,
        "reason": "zero_sales",
    }
    assert db.exec(select(HighRiskActionRequest)).all() == []
    assert db.exec(select(BusinessActionExecution)).all() == []


def test_pdca_idempotency_replays_same_snapshot_and_rejects_collision(setup) -> None:
    _, db, users, resources = setup
    request = {
        "tenant_id": "tenant_demo",
        "ad_account_resource_id": resources["account"],
        "store_resource_id": resources["store"],
        "idempotency_key": "pdca-contract-replay",
        "filename": "synthetic-search-terms.csv",
        "content_type": "text/csv",
        "target_acos": Decimal("0.30"),
        "currency": "USD",
        "user": users["advertising"],
    }
    first = create_pdca_search_term_run(db, data=_search_term_csv(), **request)
    replay = create_pdca_search_term_run(db, data=_search_term_csv(), **request)
    replay_with_new_key = create_pdca_search_term_run(
        db,
        data=_search_term_csv(),
        **{**request, "idempotency_key": "pdca-contract-new-key"},
    )

    assert replay.id == first.id
    assert replay_with_new_key.id == first.id
    assert first.attempt == 1
    assert len(db.exec(select(PdcaSearchTermRun)).all()) == 1
    assert len(db.exec(select(PdcaFactSearchTerm)).all()) == 2
    assert len(db.exec(select(PdcaAction)).all()) == 2

    with pytest.raises(HTTPException) as collision:
        create_pdca_search_term_run(db, data=_search_term_csv(extra_spend="1"), **request)
    assert collision.value.status_code == 409
    assert len(db.exec(select(PdcaSearchTermRun)).all()) == 1

    rerun = create_pdca_search_term_run(
        db,
        data=_search_term_csv(),
        **{
            **request,
            "idempotency_key": "pdca-contract-attempt-2",
            "explicit_rerun": True,
        },
    )
    assert rerun.id != first.id
    assert rerun.attempt == 2
    assert len(db.exec(select(PdcaSearchTermRun)).all()) == 2


def test_pdca_missing_mapping_and_cross_tenant_are_rejected(setup) -> None:
    _, db, users, resources = setup
    missing_orders = b"\n".join(
        line.rsplit(b",", 1)[0] for line in _search_term_csv().splitlines()
    )
    with pytest.raises(HTTPException) as mapping_error:
        create_pdca_search_term_run(
            db,
            tenant_id="tenant_demo",
            ad_account_resource_id=resources["account"],
            store_resource_id=resources["store"],
            idempotency_key="pdca-contract-missing",
            filename="synthetic-search-terms.csv",
            content_type="text/csv",
            data=missing_orders,
            target_acos=Decimal("0.30"),
            currency="USD",
            user=users["advertising"],
        )
    assert mapping_error.value.status_code == 422
    assert "missing required fields: orders" in str(mapping_error.value.detail)

    with pytest.raises(HTTPException) as ambiguous_error:
        create_pdca_search_term_run(
            db,
            tenant_id="tenant_demo",
            ad_account_resource_id=resources["account"],
            store_resource_id=resources["store"],
            idempotency_key="pdca-contract-ambiguous",
            filename="synthetic-search-terms.csv",
            content_type="text/csv",
            data=_duplicate_orders_header_csv(),
            target_acos=Decimal("0.30"),
            currency="USD",
            user=users["advertising"],
        )
    assert ambiguous_error.value.status_code == 422
    assert "ambiguous fields: orders" in str(ambiguous_error.value.detail)

    with pytest.raises(HTTPException) as other_tenant:
        list_pdca_search_term_runs(
            db,
            tenant_id="tenant_demo",
            ad_account_resource_id=resources["account"],
            store_resource_id=resources["store"],
            user=users["other"],
        )
    assert other_tenant.value.status_code == 403


def test_pdca_uses_stable_ids_for_grain_and_filters_history_by_resource(setup) -> None:
    _, db, users, resources = setup
    first = create_pdca_search_term_run(
        db,
        tenant_id="tenant_demo",
        ad_account_resource_id=resources["account"],
        store_resource_id=resources["store"],
        idempotency_key="pdca-stable-grain-001",
        filename="synthetic-search-terms.csv",
        content_type="text/csv",
        data=_renamed_grain_csv(),
        target_acos=Decimal("0.30"),
        currency="USD",
        user=users["advertising"],
    )
    assert first.fact_count == 1
    fact = db.exec(select(PdcaFactSearchTerm)).one()
    assert fact.clicks == 3
    assert fact.spend == Decimal("3.000000")

    second_account = create_resource(
        db,
        request=BusinessResourceCreate(
            tenant_id="tenant_demo",
            resource_type="ad_account",
            code="ADS-EU",
            name="Amazon Ads EU",
        ),
        user=users["supervisor"],
    )
    create_pdca_search_term_run(
        db,
        tenant_id="tenant_demo",
        ad_account_resource_id=second_account.id,
        store_resource_id=resources["store"],
        idempotency_key="pdca-second-account-001",
        filename="synthetic-search-terms.csv",
        content_type="text/csv",
        data=_search_term_csv(),
        target_acos=Decimal("0.30"),
        currency="USD",
        user=users["advertising"],
    )
    listed = list_pdca_search_term_runs(
        db,
        tenant_id="tenant_demo",
        ad_account_resource_id=resources["account"],
        store_resource_id=resources["store"],
        user=users["advertising"],
    )
    assert [item.id for item in listed] == [first.id]


def test_pdca_multipart_api_contract_requires_idempotency_and_returns_rules_only(setup) -> None:
    engine, _, users, resources = setup
    app = FastAPI()
    app.include_router(advertising_api.router)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    auth = {"Authorization": f"Bearer {create_access_token(users['advertising'])}"}
    path = "/api/enterprise/work-tasks/advertising/pdca/search-term-runs"
    params = {
        "tenant_id": "tenant_demo",
        "ad_account_resource_id": resources["account"],
        "store_resource_id": resources["store"],
        "target_acos": "0.30",
        "currency": "USD",
    }

    missing_key = client.post(
        path,
        params=params,
        headers=auth,
        files={"file": ("synthetic.csv", _search_term_csv(), "text/csv")},
    )
    assert missing_key.status_code == 422

    created = client.post(
        path,
        params=params,
        headers={**auth, "Idempotency-Key": "pdca-api-contract-001"},
        files={"file": ("synthetic.csv", _search_term_csv(), "text/csv")},
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["mode"] == "rules_only"
    assert payload["attempt"] == 1
    assert payload["source_label"] == "local source file"
    assert payload["external_execution_allowed"] is False
    assert payload["mapping"]["search_term"] == "Customer Search Term"
    assert all(item["status"] == "suggested" for item in payload["top_actions"])

    missing_scope = client.get(path, params={"tenant_id": "tenant_demo"}, headers=auth)
    assert missing_scope.status_code == 422

    listed = client.get(path, params=params, headers=auth)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [payload["id"]]


def test_pdca_database_and_postgres_migration_forbid_execution(setup) -> None:
    _, db, users, resources = setup
    create_pdca_search_term_run(
        db,
        tenant_id="tenant_demo",
        ad_account_resource_id=resources["account"],
        store_resource_id=resources["store"],
        idempotency_key="pdca-db-gate-001",
        filename="synthetic-search-terms.csv",
        content_type="text/csv",
        data=_search_term_csv(),
        target_acos=Decimal("0.30"),
        currency="USD",
        user=users["advertising"],
    )
    action = db.exec(select(PdcaAction)).first()
    assert action is not None
    action.external_execution_allowed = True
    db.add(action)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    migration = (
        Path(__file__).parents[1]
        / "migrations"
        / "20260908_pdca_search_term_rules_v1.sql"
    ).read_text(encoding="utf-8")
    for table in ("pdca_search_term_runs", "pdca_fact_search_terms", "pdca_actions"):
        assert f"CREATE TABLE IF NOT EXISTS public.{table}" in migration
        assert f"'{table}'" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "pdca_actions_no_execution_check" in migration
    assert "external_execution_allowed = false" in migration
    assert "GRANT SELECT, INSERT" in migration
