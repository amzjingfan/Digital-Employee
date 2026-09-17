from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.bi.schema import (
    BiDailyCommerceFactInput,
    BiDailyCommerceFactRead,
    BiDailyMetricRead,
    BiIngestionBatchCreate,
    BiIngestionBatchRead,
    BiQualityCheckRead,
)
from app.db import set_tenant_context
from app.db.models import (
    BiDailyCommerceFact,
    BiDailyMetric,
    BiDataQualityCheck,
    BiIngestionBatch,
    BiMetricDefinition,
    User,
)

_MANAGER_ROLES = {"operations_supervisor", "platform_admin"}
_READER_ROLES = _MANAGER_ROLES | {
    "advertising_inspection_specialist",
    "logistics_exception_specialist",
    "procurement_specialist",
}
_METRIC_VERSION = "1.0.0"
_SCALE = Decimal("0.000001")
_METRIC_CONTRACTS: dict[str, dict[str, Any]] = {
    "gmv": {
        "name": "GMV",
        "formula": "sum(gross_sales) - sum(refund_amount)",
        "currency_policy": "source_currency",
    },
    "ctr": {
        "name": "CTR",
        "formula": "sum(clicks) / sum(impressions)",
        "currency_policy": "dimensionless",
    },
    "cvr": {
        "name": "CVR",
        "formula": "sum(orders) / sum(clicks)",
        "currency_policy": "dimensionless",
    },
    "cpc": {
        "name": "CPC",
        "formula": "sum(ad_spend) / sum(clicks)",
        "currency_policy": "source_currency",
    },
    "acos": {
        "name": "ACOS",
        "formula": "sum(ad_spend) / sum(attributed_ad_sales)",
        "currency_policy": "dimensionless",
    },
    "tacos": {
        "name": "TACOS",
        "formula": "sum(ad_spend) / (sum(gross_sales) - sum(refund_amount))",
        "currency_policy": "dimensionless",
    },
    "roas": {
        "name": "ROAS",
        "formula": "sum(attributed_ad_sales) / sum(ad_spend)",
        "currency_policy": "dimensionless",
    },
    "inventory_days": {
        "name": "库存天数",
        "formula": ("sum(available_inventory * rolling_window_days) / sum(rolling_units_sold)"),
        "currency_policy": "dimensionless",
    },
}


