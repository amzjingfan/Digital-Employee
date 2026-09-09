from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.bi.schema import BiDailyCommerceFactInput, BiIngestionBatchCreate
from app.bi.service import get_batch, ingest_batch, list_daily_metrics, list_facts
from app.db.models import (
    BiDailyCommerceFact,
    BiDailyMetric,
    BiDataQualityCheck,
    BiIngestionBatch,
    BiMetricDefinition,
    Tenant,
    User,
)
from app.operations_reports.schema import OperationsReportGenerate
from app.operations_reports.service import generate_report


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _user(*, tenant_id: str = "tenant_a", role: str = "operations_supervisor") -> User:
    return User(
        tenant_id=tenant_id,
        username=f"{role}-{tenant_id}",
        role="member",
        business_role=role,
        password_hash="not-used",
    )


def _request(
    *,
    tenant_id: str = "tenant_a",
    source_version: str = "v1",
    gross_sales: Decimal = Decimal("100.00"),
    ad_spend: Decimal = Decimal("20.00"),
    expected_gross_sales: Decimal | None = None,
    rolling_units_sold: int = 0,
) -> BiIngestionBatchCreate:
    today = datetime.now(UTC).date()
    window_start = datetime.combine(today, time.min, UTC)
    return BiIngestionBatchCreate(
        tenant_id=tenant_id,
        source_key="manual.amazon-us",
        window_start=window_start,
        window_end=window_start + timedelta(minutes=30),
        business_timezone="UTC",
        expected_row_count=1,
        expected_gross_sales=(
            gross_sales if expected_gross_sales is None else expected_gross_sales
        ),
        expected_ad_spend=ad_spend,
        facts=[
            BiDailyCommerceFactInput(
                external_id="STORE-DAY-001",
                source_version=source_version,
                business_date=today,
                brand_id="brand_1",
                store_id="store_1",
                platform="amazon",
                entity_type="store",
                entity_id="store_1",
                currency="usd",
                gross_sales=gross_sales,
                refund_amount=Decimal("10.00"),
                ad_spend=ad_spend,
                attributed_ad_sales=Decimal("50.00"),
                impressions=100,
                clicks=10,
                orders=2,
                available_inventory=30,
                rolling_units_sold=rolling_units_sold,
                rolling_window_days=30,
                source_observed_at=datetime.now(UTC) - timedelta(minutes=5),
            )
        ],
    )


def _seed(db: Session, *tenant_ids: str) -> dict[str, User]:
    users: dict[str, User] = {}
    for tenant_id in tenant_ids:
        user = _user(tenant_id=tenant_id)
        db.add(Tenant(id=tenant_id, name=tenant_id))
        db.add(user)
        users[tenant_id] = user
    db.commit()
    return users


def test_ingestion_is_idempotent_decimal_and_zero_denominators_are_explicit() -> None:
    with _session() as db:
        user = _seed(db, "tenant_a")["tenant_a"]
        request = _request()

        first = ingest_batch(db, request=request, user=user)
        replay = ingest_batch(db, request=request, user=user)
        metrics = list_daily_metrics(
            db,
            tenant_id="tenant_a",
            user=user,
            start_date=request.facts[0].business_date,
            end_date=request.facts[0].business_date,
            entity_type="tenant",
        )

        assert first.id == replay.id
        assert first.status == "succeeded"
        assert first.quality_status == "passed"
        assert first.fact_count == 1
        assert first.metric_count == 16
        assert len(db.exec(select(BiIngestionBatch)).all()) == 1
        assert len(db.exec(select(BiDailyCommerceFact)).all()) == 1
        assert len(db.exec(select(BiMetricDefinition)).all()) == 8
        assert len(db.exec(select(BiDataQualityCheck)).all()) == 8
        by_code = {item.metric_code: item for item in metrics}
        assert by_code["gmv"].value == Decimal("90.000000")
        assert by_code["ctr"].value == Decimal("0.100000")
        assert by_code["acos"].value == Decimal("0.400000")
        assert by_code["inventory_days"].value is None
        assert by_code["inventory_days"].null_reason == "denominator_zero"
        assert by_code["gmv"].evidence["fact_count"] == 1
        assert by_code["gmv"].evidence["fact_ids"] == [
            db.exec(select(BiDailyCommerceFact)).one().id
        ]
        evidence_facts = list_facts(
            db,
            tenant_id="tenant_a",
            user=user,
            batch_id=first.id,
        )
        assert [item.id for item in evidence_facts] == by_code["gmv"].evidence["fact_ids"]


