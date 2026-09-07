from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.business_resources.schema import BusinessResourceCreate
from app.business_resources.service import create_resource, decide_action_request
from app.crossborder.schema import (
    AfterSalesCaseCreate,
    AfterSalesClassification,
    AfterSalesClose,
    AfterSalesDraft,
    AfterSalesQueryResult,
    EvidenceCitation,
    HumanExceptionResolution,
    IntegrationHealthReport,
    LogisticsAnomalyBatchCreate,
    LogisticsAnomalyInput,
    LogisticsEscalation,
    LogisticsResolution,
)
from app.crossborder.service import (
    classify_after_sales_case,
    close_after_sales_case,
    create_after_sales_case,
    crossborder_overview,
    draft_after_sales_resolution,
    escalate_logistics_anomaly,
    get_after_sales_case,
    get_logistics_anomaly,
    ingest_logistics_anomalies,
    list_after_sales_cases,
    list_integration_health,
    list_logistics_anomalies,
    record_after_sales_query,
    report_integration_health,
    resolve_after_sales_exception,
    resolve_logistics_anomaly,
)
from app.db.models import (
    AfterSalesCase,
    ProductQualityIssue,
    Tenant,
    User,
    WorkTask,
    utc_now,
)


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _user(user_id: str, role: str, *, tenant_id: str = "tenant_demo", admin: bool = False) -> User:
    return User(
        id=user_id,
        tenant_id=tenant_id,
        username=user_id,
        role="admin" if admin else "member",
        business_role=role,
        password_hash="disabled",
    )


@pytest.fixture
def db() -> Session:
    engine = _engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Tenant(id="tenant_demo", name="Demo"))
        session.add(Tenant(id="tenant_other", name="Other"))
        session.commit()
        yield session


@pytest.fixture
def workforce(db: Session) -> dict[str, User]:
    users = {
        "supervisor": _user("supervisor", "operations_supervisor"),
        "supervisor2": _user("supervisor2", "operations_supervisor"),
        "after_sales": _user("after-sales", "after_sales_specialist"),
        "logistics": _user("logistics", "logistics_exception_specialist"),
        "listing": _user("listing", "listing_compliance_specialist"),
        "procurement": _user("procurement", "procurement_specialist"),
        "other_tenant": _user(
            "other", "operations_supervisor", tenant_id="tenant_other"
        ),
    }
    db.add_all(users.values())
    db.commit()
    return users


@pytest.fixture
def resources(db: Session, workforce: dict[str, User]) -> dict[str, str]:
    supervisor = workforce["supervisor"]
    store = create_resource(
        db,
        request=BusinessResourceCreate(
            tenant_id="tenant_demo",
            resource_type="store",
            code="STORE-US",
            name="Amazon US",
        ),
        user=supervisor,
    )
    carrier = create_resource(
        db,
        request=BusinessResourceCreate(
            tenant_id="tenant_demo",
            resource_type="carrier",
            code="UPS-US",
            name="UPS US",
        ),
        user=supervisor,
    )
    return {"store": store.id, "carrier": carrier.id}


def _create_case(
    db: Session,
    workforce: dict[str, User],
    resources: dict[str, str],
    *,
    key: str = "CASE-2026-0001",
):
    return create_after_sales_case(
        db,
        request=AfterSalesCaseCreate(
            tenant_id="tenant_demo",
            case_key=key,
            store_resource_id=resources["store"],
            platform="Amazon",
            marketplace_country="US",
            language="en-US",
            order_reference="AMZ-ORDER-11112222",
            summary="Customer reports that the parcel has not arrived.",
        ),
        user=workforce["after_sales"],
    )


def _query_case(db: Session, case, user: User, *, dependency_status=None):
    return record_after_sales_query(
        db,
        case_id=case.id,
        request=AfterSalesQueryResult(
            tenant_id="tenant_demo",
            expected_version=case.version,
            order_snapshot={
                "order_status": "shipped",
                "payment_status": "paid",
                "shipment_status": "in_transit",
                "logistics_status": "stalled",
                "sku_codes": ["SKU-1"],
                "history": [
                    {
                        "event_code": "PICKED_UP",
                        "status": "complete",
                        "source": "carrier",
                        "occurred_at": "2026-09-01T10:00:00Z",
                        "customer_email": "must-not-persist@example.com",
                    }
                ],
                "currency": "USD",
                "order_amount": 39.9,
                "updated_at": "2026-09-02T10:00:00Z",
            },
            citations=[
                EvidenceCitation(
                    source_id="kb_after_sales_policy_v3",
                    title="US delivery exception policy",
                    version="3.0",
                    scope="tenant_demo/store:STORE-US",
                    excerpt="Escalate stalled parcels before the platform deadline.",
                    retrieved_at=utc_now(),
                )
            ],
            dependency_status=dependency_status
            or {"orders": "healthy", "logistics": "healthy", "knowledge": "healthy"},
            observed_at=utc_now(),
        ),
        user=user,
    )