def ingest_batch(
    db: Session,
    *,
    request: BiIngestionBatchCreate,
    user: User,
) -> BiIngestionBatchRead:
    """Validate and publish one deterministic source window without accumulating replays."""

    _require_manager(user, request.tenant_id)
    set_tenant_context(db, request.tenant_id)
    window_start = _utc(request.window_start)
    window_end = _utc(request.window_end)
    input_digest = _batch_digest(request)
    existing = db.exec(
        select(BiIngestionBatch).where(
            BiIngestionBatch.tenant_id == request.tenant_id,
            BiIngestionBatch.source_key == request.source_key,
            BiIngestionBatch.window_start == window_start,
            BiIngestionBatch.window_end == window_end,
            BiIngestionBatch.input_digest == input_digest,
        )
    ).first()
    if existing is not None:
        return _read_batch(db, existing)

    actual_gross_sales = sum((item.gross_sales for item in request.facts), Decimal(0))
    actual_ad_spend = sum((item.ad_spend for item in request.facts), Decimal(0))
    observed_times = [_utc(item.source_observed_at) for item in request.facts]
    batch = BiIngestionBatch(
        tenant_id=request.tenant_id,
        source_key=request.source_key,
        window_start=window_start,
        window_end=window_end,
        business_timezone=request.business_timezone,
        snapshot_mode=request.snapshot_mode,
        input_digest=input_digest,
        row_count=len(request.facts),
        expected_row_count=request.expected_row_count,
        expected_gross_sales=request.expected_gross_sales,
        expected_ad_spend=request.expected_ad_spend,
        actual_gross_sales=actual_gross_sales,
        actual_ad_spend=actual_ad_spend,
        reconciliation_tolerance=request.reconciliation_tolerance,
        metric_definition_version=_METRIC_VERSION,
        latest_source_observed_at=max(observed_times) if observed_times else None,
        created_by_user_id=user.id,
    )
    db.add(batch)
    try:
        db.flush()
    except IntegrityError as exc:
        return _recover_concurrent_batch(
            db,
            request=request,
            input_digest=input_digest,
            window_start=window_start,
            window_end=window_end,
            error=exc,
        )

    checks = _quality_results(
        db,
        request=request,
        window_start=window_start,
        window_end=window_end,
        actual_gross_sales=actual_gross_sales,
        actual_ad_spend=actual_ad_spend,
    )
    for check in checks:
        db.add(
            BiDataQualityCheck(
                tenant_id=request.tenant_id,
                batch_id=batch.id,
                **check,
            )
        )

    if any(check["status"] == "failed" for check in checks):
        batch.status = "rejected"
        batch.quality_status = "failed"
        batch.rejected_count = len(request.facts)
        batch.completed_at = _now()
        db.add(batch)
        try:
            db.commit()
        except IntegrityError as exc:
            return _recover_concurrent_batch(
                db,
                request=request,
                input_digest=input_digest,
                window_start=window_start,
                window_end=window_end,
                error=exc,
            )
        db.refresh(batch)
        return _read_batch(db, batch)

    definitions = _ensure_metric_definitions(db, tenant_id=request.tenant_id, user=user)
    previous_batches = db.exec(
        select(BiIngestionBatch).where(
            BiIngestionBatch.tenant_id == request.tenant_id,
            BiIngestionBatch.source_key == request.source_key,
            BiIngestionBatch.window_start == window_start,
            BiIngestionBatch.window_end == window_end,
            BiIngestionBatch.status == "succeeded",
        )
    ).all()
    for previous in previous_batches:
        previous.status = "superseded"
        db.add(previous)

    fact_ids = _publish_facts(
        db,
        batch=batch,
        request=request,
        previous_batch_ids={item.id for item in previous_batches},
    )
    _rebuild_metrics(
        db,
        batch=batch,
        request=request,
        definitions=definitions,
        window_start=window_start,
        window_end=window_end,
    )
    batch.status = "succeeded"
    batch.quality_status = "passed"
    batch.accepted_count = len(fact_ids)
    batch.completed_at = _now()
    db.add(batch)
    try:
        db.commit()
    except IntegrityError as exc:
        return _recover_concurrent_batch(
            db,
            request=request,
            input_digest=input_digest,
            window_start=window_start,
            window_end=window_end,
            error=exc,
        )
    db.refresh(batch)
    return _read_batch(db, batch)