def test_revised_window_supersedes_facts_and_metrics_without_accumulation() -> None:
    with _session() as db:
        user = _seed(db, "tenant_a")["tenant_a"]
        first = ingest_batch(db, request=_request(), user=user)
        revised_request = _request(
            source_version="v2",
            gross_sales=Decimal("130.00"),
            rolling_units_sold=15,
        )

        revised = ingest_batch(db, request=revised_request, user=user)
        replay = ingest_batch(db, request=revised_request, user=user)
        batches = db.exec(select(BiIngestionBatch).order_by(BiIngestionBatch.created_at)).all()
        facts = db.exec(select(BiDailyCommerceFact)).all()
        current_metrics = db.exec(
            select(BiDailyMetric).where(BiDailyMetric.is_current.is_(True))
        ).all()

        assert revised.id == replay.id
        assert first.id != revised.id
        assert [item.status for item in batches] == ["superseded", "succeeded"]
        assert len(facts) == 2
        assert sum(item.is_current for item in facts) == 1
        assert next(item for item in facts if item.is_current).gross_sales == Decimal("130.000000")
        assert len(current_metrics) == 16
        tenant_gmv = next(
            item
            for item in current_metrics
            if item.entity_type == "tenant" and item.metric_code == "gmv"
        )
        assert tenant_gmv.value == Decimal("120.000000")


def test_reconciliation_and_source_version_conflicts_are_rejected_with_evidence() -> None:
    with _session() as db:
        user = _seed(db, "tenant_a")["tenant_a"]
        reconciliation_failure = _request(expected_gross_sales=Decimal("999.00"))
        rejected = ingest_batch(db, request=reconciliation_failure, user=user)

        assert rejected.status == "rejected"
        assert rejected.quality_status == "failed"
        assert rejected.fact_count == 0
        failed_codes = {
            item.check_code for item in rejected.quality_checks if item.status == "failed"
        }
        assert failed_codes == {"source_gross_sales_reconciliation"}

        accepted = ingest_batch(db, request=_request(source_version="v2"), user=user)
        conflict = ingest_batch(
            db,
            request=_request(source_version="v2", gross_sales=Decimal("140.00")),
            user=user,
        )

        assert accepted.status == "succeeded"
        assert conflict.status == "rejected"
        version_check = next(
            item
            for item in conflict.quality_checks
            if item.check_code == "source_version_immutability"
        )
        assert version_check.status == "failed"
        assert version_check.observed["sample"][0]["reason"] == "version_content_changed"
        assert len(db.exec(select(BiDailyCommerceFact)).all()) == 1


def test_same_external_ids_are_isolated_by_tenant_and_cross_tenant_reads_fail() -> None:
    with _session() as db:
        users = _seed(db, "tenant_a", "tenant_b")
        request_a = _request(tenant_id="tenant_a", gross_sales=Decimal("100.00"))
        request_b = _request(tenant_id="tenant_b", gross_sales=Decimal("250.00"))
        ingest_batch(db, request=request_a, user=users["tenant_a"])
        ingest_batch(db, request=request_b, user=users["tenant_b"])

        metrics_a = list_daily_metrics(
            db,
            tenant_id="tenant_a",
            user=users["tenant_a"],
            start_date=request_a.facts[0].business_date,
            end_date=request_a.facts[0].business_date,
            metric_code="gmv",
            entity_type="tenant",
        )
        metrics_b = list_daily_metrics(
            db,
            tenant_id="tenant_b",
            user=users["tenant_b"],
            start_date=request_b.facts[0].business_date,
            end_date=request_b.facts[0].business_date,
            metric_code="gmv",
            entity_type="tenant",
        )

        assert metrics_a[0].value == Decimal("90.000000")
        assert metrics_b[0].value == Decimal("240.000000")
        with pytest.raises(HTTPException) as error:
            get_batch(
                db,
                tenant_id="tenant_b",
                batch_id=metrics_b[0].batch_id,
                user=users["tenant_a"],
            )
        assert error.value.status_code == 403


def test_operations_report_freezes_bi_definition_batch_and_fact_evidence() -> None:
    with _session() as db:
        user = _seed(db, "tenant_a")["tenant_a"]
        request = _request(rolling_units_sold=15)
        batch = ingest_batch(db, request=request, user=user)

        report = generate_report(
            db,
            request=OperationsReportGenerate(
                tenant_id="tenant_a",
                report_type="daily",
                report_date=request.facts[0].business_date,
                timezone="UTC",
            ),
            user=user,
        )

        kpis = report.sections["commerce_kpis"]
        assert len(kpis) == 8
        gmv = next(item for item in kpis if item["metric_code"] == "gmv")
        assert gmv["value"] == "90.000000"
        assert gmv["metric_definition_version"] == "1.0.0"
        assert gmv["batch_id"] == batch.id
        assert gmv["evidence"]["fact_count"] == 1
        assert "bi_daily_metric" in {item.source_type for item in report.sources}
