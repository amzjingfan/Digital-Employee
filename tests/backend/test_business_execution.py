from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.business_execution.connectors import AmazonAdsConnector, GenericBusinessHttpConnector
from app.business_execution.contracts import ConnectorOutcome, ExecutionContext
from app.business_execution.service import (
    request_compensation,
    retry_execution,
    stage_approved_execution,
)
from app.business_execution.worker import run_execution_cycle
from app.business_resources.schema import (
    BusinessResourceCreate,
    BusinessResourceUpdate,
    HighRiskActionCreate,
)
from app.business_resources.service import (
    create_action_request,
    create_resource,
    decide_action_request,
    update_resource,
)
from app.config import Settings
from app.db.models import (
    BusinessActionExecution,
    BusinessActionExecutionEvent,
    HighRiskActionEvent,
    HighRiskActionRequest,
    Tenant,
    User,
)


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _settings(**overrides) -> Settings:
    values = {
        "business_execution_enabled": True,
        "business_execution_mode": "sandbox",
        "business_execution_tenant_ids": "tenant_demo",
        "business_execution_poll_seconds": 0.01,
        "business_execution_max_attempts": 3,
    }
    values.update(overrides)
    return Settings(**values)


def _user(user_id: str, role: str) -> User:
    return User(
        id=user_id,
        tenant_id="tenant_demo",
        username=user_id,
        role="member",
        business_role=role,
        password_hash="disabled",
    )


@pytest.fixture
def setup(monkeypatch):
    db_engine = _engine()
    SQLModel.metadata.create_all(db_engine)
    settings = _settings()
    monkeypatch.setattr("app.business_execution.service.get_settings", lambda: settings)
    with Session(db_engine) as db:
        db.add(Tenant(id="tenant_demo", name="Demo"))
        requester = _user("listing", "listing_compliance_specialist")
        supervisor = _user("supervisor", "operations_supervisor")
        second = _user("supervisor-2", "operations_supervisor")
        db.add(requester)
        db.add(supervisor)
        db.add(second)
        db.commit()
        resource = create_resource(
            db,
            request=BusinessResourceCreate(
                tenant_id="tenant_demo",
                resource_type="store",
                code="STORE-US",
                name="美国店铺",
            ),
            user=supervisor,
        )
        yield db_engine, settings, requester, supervisor, second, resource


def _approve_listing(db_engine, requester, supervisor, resource, *, simulate_outcome=""):
    with Session(db_engine) as db:
        payload = {
            "listing_id": "SKU-100",
            "marketplace": "Amazon US",
            "product_type": "PRODUCT",
            "attributes": {"item_name": [{"value": "Demo"}]},
        }
        if simulate_outcome:
            payload["simulate_outcome"] = simulate_outcome
        action = create_action_request(
            db,
            request=HighRiskActionCreate(
                tenant_id="tenant_demo",
                resource_id=resource.id,
                action_type="publish_listing",
                summary="发布沙箱 Listing 并验证执行回执",
                payload=payload,
            ),
            user=requester,
        )
        return decide_action_request(
            db,
            tenant_id="tenant_demo",
            request_id=action.id,
            decision="approved",
            reason="合规材料完整，批准沙箱执行",
            user=supervisor,
        )


def test_approval_stages_one_execution_and_sandbox_worker_records_receipt(setup) -> None:
    db_engine, settings, requester, supervisor, _, resource = setup
    approved = _approve_listing(db_engine, requester, supervisor, resource)
    assert approved.execution is not None
    assert approved.execution.status == "queued"

    assert run_execution_cycle(db_engine=db_engine, settings=settings) == 1
    with Session(db_engine) as db:
        execution = db.exec(
            select(BusinessActionExecution).where(BusinessActionExecution.request_id == approved.id)
        ).one()
        assert execution.status == "succeeded"
        assert execution.attempt_count == 1
        assert execution.receipt_json["provider"] == "staffdeck-sandbox"
        assert execution.external_operation_id == f"sandbox-{execution.id}"
        assert [
            event.event_type
            for event in db.exec(
                select(BusinessActionExecutionEvent)
                .where(BusinessActionExecutionEvent.execution_id == execution.id)
                .order_by(BusinessActionExecutionEvent.occurred_at)
            ).all()
        ] == ["execution_staged", "execution_started", "execution_succeeded"]

        duplicate = stage_approved_execution(
            db,
            _action_row(db, approved.id),
            settings=settings,
        )
        assert duplicate.id == execution.id