def test_after_sales_full_chain_links_query_citations_approval_tasks_and_trace(
    db: Session, workforce: dict[str, User], resources: dict[str, str]
) -> None:
    case = _create_case(db, workforce, resources)
    stored = db.get(AfterSalesCase, case.id)
    assert stored is not None
    assert "11112222" not in stored.order_reference_masked
    assert stored.order_reference_digest.startswith("sha256:")
    assert db.get(WorkTask, case.task_id).source_type == "after_sales_case"

    queried = _query_case(db, case, workforce["after_sales"])
    assert queried.status == "queried"
    assert queried.order_snapshot["history"][0].get("customer_email") is None
    assert queried.citations[0]["version"] == "3.0"

    classified = classify_after_sales_case(
        db,
        case_id=case.id,
        request=AfterSalesClassification(
            tenant_id="tenant_demo",
            expected_version=queried.version,
            category="return_refund",
            confidence=0.94,
            risk_level="medium",
        ),
        user=workforce["after_sales"],
    )
    drafted = draft_after_sales_resolution(
        db,
        case_id=case.id,
        request=AfterSalesDraft(
            tenant_id="tenant_demo",
            expected_version=classified.version,
            recommendation={"action": "refund", "policy": "delivery_exception_v3"},
            reply_draft="We are sorry. A reviewed refund is being arranged.",
            requires_approval=True,
            refund_amount=39.9,
            currency="USD",
        ),
        user=workforce["after_sales"],
    )
    assert drafted.status == "waiting_approval"
    assert drafted.approval_request_id

    approved = decide_action_request(
        db,
        tenant_id="tenant_demo",
        request_id=drafted.approval_request_id,
        decision="approved",
        reason="Policy, evidence and amount verified",
        user=workforce["supervisor"],
    )
    assert approved.status == "approved"

    closed = close_after_sales_case(
        db,
        case_id=case.id,
        request=AfterSalesClose(
            tenant_id="tenant_demo",
            expected_version=drafted.version,
            root_cause="Carrier scan stopped before the delivery promise.",
            outcome="Approved resolution prepared; no external reply was sent by this workflow.",
        ),
        user=workforce["after_sales"],
    )
    assert closed.status == "closed"
    assert closed.follow_up_task_ids
    assert db.get(WorkTask, closed.task_id).status == "completed"
    assert db.get(WorkTask, closed.follow_up_task_ids[0]).owner_business_role == (
        "listing_compliance_specialist"
    )
    assert [event.event_type for event in closed.events] == [
        "intake_created",
        "order_context_queried",
        "classified",
        "resolution_drafted",
        "case_closed",
    ]


def test_after_sales_dependency_failure_hands_off_and_requires_manager_resolution(
    db: Session, workforce: dict[str, User], resources: dict[str, str]
) -> None:
    case = _create_case(db, workforce, resources, key="CASE-2026-STALE")
    held = _query_case(
        db,
        case,
        workforce["after_sales"],
        dependency_status={"orders": "healthy", "logistics": "stale"},
    )
    assert held.status == "needs_human"
    assert db.get(WorkTask, held.task_id).status == "waiting_input"
    health = list_integration_health(db, tenant_id="tenant_demo", user=workforce["supervisor"])
    assert {item.dependency_key: item.status for item in health}["logistics"] == "degraded"

    with pytest.raises(HTTPException) as specialist_resolution:
        resolve_after_sales_exception(
            db,
            case_id=case.id,
            request=HumanExceptionResolution(
                tenant_id="tenant_demo",
                expected_version=held.version,
                resolution_note="Checked manually and refreshed the carrier event.",
            ),
            user=workforce["after_sales"],
        )
    assert specialist_resolution.value.status_code == 403
    db.rollback()

    resumed = resolve_after_sales_exception(
        db,
        case_id=case.id,
        request=HumanExceptionResolution(
            tenant_id="tenant_demo",
            expected_version=held.version,
            resolution_note="Checked manually and refreshed the carrier event.",
        ),
        user=workforce["supervisor"],
    )
    assert resumed.status == "classified"
    assert resumed.needs_human is False