def get_batch(
    db: Session,
    *,
    tenant_id: str,
    batch_id: str,
    user: User,
) -> BiIngestionBatchRead:
    _require_reader(user, tenant_id)
    set_tenant_context(db, tenant_id)
    row = db.exec(
        select(BiIngestionBatch).where(
            BiIngestionBatch.tenant_id == tenant_id,
            BiIngestionBatch.id == batch_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="BI ingestion batch not found")
    return _read_batch(db, row)


def list_daily_metrics(
    db: Session,
    *,
    tenant_id: str,
    user: User,
    start_date: date,
    end_date: date,
    metric_code: str | None = None,
    brand_id: str | None = None,
    store_id: str | None = None,
    platform: str | None = None,
    entity_type: str | None = None,
) -> list[BiDailyMetricRead]:
    _require_reader(user, tenant_id)
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must not be before start_date")
    if (end_date - start_date).days > 92:
        raise HTTPException(status_code=422, detail="BI metric queries are limited to 93 days")
    set_tenant_context(db, tenant_id)
    statement = select(BiDailyMetric).where(
        BiDailyMetric.tenant_id == tenant_id,
        BiDailyMetric.business_date >= start_date,
        BiDailyMetric.business_date <= end_date,
        BiDailyMetric.is_current.is_(True),
    )
    for column, value in (
        (BiDailyMetric.metric_code, metric_code),
        (BiDailyMetric.brand_id, brand_id),
        (BiDailyMetric.store_id, store_id),
        (BiDailyMetric.platform, platform),
        (BiDailyMetric.entity_type, entity_type),
    ):
        if value:
            statement = statement.where(column == value)
    rows = db.exec(
        statement.order_by(
            BiDailyMetric.business_date,
            BiDailyMetric.entity_type,
            BiDailyMetric.entity_id,
            BiDailyMetric.metric_code,
        ).limit(5000)
    ).all()
    return [_read_metric(row) for row in rows]


def list_facts(
    db: Session,
    *,
    tenant_id: str,
    user: User,
    batch_id: str | None = None,
    business_date: date | None = None,
    store_id: str | None = None,
    current_only: bool = True,
) -> list[BiDailyCommerceFactRead]:
    """Resolve KPI evidence to normalized facts within the validated tenant context."""

    _require_reader(user, tenant_id)
    set_tenant_context(db, tenant_id)
    statement = select(BiDailyCommerceFact).where(BiDailyCommerceFact.tenant_id == tenant_id)
    if batch_id:
        statement = statement.where(BiDailyCommerceFact.batch_id == batch_id)
    if business_date:
        statement = statement.where(BiDailyCommerceFact.business_date == business_date)
    if store_id:
        statement = statement.where(BiDailyCommerceFact.store_id == store_id)
    if current_only:
        statement = statement.where(BiDailyCommerceFact.is_current.is_(True))
    rows = db.exec(
        statement.order_by(
            BiDailyCommerceFact.business_date,
            BiDailyCommerceFact.store_id,
            BiDailyCommerceFact.external_id,
            BiDailyCommerceFact.created_at,
        ).limit(1000)
    ).all()
    return [_read_fact(row) for row in rows]


def _quality_results(
    db: Session,
    *,
    request: BiIngestionBatchCreate,
    window_start: datetime,
    window_end: datetime,
    actual_gross_sales: Decimal,
    actual_ad_spend: Decimal,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def add(
        check_code: str,
        *,
        passed: bool | None,
        observed: dict[str, Any],
        expected: dict[str, Any],
        detail: str,
        severity: str = "error",
    ) -> None:
        checks.append(
            {
                "check_code": check_code,
                "status": "skipped" if passed is None else "passed" if passed else "failed",
                "severity": "info" if passed is None else severity,
                "observed_json": observed,
                "expected_json": expected,
                "detail": detail,
            }
        )

    external_counts = Counter(item.external_id for item in request.facts)
    duplicates = sorted(key for key, count in external_counts.items() if count > 1)
    add(
        "payload_external_id_uniqueness",
        passed=not duplicates,
        observed={"duplicate_count": len(duplicates), "sample": duplicates[:20]},
        expected={"duplicate_count": 0},
        detail="A source window can contain at most one version of each external fact.",
    )

    local_start, local_end = _local_date_bounds(
        window_start,
        window_end,
        request.business_timezone,
    )
    invalid_dates = sorted(
        {
            item.business_date.isoformat()
            for item in request.facts
            if item.business_date < local_start or item.business_date >= local_end
        }
    )
    add(
        "business_date_within_window",
        passed=not invalid_dates,
        observed={"invalid_date_count": len(invalid_dates), "sample": invalid_dates[:20]},
        expected={
            "start_inclusive": local_start.isoformat(),
            "end_exclusive": local_end.isoformat(),
        },
        detail="Business dates are evaluated in the declared source timezone.",
    )

    now = _now()
    future_observations = [
        item.external_id
        for item in request.facts
        if _utc(item.source_observed_at) > now + timedelta(minutes=5)
    ]
    add(
        "source_observed_not_future",
        passed=not future_observations,
        observed={"future_count": len(future_observations), "sample": future_observations[:20]},
        expected={"maximum_clock_skew_seconds": 300},
        detail="Future source timestamps would make freshness evidence misleading.",
    )

    currency_groups: dict[tuple[Any, ...], set[str]] = defaultdict(set)
    for item in request.facts:
        currency_groups[(item.business_date, "tenant")].add(item.currency)
        currency_groups[
            (
                item.business_date,
                item.brand_id,
                item.store_id,
                item.platform,
                item.entity_type,
                item.entity_id,
            )
        ].add(item.currency)
    mixed_groups = [
        {"grain": [str(part) for part in grain], "currencies": sorted(currencies)}
        for grain, currencies in currency_groups.items()
        if len(currencies) > 1
    ]
    add(
        "single_currency_per_metric_grain",
        passed=not mixed_groups,
        observed={"mixed_grain_count": len(mixed_groups), "sample": mixed_groups[:10]},
        expected={"currency_count_per_grain": 1},
        detail="Cross-currency values are never summed without an explicit exchange-rate version.",
    )

    if request.expected_row_count is None:
        add(
            "source_row_count_reconciliation",
            passed=None,
            observed={"actual": len(request.facts)},
            expected={"configured": False},
            detail="The source did not provide an expected row count.",
        )
    else:
        add(
            "source_row_count_reconciliation",
            passed=request.expected_row_count == len(request.facts),
            observed={"actual": len(request.facts)},
            expected={"actual": request.expected_row_count},
            detail="Normalized row count must match the source-side count.",
        )

    _add_amount_check(
        add,
        code="source_gross_sales_reconciliation",
        actual=actual_gross_sales,
        expected=request.expected_gross_sales,
        tolerance=request.reconciliation_tolerance,
    )
    _add_amount_check(
        add,
        code="source_ad_spend_reconciliation",
        actual=actual_ad_spend,
        expected=request.expected_ad_spend,
        tolerance=request.reconciliation_tolerance,
    )

    version_issues = _source_version_issues(db, request=request)
    add(
        "source_version_immutability",
        passed=not version_issues,
        observed={"conflict_count": len(version_issues), "sample": version_issues[:20]},
        expected={"conflict_count": 0},
        detail="One source version cannot change content or roll back a newer observed fact.",
    )
    return checks


def _add_amount_check(
    add: Any,
    *,
    code: str,
    actual: Decimal,
    expected: Decimal | None,
    tolerance: Decimal,
) -> None:
    if expected is None:
        add(
            code,
            passed=None,
            observed={"actual": str(actual)},
            expected={"configured": False},
            detail="The source did not provide an amount total for reconciliation.",
        )
        return
    difference = abs(actual - expected)
    add(
        code,
        passed=difference <= tolerance,
        observed={"actual": str(actual), "absolute_difference": str(difference)},
        expected={"actual": str(expected), "tolerance": str(tolerance)},
        detail="Decimal source totals must reconcile within the declared absolute tolerance.",
    )


def _source_version_issues(
    db: Session,
    *,
    request: BiIngestionBatchCreate,
) -> list[dict[str, str]]:
    if not request.facts:
        return []
    external_ids = sorted({item.external_id for item in request.facts})
    existing = db.exec(
        select(BiDailyCommerceFact).where(
            BiDailyCommerceFact.tenant_id == request.tenant_id,
            BiDailyCommerceFact.source_key == request.source_key,
            BiDailyCommerceFact.external_id.in_(external_ids),
        )
    ).all()
    versions = {(row.external_id, row.source_version): row for row in existing}
    current = {
        row.external_id: row
        for row in sorted(existing, key=lambda item: (item.source_observed_at, item.created_at))
        if row.is_current
    }
    issues: list[dict[str, str]] = []
    for item in request.facts:
        digest = _fact_digest(item)
        exact = versions.get((item.external_id, item.source_version))
        if exact is not None and exact.content_digest != digest:
            issues.append({"external_id": item.external_id, "reason": "version_content_changed"})
            continue
        if exact is not None and not exact.is_current:
            issues.append({"external_id": item.external_id, "reason": "superseded_source_version"})
            continue
        active = current.get(item.external_id)
        if active is not None and _utc(item.source_observed_at) < _utc(active.source_observed_at):
            issues.append({"external_id": item.external_id, "reason": "older_observation"})
    return issues


def _publish_facts(
    db: Session,
    *,
    batch: BiIngestionBatch,
    request: BiIngestionBatchCreate,
    previous_batch_ids: set[str],
) -> list[str]:
    input_external_ids = {item.external_id for item in request.facts}
    current_window = []
    if request.snapshot_mode == "full_window" and previous_batch_ids:
        current_window = db.exec(
            select(BiDailyCommerceFact).where(
                BiDailyCommerceFact.tenant_id == request.tenant_id,
                BiDailyCommerceFact.source_key == request.source_key,
                BiDailyCommerceFact.batch_id.in_(sorted(previous_batch_ids)),
                BiDailyCommerceFact.is_current.is_(True),
            )
        ).all()
        for row in current_window:
            if row.external_id not in input_external_ids:
                row.is_current = False
                db.add(row)

    existing = (
        db.exec(
            select(BiDailyCommerceFact).where(
                BiDailyCommerceFact.tenant_id == request.tenant_id,
                BiDailyCommerceFact.source_key == request.source_key,
                BiDailyCommerceFact.external_id.in_(sorted(input_external_ids)),
            )
        ).all()
        if input_external_ids
        else []
    )
    versions = {(row.external_id, row.source_version): row for row in existing}
    current_by_external = {row.external_id: row for row in existing if row.is_current}
    published: list[str] = []
    for item in request.facts:
        current = current_by_external.get(item.external_id)
        exact = versions.get((item.external_id, item.source_version))
        if exact is not None:
            current_by_external[item.external_id] = exact
            published.append(exact.id)
            continue
        if current is not None:
            current.is_current = False
            db.add(current)
        row = BiDailyCommerceFact(
            tenant_id=request.tenant_id,
            batch_id=batch.id,
            source_key=request.source_key,
            external_id=item.external_id,
            source_version=item.source_version,
            content_digest=_fact_digest(item),
            replaces_fact_id=current.id if current is not None else None,
            business_date=item.business_date,
            brand_id=item.brand_id,
            store_id=item.store_id,
            platform=item.platform,
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            currency=item.currency,
            gross_sales=item.gross_sales,
            refund_amount=item.refund_amount,
            ad_spend=item.ad_spend,
            attributed_ad_sales=item.attributed_ad_sales,
            impressions=item.impressions,
            clicks=item.clicks,
            orders=item.orders,
            available_inventory=item.available_inventory,
            rolling_units_sold=item.rolling_units_sold,
            rolling_window_days=item.rolling_window_days,
            source_observed_at=_utc(item.source_observed_at),
        )
        db.add(row)
        current_by_external[item.external_id] = row
        published.append(row.id)
    db.flush()
    return published


def _ensure_metric_definitions(
    db: Session,
    *,
    tenant_id: str,
    user: User,
) -> dict[str, BiMetricDefinition]:
    rows = db.exec(
        select(BiMetricDefinition).where(
            BiMetricDefinition.tenant_id == tenant_id,
            BiMetricDefinition.version == _METRIC_VERSION,
        )
    ).all()
    by_code = {row.code: row for row in rows}
    for code, contract in _METRIC_CONTRACTS.items():
        if code in by_code:
            continue
        row = BiMetricDefinition(
            tenant_id=tenant_id,
            code=code,
            version=_METRIC_VERSION,
            name=contract["name"],
            formula=contract["formula"],
            grain="tenant_day,store_day",
            business_timezone="source_business_timezone",
            currency_policy=contract["currency_policy"],
            attribution_window_days=7,
            created_by_user_id=user.id,
        )
        db.add(row)
        by_code[code] = row
    db.flush()
    return by_code


def _rebuild_metrics(
    db: Session,
    *,
    batch: BiIngestionBatch,
    request: BiIngestionBatchCreate,
    definitions: dict[str, BiMetricDefinition],
    window_start: datetime,
    window_end: datetime,
) -> None:
    local_start, local_end = _local_date_bounds(
        window_start,
        window_end,
        request.business_timezone,
    )
    affected_dates = (
        set(_date_range(local_start, local_end))
        if request.snapshot_mode == "full_window"
        else {item.business_date for item in request.facts}
    )
    if not affected_dates:
        return
    current_metrics = db.exec(
        select(BiDailyMetric).where(
            BiDailyMetric.tenant_id == request.tenant_id,
            BiDailyMetric.source_key == request.source_key,
            BiDailyMetric.business_date.in_(sorted(affected_dates)),
            BiDailyMetric.is_current.is_(True),
        )
    ).all()
    for metric in current_metrics:
        metric.is_current = False
        db.add(metric)

    facts = db.exec(
        select(BiDailyCommerceFact).where(
            BiDailyCommerceFact.tenant_id == request.tenant_id,
            BiDailyCommerceFact.source_key == request.source_key,
            BiDailyCommerceFact.business_date.in_(sorted(affected_dates)),
            BiDailyCommerceFact.is_current.is_(True),
        )
    ).all()
    groups: dict[tuple[Any, ...], list[BiDailyCommerceFact]] = defaultdict(list)
    for fact in facts:
        groups[(fact.business_date, fact.currency, "tenant", request.tenant_id, "", "", "")].append(
            fact
        )
        groups[
            (
                fact.business_date,
                fact.currency,
                "store",
                fact.store_id,
                fact.brand_id,
                fact.store_id,
                fact.platform,
            )
        ].append(fact)

    now = _now()
    for grain, grain_facts in groups.items():
        business_date, source_currency, entity_type, entity_id, brand_id, store_id, platform = grain
        values = _metric_values(grain_facts)
        latest_observed = max(_utc(item.source_observed_at) for item in grain_facts)
        freshness = "fresh" if now - latest_observed <= timedelta(minutes=60) else "stale"
        fact_ids = sorted(item.id for item in grain_facts)
        evidence = {
            "batch_id": batch.id,
            "source_key": request.source_key,
            "business_date": business_date.isoformat(),
            "brand_id": brand_id,
            "store_id": store_id,
            "platform": platform,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "fact_count": len(fact_ids),
            "fact_ids": fact_ids[:100],
            "fact_ids_truncated": len(fact_ids) > 100,
            "fact_ids_digest": hashlib.sha256("\n".join(fact_ids).encode()).hexdigest(),
            "metric_definition_version": _METRIC_VERSION,
            "business_timezone": request.business_timezone,
        }
        for code, (value, null_reason) in values.items():
            definition = definitions[code]
            db.add(
                BiDailyMetric(
                    tenant_id=request.tenant_id,
                    batch_id=batch.id,
                    metric_definition_id=definition.id,
                    metric_code=code,
                    metric_definition_version=definition.version,
                    business_date=business_date,
                    source_key=request.source_key,
                    brand_id=brand_id,
                    store_id=store_id,
                    platform=platform,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    # Ratios retain the calculation currency as scope metadata even though
                    # the numeric value itself is dimensionless.
                    currency=source_currency,
                    value=value,
                    null_reason=null_reason,
                    freshness_status=freshness,
                    latest_source_observed_at=latest_observed,
                    evidence_json=evidence,
                )
            )
    db.flush()


def _metric_values(
    facts: list[BiDailyCommerceFact],
) -> dict[str, tuple[Decimal | None, str | None]]:
    gross_sales = sum((item.gross_sales for item in facts), Decimal(0))
    refunds = sum((item.refund_amount for item in facts), Decimal(0))
    net_sales = gross_sales - refunds
    ad_spend = sum((item.ad_spend for item in facts), Decimal(0))
    attributed_sales = sum((item.attributed_ad_sales for item in facts), Decimal(0))
    impressions = sum(item.impressions for item in facts)
    clicks = sum(item.clicks for item in facts)
    orders = sum(item.orders for item in facts)
    rolling_units_sold = sum(item.rolling_units_sold for item in facts)
    weighted_inventory_days = sum(
        item.available_inventory * item.rolling_window_days for item in facts
    )
    return {
        "gmv": (_quantize(net_sales), None),
        "ctr": _divide(Decimal(clicks), Decimal(impressions)),
        "cvr": _divide(Decimal(orders), Decimal(clicks)),
        "cpc": _divide(ad_spend, Decimal(clicks)),
        "acos": _divide(ad_spend, attributed_sales),
        "tacos": _divide(ad_spend, net_sales),
        "roas": _divide(attributed_sales, ad_spend),
        "inventory_days": _divide(Decimal(weighted_inventory_days), Decimal(rolling_units_sold)),
    }


def _divide(numerator: Decimal, denominator: Decimal) -> tuple[Decimal | None, str | None]:
    if denominator == 0:
        return None, "denominator_zero"
    return _quantize(numerator / denominator), None


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_SCALE, rounding=ROUND_HALF_UP)


def _batch_digest(request: BiIngestionBatchCreate) -> str:
    payload = request.model_dump(mode="json")
    payload["window_start"] = _utc(request.window_start).isoformat()
    payload["window_end"] = _utc(request.window_end).isoformat()
    normalized_facts = []
    for item in request.facts:
        fact = item.model_dump(mode="json")
        fact["source_observed_at"] = _utc(item.source_observed_at).isoformat()
        normalized_facts.append(fact)
    payload["facts"] = sorted(
        normalized_facts,
        key=lambda item: (item["external_id"], item["source_version"]),
    )
    return _json_digest(payload)


def _fact_digest(item: BiDailyCommerceFactInput) -> str:
    payload = item.model_dump(mode="json")
    payload["source_observed_at"] = _utc(item.source_observed_at).isoformat()
    return _json_digest(payload)


def _json_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _recover_concurrent_batch(
    db: Session,
    *,
    request: BiIngestionBatchCreate,
    input_digest: str,
    window_start: datetime,
    window_end: datetime,
    error: IntegrityError,
) -> BiIngestionBatchRead:
    db.rollback()
    set_tenant_context(db, request.tenant_id)
    existing = db.exec(
        select(BiIngestionBatch).where(
            BiIngestionBatch.tenant_id == request.tenant_id,
            BiIngestionBatch.source_key == request.source_key,
            BiIngestionBatch.window_start == window_start,
            BiIngestionBatch.window_end == window_end,
            BiIngestionBatch.input_digest == input_digest,
        )
    ).first()
    if existing is not None:
        return _read_batch(db, existing)
    raise HTTPException(
        status_code=409,
        detail="Another BI payload won this source window; retry after reading the current batch",
    ) from error


def _local_date_bounds(
    window_start: datetime,
    window_end: datetime,
    timezone_name: str,
) -> tuple[date, date]:
    timezone = ZoneInfo(timezone_name)
    local_start = _utc(window_start).astimezone(timezone)
    local_end = _utc(window_end).astimezone(timezone)
    end_date = local_end.date()
    if local_end.time() != datetime.min.time():
        end_date += timedelta(days=1)
    return local_start.date(), end_date


def _date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days)]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _now() -> datetime:
    return datetime.now(UTC)