def test_retryable_failure_reuses_same_execution_and_then_succeeds(setup) -> None:
    db_engine, settings, requester, supervisor, _, resource = setup
    approved = _approve_listing(
        db_engine,
        requester,
        supervisor,
        resource,
        simulate_outcome="retryable_once",
    )
    assert run_execution_cycle(db_engine=db_engine, settings=settings) == 2
    with Session(db_engine) as db:
        execution = db.exec(
            select(BusinessActionExecution).where(BusinessActionExecution.request_id == approved.id)
        ).one()
        assert execution.status == "succeeded"
        assert execution.attempt_count == 2
        events = db.exec(
            select(BusinessActionExecutionEvent).where(
                BusinessActionExecutionEvent.execution_id == execution.id
            )
        ).all()
        assert any(event.event_type == "execution_retry_scheduled" for event in events)


def test_ambiguous_remote_outcome_fails_closed_for_manual_resolution(setup) -> None:
    db_engine, settings, requester, supervisor, _, resource = setup
    approved = _approve_listing(
        db_engine,
        requester,
        supervisor,
        resource,
        simulate_outcome="unknown",
    )
    assert run_execution_cycle(db_engine=db_engine, settings=settings) == 1
    with Session(db_engine) as db:
        execution = db.exec(
            select(BusinessActionExecution).where(BusinessActionExecution.request_id == approved.id)
        ).one()
        assert execution.status == "manual_resolution_required"
        assert execution.next_attempt_at is None


def test_successful_action_can_be_compensated_but_not_by_requester(setup) -> None:
    db_engine, settings, requester, supervisor, second, resource = setup
    approved = _approve_listing(db_engine, requester, supervisor, resource)
    run_execution_cycle(db_engine=db_engine, settings=settings)
    with Session(db_engine) as db:
        execution = db.exec(
            select(BusinessActionExecution).where(BusinessActionExecution.request_id == approved.id)
        ).one()
        with pytest.raises(HTTPException) as denied:
            request_compensation(
                db,
                tenant_id="tenant_demo",
                execution_id=execution.id,
                reason="申请人尝试自行补偿",
                user=requester,
            )
        assert denied.value.status_code == 403
        requested = request_compensation(
            db,
            tenant_id="tenant_demo",
            execution_id=execution.id,
            reason="外部核对后需要撤销发布",
            user=second,
        )
        assert requested.status == "compensation_requested"

    assert run_execution_cycle(db_engine=db_engine, settings=settings) == 1
    with Session(db_engine) as db:
        execution = db.exec(
            select(BusinessActionExecution).where(BusinessActionExecution.request_id == approved.id)
        ).one()
        assert execution.status == "compensated"
        assert execution.receipt_json["compensation_receipt"]["compensated"] is True


def test_live_generic_connector_denies_non_allowlisted_host() -> None:
    settings = _settings(
        business_execution_mode="live",
        business_execution_allowed_hosts="api.example.com",
    )
    connector = GenericBusinessHttpConnector(
        connector_type="logistics_http",
        settings=settings,
    )
    context = ExecutionContext(
        execution_id="exec-1",
        tenant_id="tenant_demo",
        request_id="request-1",
        resource_id="carrier-1",
        resource_type="carrier",
        resource_code="UPS-US",
        action_type="change_routing_rule",
        payload={"route_policy": "priority"},
        resource_metadata={
            "execute_url": "https://127.0.0.1/internal",
            "auth_profile": "LOGISTICS_PRIMARY",
            "supports_idempotency": True,
        },
        connector_type="logistics_http",
        environment="live",
        idempotency_key="stable-key",
        attempt_no=1,
    )
    outcome = connector.execute(context)
    assert outcome.disposition == "terminal_failure"
    assert outcome.error_code == "unsafe_connector_url"