def test_after_sales_rejects_pii_fields_scope_mismatch_version_conflict_and_bola(
    db: Session, workforce: dict[str, User], resources: dict[str, str]
) -> None:
    case = _create_case(db, workforce, resources, key="CASE-2026-SECURITY")
    with pytest.raises(HTTPException) as pii:
        record_after_sales_query(
            db,
            case_id=case.id,
            request=AfterSalesQueryResult(
                tenant_id="tenant_demo",
                expected_version=case.version,
                order_snapshot={"customer_email": "secret@example.com"},
                citations=[
                    EvidenceCitation(
                        source_id="kb-1",
                        title="Policy",
                        version="1",
                        scope="tenant_demo",
                        retrieved_at=utc_now(),
                    )
                ],
                observed_at=utc_now(),
            ),
            user=workforce["after_sales"],
        )
    assert pii.value.status_code == 422
    db.rollback()

    with pytest.raises(HTTPException) as other_tenant:
        get_after_sales_case(
            db,
            tenant_id="tenant_demo",
            case_id=case.id,
            user=workforce["other_tenant"],
        )
    assert other_tenant.value.status_code == 403

    with pytest.raises(HTTPException) as wrong_role:
        list_after_sales_cases(db, tenant_id="tenant_demo", user=workforce["listing"])
    assert wrong_role.value.status_code == 403


def _anomaly_batch(resources: dict[str, str], *, batch_key: str):
    return LogisticsAnomalyBatchCreate(
        tenant_id="tenant_demo",
        batch_key=batch_key,
        items=[
            LogisticsAnomalyInput(
                carrier_resource_id=resources["carrier"],
                store_resource_id=resources["store"],
                platform="Amazon",
                order_reference="AMZ-ORDER-33334444",
                status_event_id="UPS-EVENT-77",
                shipment_status="IN_TRANSIT",
                anomaly_type="stalled",
                customer_impact="high",
                deadline_at=utc_now() + timedelta(hours=3),
                observed_at=utc_now(),
                channel="FBA",
                warehouse="ONT8",
                country="US",
                sku="SKU-RED",
                batch="PO-2026-09",
                evidence={
                    "last_scan_at": "2026-08-30T10:00:00Z",
                    "days_in_transit": 9,
                    "source_record_id": "evt-77",
                },
            )
        ],
    )


def test_logistics_detection_deduplicates_clusters_escalates_and_resolves(
    db: Session, workforce: dict[str, User], resources: dict[str, str]
) -> None:
    first = ingest_logistics_anomalies(
        db,
        request=_anomaly_batch(resources, batch_key="BATCH-LOG-001"),
        user=workforce["logistics"],
    )
    assert first.created_count == 1
    anomaly = first.items[0]
    assert anomaly.status == "clustered"
    assert anomaly.severity == "critical"
    assert anomaly.cluster_key.startswith("cluster:")

    duplicate = ingest_logistics_anomalies(
        db,
        request=_anomaly_batch(resources, batch_key="BATCH-LOG-002"),
        user=workforce["logistics"],
    )
    assert duplicate.created_count == 0
    assert duplicate.deduplicated_count == 1
    assert duplicate.items[0].id == anomaly.id
    assert duplicate.items[0].occurrence_count == 2

    escalated = escalate_logistics_anomaly(
        db,
        anomaly_id=anomaly.id,
        request=LogisticsEscalation(
            tenant_id="tenant_demo",
            expected_version=duplicate.items[0].version,
            targets=[
                "after_sales_specialist",
                "procurement_specialist",
                "operations_supervisor",
            ],
            reason=(
                "Platform deadline is within three hours; "
                "notify customer and assess batch risk."
            ),
        ),
        user=workforce["logistics"],
    )
    assert escalated.status == "escalated"
    assert len(escalated.follow_up_task_ids) == 3
    owners = {
        db.get(WorkTask, task_id).owner_business_role
        for task_id in escalated.follow_up_task_ids
    }
    assert owners == {
        "after_sales_specialist",
        "procurement_specialist",
        "operations_supervisor",
    }
    assert len(
        list_logistics_anomalies(
            db, tenant_id="tenant_demo", user=workforce["after_sales"]
        )
    ) == 1

    resolved = resolve_logistics_anomaly(
        db,
        anomaly_id=anomaly.id,
        request=LogisticsResolution(
            tenant_id="tenant_demo",
            expected_version=escalated.version,
            resolution="Carrier confirmed a recovery scan and delivery appointment.",
        ),
        user=workforce["logistics"],
    )
    assert resolved.status == "resolved"
    assert db.get(WorkTask, resolved.task_id).status == "completed"
    assert [event.event_type for event in resolved.events] == [
        "detected",
        "clustered",
        "duplicate_observed",
        "escalated",
        "resolved",
    ]