def _read_batch(db: Session, row: BiIngestionBatch) -> BiIngestionBatchRead:
    checks = db.exec(
        select(BiDataQualityCheck)
        .where(
            BiDataQualityCheck.tenant_id == row.tenant_id,
            BiDataQualityCheck.batch_id == row.id,
        )
        .order_by(BiDataQualityCheck.check_code)
    ).all()
    facts = db.exec(
        select(BiDailyCommerceFact).where(
            BiDailyCommerceFact.tenant_id == row.tenant_id,
            BiDailyCommerceFact.batch_id == row.id,
        )
    ).all()
    metrics = db.exec(
        select(BiDailyMetric).where(
            BiDailyMetric.tenant_id == row.tenant_id,
            BiDailyMetric.batch_id == row.id,
        )
    ).all()
    return BiIngestionBatchRead(
        id=row.id,
        tenant_id=row.tenant_id,
        source_key=row.source_key,
        window_start=row.window_start,
        window_end=row.window_end,
        business_timezone=row.business_timezone,
        snapshot_mode=row.snapshot_mode,
        input_digest=row.input_digest,
        status=row.status,
        quality_status=row.quality_status,
        row_count=row.row_count,
        accepted_count=row.accepted_count,
        rejected_count=row.rejected_count,
        expected_row_count=row.expected_row_count,
        expected_gross_sales=row.expected_gross_sales,
        expected_ad_spend=row.expected_ad_spend,
        actual_gross_sales=row.actual_gross_sales,
        actual_ad_spend=row.actual_ad_spend,
        reconciliation_tolerance=row.reconciliation_tolerance,
        metric_definition_version=row.metric_definition_version,
        latest_source_observed_at=row.latest_source_observed_at,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        completed_at=row.completed_at,
        fact_count=len(facts),
        metric_count=len(metrics),
        quality_checks=[
            BiQualityCheckRead(
                id=check.id,
                check_code=check.check_code,
                status=check.status,
                severity=check.severity,
                observed=dict(check.observed_json or {}),
                expected=dict(check.expected_json or {}),
                detail=check.detail,
                created_at=check.created_at,
            )
            for check in checks
        ],
    )