@pytest.mark.parametrize(
    ("action_type", "payload", "metadata", "expected_body"),
    [
        (
            "change_ad_bid",
            {
                "campaign_id": "C-1",
                "target_id": "T-1",
                "bid": 1.2,
                "previous_bid": 0.9,
            },
            {"bid_update_path": "/v2/sp/targets"},
            [{"campaignId": "C-1", "targetId": "T-1", "bid": 0.9}],
        ),
        (
            "change_campaign_status",
            {"campaign_id": "C-1", "status": "PAUSED", "previous_status": "ENABLED"},
            {"campaign_update_path": "/v2/sp/campaigns"},
            [{"campaignId": "C-1", "state": "ENABLED"}],
        ),
        (
            "update_negative_keywords",
            {"campaign_id": "C-1", "rollback_keyword_ids": ["K-1", "K-2"]},
            {"negative_keyword_rollback_path": "/v2/sp/negativeKeywords"},
            [
                {"keywordId": "K-1", "state": "ARCHIVED"},
                {"keywordId": "K-2", "state": "ARCHIVED"},
            ],
        ),
    ],
)
def test_amazon_ads_compensation_uses_verified_inverse_operation(
    monkeypatch, action_type, payload, metadata, expected_body
) -> None:
    connector = AmazonAdsConnector(settings=_settings())
    captured = {}

    def fake_request(context, path, body):
        captured.update(path=path, body=body)
        return ConnectorOutcome(disposition="succeeded", receipt={"compensated": True})

    monkeypatch.setattr(connector, "_request", fake_request)
    context = ExecutionContext(
        execution_id="exec-ads-compensate",
        tenant_id="tenant_demo",
        request_id="request-ads-compensate",
        resource_id="ads-1",
        resource_type="ad_account",
        resource_code="ADS-US",
        action_type=action_type,
        payload=payload,
        resource_metadata=metadata,
        connector_type="amazon_ads",
        environment="live",
        idempotency_key="stable-key",
        attempt_no=1,
    )
    outcome = connector.compensate(context, {})
    assert outcome.disposition == "succeeded"
    assert captured["body"] == expected_body


def test_amazon_ads_negative_keyword_compensation_fails_closed_without_remote_ids() -> None:
    connector = AmazonAdsConnector(settings=_settings())
    context = ExecutionContext(
        execution_id="exec-ads-manual",
        tenant_id="tenant_demo",
        request_id="request-ads-manual",
        resource_id="ads-1",
        resource_type="ad_account",
        resource_code="ADS-US",
        action_type="update_negative_keywords",
        payload={"campaign_id": "C-1", "keywords": ["example"]},
        resource_metadata={"negative_keyword_rollback_path": "/negativeKeywords"},
        connector_type="amazon_ads",
        environment="live",
        idempotency_key="stable-key",
        attempt_no=1,
    )
    outcome = connector.compensate(context, {})
    assert outcome.disposition == "terminal_failure"
    assert outcome.error_code == "negative_keyword_rollback_unavailable"


def test_resource_change_invalidates_approved_execution_before_connector(setup) -> None:
    db_engine, settings, requester, supervisor, _, resource = setup
    approved = _approve_listing(db_engine, requester, supervisor, resource)

    with Session(db_engine) as db:
        changed = update_resource(
            db,
            resource_id=resource.id,
            request=BusinessResourceUpdate(
                tenant_id="tenant_demo",
                metadata={"marketplace_id": "ATVPDKIKX0DER", "region": "na"},
            ),
            user=supervisor,
        )
        action = db.get(HighRiskActionRequest, approved.id)
        execution = db.exec(
            select(BusinessActionExecution).where(BusinessActionExecution.request_id == approved.id)
        ).one()
        assert changed.revision == 2
        assert action is not None and action.status == "invalidated"
        assert execution.status == "failed"
        assert execution.last_error_code == "approval_invalidated"
        with pytest.raises(HTTPException) as denied:
            retry_execution(
                db,
                tenant_id="tenant_demo",
                execution_id=execution.id,
                reason="尝试重放已失效审批",
                user=supervisor,
            )
        assert denied.value.status_code == 409

    assert run_execution_cycle(db_engine=db_engine, settings=settings) == 0


def test_worker_detects_action_payload_tampering_before_connector(setup) -> None:
    db_engine, settings, requester, supervisor, _, resource = setup
    approved = _approve_listing(db_engine, requester, supervisor, resource)

    with Session(db_engine) as db:
        action = db.get(HighRiskActionRequest, approved.id)
        assert action is not None
        action.payload_json = {**action.payload_json, "listing_id": "TAMPERED"}
        db.add(action)
        db.commit()

    assert run_execution_cycle(db_engine=db_engine, settings=settings) == 0
    with Session(db_engine) as db:
        action = db.get(HighRiskActionRequest, approved.id)
        execution = db.exec(
            select(BusinessActionExecution).where(BusinessActionExecution.request_id == approved.id)
        ).one()
        events = db.exec(
            select(HighRiskActionEvent).where(HighRiskActionEvent.request_id == approved.id)
        ).all()
        assert action is not None and action.status == "invalidated"
        assert action.invalidation_reason == "approved_action_content_changed"
        assert execution.status == "failed"
        assert execution.receipt_json == {}
        assert any(event.event_type == "invalidated" for event in events)


def _action_row(db: Session, request_id: str):
    from app.db.models import HighRiskActionRequest

    return db.exec(
        select(HighRiskActionRequest).where(HighRiskActionRequest.id == request_id)
    ).one()