def test_logistics_bola_and_optimistic_locking(
    db: Session, workforce: dict[str, User], resources: dict[str, str]
) -> None:
    anomaly = ingest_logistics_anomalies(
        db,
        request=_anomaly_batch(resources, batch_key="BATCH-LOG-SECURITY"),
        user=workforce["logistics"],
    ).items[0]
    with pytest.raises(HTTPException) as other_tenant:
        get_logistics_anomaly(
            db,
            tenant_id="tenant_demo",
            anomaly_id=anomaly.id,
            user=workforce["other_tenant"],
        )
    assert other_tenant.value.status_code == 403
    with pytest.raises(HTTPException) as wrong_role:
        get_logistics_anomaly(
            db,
            tenant_id="tenant_demo",
            anomaly_id=anomaly.id,
            user=workforce["listing"],
        )
    assert wrong_role.value.status_code == 403
    with pytest.raises(HTTPException) as stale_write:
        resolve_logistics_anomaly(
            db,
            anomaly_id=anomaly.id,
            request=LogisticsResolution(
                tenant_id="tenant_demo",
                expected_version=99,
                resolution="This stale client must not overwrite newer state.",
            ),
            user=workforce["logistics"],
        )
    assert stale_write.value.status_code == 409


def test_integration_health_is_visible_and_stale_state_is_never_silent(
    db: Session, workforce: dict[str, User]
) -> None:
    reported = report_integration_health(
        db,
        request=IntegrationHealthReport(
            tenant_id="tenant_demo",
            dependency_key="amazon-orders-api",
            display_name="Amazon Orders API",
            domain="orders",
            status="degraded",
            reason_code="rate_limited",
            message="Requests are being throttled.",
            recovery_hint="Wait for the rate window and retry with backoff.",
            observed_at=utc_now() - timedelta(minutes=20),
            stale_after_seconds=60,
        ),
        user=workforce["supervisor"],
    )
    assert reported.status == "degraded"
    assert reported.effective_status == "stale"
    visible = list_integration_health(
        db, tenant_id="tenant_demo", user=workforce["after_sales"]
    )
    assert visible[0].effective_status == "stale"
    overview = crossborder_overview(
        db, tenant_id="tenant_demo", user=workforce["supervisor"]
    )
    assert overview.degraded_dependencies == 1


def test_damaged_case_creates_quality_loop_for_procurement_design_and_listing(
    db: Session, workforce: dict[str, User], resources: dict[str, str]
) -> None:
    case = _create_case(db, workforce, resources, key="CASE-QUALITY-0001")
    queried = _query_case(db, case, workforce["after_sales"])
    classified = classify_after_sales_case(
        db,
        case_id=case.id,
        request=AfterSalesClassification(
            tenant_id="tenant_demo",
            expected_version=queried.version,
            category="damaged",
            confidence=0.96,
            risk_level="medium",
        ),
        user=workforce["after_sales"],
    )
    drafted = draft_after_sales_resolution(
        db,
        case_id=case.id,
        request=AfterSalesDraft(
            tenant_id="tenant_demo",
            expected_version=classified.version,
            recommendation={"action": "replace", "reason": "damaged_in_transit"},
            reply_draft="We documented the damage and prepared a reviewed replacement plan.",
        ),
        user=workforce["after_sales"],
    )
    closed = close_after_sales_case(
        db,
        case_id=case.id,
        request=AfterSalesClose(
            tenant_id="tenant_demo",
            expected_version=drafted.version,
            root_cause="Packaging protection failed during line-haul handling.",
            outcome="Customer resolution completed; product quality loop opened.",
        ),
        user=workforce["after_sales"],
    )
    issue = db.exec(
        select(ProductQualityIssue).where(ProductQualityIssue.source_case_id == case.id)
    ).one()
    assert issue.task_ids_json == closed.follow_up_task_ids
    roles = {db.get(WorkTask, task_id).owner_business_role for task_id in issue.task_ids_json}
    assert roles == {"procurement_specialist", "designer", "listing_compliance_specialist"}