def _read_metric(row: BiDailyMetric) -> BiDailyMetricRead:
    return BiDailyMetricRead(
        id=row.id,
        batch_id=row.batch_id,
        metric_definition_id=row.metric_definition_id,
        metric_code=row.metric_code,
        metric_definition_version=row.metric_definition_version,
        business_date=row.business_date,
        source_key=row.source_key,
        brand_id=row.brand_id,
        store_id=row.store_id,
        platform=row.platform,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        currency=row.currency,
        value=row.value,
        null_reason=row.null_reason,
        freshness_status=row.freshness_status,
        latest_source_observed_at=row.latest_source_observed_at,
        evidence=dict(row.evidence_json or {}),
        created_at=row.created_at,
    )


def _read_fact(row: BiDailyCommerceFact) -> BiDailyCommerceFactRead:
    return BiDailyCommerceFactRead(
        id=row.id,
        batch_id=row.batch_id,
        source_key=row.source_key,
        external_id=row.external_id,
        source_version=row.source_version,
        content_digest=row.content_digest,
        replaces_fact_id=row.replaces_fact_id,
        is_current=row.is_current,
        business_date=row.business_date,
        brand_id=row.brand_id,
        store_id=row.store_id,
        platform=row.platform,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        currency=row.currency,
        gross_sales=row.gross_sales,
        refund_amount=row.refund_amount,
        ad_spend=row.ad_spend,
        attributed_ad_sales=row.attributed_ad_sales,
        impressions=row.impressions,
        clicks=row.clicks,
        orders=row.orders,
        available_inventory=row.available_inventory,
        rolling_units_sold=row.rolling_units_sold,
        rolling_window_days=row.rolling_window_days,
        source_observed_at=row.source_observed_at,
        created_at=row.created_at,
    )


def _require_manager(user: User, tenant_id: str) -> None:
    _require_role(user, tenant_id, _MANAGER_ROLES, "BI data administrator role is required")


def _require_reader(user: User, tenant_id: str) -> None:
    _require_role(user, tenant_id, _READER_ROLES, "BI reader role is required")


def _require_role(user: User, tenant_id: str, allowed: set[str], detail: str) -> None:
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access is forbidden")
    role = "platform_admin" if user.role == "admin" else (user.business_role or "")
    if role not in allowed:
        raise HTTPException(status_code=403, detail=detail)
