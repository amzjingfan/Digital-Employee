from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.advertising.schema import PdcaSearchTermActionRead, PdcaSearchTermRunRead
from app.advertising.service import authorize_advertising_scope
from app.config import get_settings
from app.db.models import (
    CommerceGovernanceEvent,
    PdcaAction,
    PdcaFactSearchTerm,
    PdcaIdempotencyKey,
    PdcaSearchTermRun,
    User,
)

MAPPING_VERSION = "amazon-search-term-csv.v1"
RULE_VERSION = "pdca-search-term-rules.v1"
METRIC_DEFINITION_VERSION = "pdca-metrics.v1"
_ZERO = Decimal(0)
_MONEY_QUANTUM = Decimal("0.000001")
_RATIO_QUANTUM = Decimal("0.000001")
_MAX_NUMERIC_VALUE = Decimal(1000000000000)

_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("date", "report date", "日期"),
    "campaign_name": ("campaign name", "campaign", "广告活动名称", "广告活动"),
    "campaign_id": ("campaign id", "campaignid", "广告活动 id", "广告活动id"),
    "ad_group_name": ("ad group name", "ad group", "广告组名称", "广告组"),
    "ad_group_id": ("ad group id", "adgroupid", "广告组 id", "广告组id"),
    "targeting": ("targeting", "target", "投放", "投放对象"),
    "match_type": ("match type", "matchtype", "匹配类型"),
    "search_term": (
        "customer search term",
        "search term",
        "customer search term text",
        "客户搜索词",
        "搜索词",
    ),
    "impressions": ("impressions", "impression", "展示量", "曝光量"),
    "clicks": ("clicks", "click", "点击量", "点击次数"),
    "spend": ("spend", "cost", "花费", "广告花费"),
    "sales": ("sales", "sales 7 day", "attributed sales", "销售额", "广告销售额"),
    "orders": ("orders", "orders 7 day", "purchases", "订单量", "订单数"),
}


def create_pdca_search_term_run(
    db: Session,
    *,
    tenant_id: str,
    ad_account_resource_id: str,
    store_resource_id: str | None,
    idempotency_key: str,
    filename: str,
    content_type: str | None,
    data: bytes,
    target_acos: Decimal,
    currency: str,
    explicit_rerun: bool = False,
    user: User,
) -> PdcaSearchTermRunRead:
    """Parse, aggregate and persist one rules-only Amazon search-term diagnosis.

    This boundary never creates a HighRiskActionRequest or BusinessActionExecution.
    Every generated action is durable advice that must be reviewed and applied outside
    this P0 workflow.
    """

    authorize_advertising_scope(
        db,
        tenant_id=tenant_id,
        user=user,
        ad_account_resource_id=ad_account_resource_id,
        store_resource_id=store_resource_id,
    )
    normalized_key = idempotency_key.strip()
    if len(normalized_key) < 8 or len(normalized_key) > 160:
        raise HTTPException(status_code=422, detail="Idempotency-Key must be 8-160 characters")
    normalized_currency = currency.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", normalized_currency):
        raise HTTPException(status_code=422, detail="Currency must be a three-letter ISO code")
    try:
        normalized_target = _decimal_value(target_acos, "target_acos")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if normalized_target <= 0 or normalized_target > 1:
        raise HTTPException(status_code=422, detail="target_acos must be greater than 0 and at most 1")

    source_sha256, mapping, rows = _parse_search_term_csv(
        filename=filename,
        content_type=content_type,
        data=data,
    )
    input_digest = _digest(
        {
            "tenant_id": tenant_id,
            "ad_account_resource_id": ad_account_resource_id,
            "store_resource_id": store_resource_id,
            "source_sha256": source_sha256,
            "target_acos": _decimal_text(normalized_target),
            "currency": normalized_currency,
            "mapping_version": MAPPING_VERSION,
            "rule_version": RULE_VERSION,
            "metric_definition_version": METRIC_DEFINITION_VERSION,
        }
    )
    existing = _run_for_idempotency_key(
        db,
        tenant_id=tenant_id,
        idempotency_key=normalized_key,
        input_digest=input_digest,
    )
    if existing:
        db.commit()
        return _run_read(db, existing)

    latest_snapshot = db.exec(
        select(PdcaSearchTermRun)
        .where(
            PdcaSearchTermRun.tenant_id == tenant_id,
            PdcaSearchTermRun.input_digest == input_digest,
        )
        .order_by(PdcaSearchTermRun.attempt.desc())
    ).first()
    if latest_snapshot and not explicit_rerun:
        bound = _bind_idempotency_key(
            db,
            tenant_id=tenant_id,
            idempotency_key=normalized_key,
            input_digest=input_digest,
            run=latest_snapshot,
        )
        return _run_read(db, bound)
    attempt = (latest_snapshot.attempt + 1) if latest_snapshot else 1

    aggregates = _aggregate_rows(rows)
    summary = _account_summary(aggregates)
    warnings = [
        "Product attribution evidence was not supplied; precise-negative actions are disabled.",
        "Brand whitelist evidence was not supplied; high-spend zero-order terms require manual review.",
        "Optional share-of-voice, advertised-product and total-traffic reports were not supplied.",
        "This rules-only run creates advice and never executes an Amazon Ads write.",
    ]
    run = PdcaSearchTermRun(
        tenant_id=tenant_id,
        idempotency_key=normalized_key,
        ad_account_resource_id=ad_account_resource_id,
        store_resource_id=store_resource_id,
        source_sha256=source_sha256,
        input_digest=input_digest,
        attempt=attempt,
        mapping_version=MAPPING_VERSION,
        rule_version=RULE_VERSION,
        metric_definition_version=METRIC_DEFINITION_VERSION,
        target_acos=normalized_target,
        currency=normalized_currency,
        source_row_count=len(rows),
        fact_count=len(aggregates),
        action_count=len(aggregates),
        quality_score=70,
        mapping_snapshot_json=mapping,
        summary_json=summary,
        warnings_json=warnings,
        external_execution_allowed=False,
        created_by_user_id=user.id,
    )
    db.add(run)
    db.add(
        PdcaIdempotencyKey(
            tenant_id=tenant_id,
            idempotency_key=normalized_key,
            run_id=run.id,
            input_digest=input_digest,
        )
    )
    total_spend = sum((item["spend"] for item in aggregates), start=_ZERO)
    for aggregate in aggregates:
        fact = _fact_row(run, aggregate)
        db.add(fact)
        db.add(_action_row(run, fact, aggregate, total_spend, normalized_target))
    db.add(
        CommerceGovernanceEvent(
            tenant_id=tenant_id,
            aggregate_type="pdca_search_term_run",
            aggregate_id=run.id,
            event_type="rules_only_diagnosis_succeeded",
            actor_id=user.id,
            actor_business_role=user.business_role,
            detail_json={
                "source_sha256": source_sha256,
                "input_digest": input_digest,
                "attempt": attempt,
                "mapping_version": MAPPING_VERSION,
                "rule_version": RULE_VERSION,
                "source_row_count": len(rows),
                "fact_count": len(aggregates),
                "action_count": len(aggregates),
                "external_execution_allowed": False,
            },
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = _run_for_idempotency_key(
            db,
            tenant_id=tenant_id,
            idempotency_key=normalized_key,
            input_digest=input_digest,
        )
        if winner:
            return _run_read(db, winner)
        winner = db.exec(
            select(PdcaSearchTermRun).where(
                PdcaSearchTermRun.tenant_id == tenant_id,
                PdcaSearchTermRun.input_digest == input_digest,
                PdcaSearchTermRun.attempt == attempt,
            )
        ).first()
        if winner:
            bound = _bind_idempotency_key(
                db,
                tenant_id=tenant_id,
                idempotency_key=normalized_key,
                input_digest=input_digest,
                run=winner,
            )
            return _run_read(db, bound)
        raise
    db.refresh(run)
    return _run_read(db, run)


def _run_for_idempotency_key(
    db: Session,
    *,
    tenant_id: str,
    idempotency_key: str,
    input_digest: str,
) -> PdcaSearchTermRun | None:
    binding = db.exec(
        select(PdcaIdempotencyKey).where(
            PdcaIdempotencyKey.tenant_id == tenant_id,
            PdcaIdempotencyKey.idempotency_key == idempotency_key,
        )
    ).first()
    if not binding:
        return None
    if binding.input_digest != input_digest:
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key was already used for a different PDCA input snapshot",
        )
    return db.exec(
        select(PdcaSearchTermRun).where(
            PdcaSearchTermRun.tenant_id == tenant_id,
            PdcaSearchTermRun.id == binding.run_id,
        )
    ).one()


def _bind_idempotency_key(
    db: Session,
    *,
    tenant_id: str,
    idempotency_key: str,
    input_digest: str,
    run: PdcaSearchTermRun,
) -> PdcaSearchTermRun:
    existing = _run_for_idempotency_key(
        db,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        input_digest=input_digest,
    )
    if existing:
        return existing
    db.add(
        PdcaIdempotencyKey(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            run_id=run.id,
            input_digest=input_digest,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = _run_for_idempotency_key(
            db,
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            input_digest=input_digest,
        )
        if winner:
            return winner
        raise
    return run


def list_pdca_search_term_runs(
    db: Session,
    *,
    tenant_id: str,
    ad_account_resource_id: str,
    store_resource_id: str | None,
    user: User,
) -> list[PdcaSearchTermRunRead]:
    authorize_advertising_scope(
        db,
        tenant_id=tenant_id,
        ad_account_resource_id=ad_account_resource_id,
        store_resource_id=store_resource_id,
        user=user,
    )
    filters = [
        PdcaSearchTermRun.tenant_id == tenant_id,
        PdcaSearchTermRun.ad_account_resource_id == ad_account_resource_id,
    ]
    if store_resource_id:
        filters.append(PdcaSearchTermRun.store_resource_id == store_resource_id)
    else:
        filters.append(PdcaSearchTermRun.store_resource_id.is_(None))
    rows = db.exec(
        select(PdcaSearchTermRun)
        .where(*filters)
        .order_by(PdcaSearchTermRun.created_at.desc(), PdcaSearchTermRun.attempt.desc())
        .limit(100)
    ).all()
    return [_run_read(db, row) for row in rows]


def _parse_search_term_csv(
    *, filename: str, content_type: str | None, data: bytes
) -> tuple[str, dict[str, str], list[dict[str, Any]]]:
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="This P0 slice accepts CSV search-term reports only")
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded search-term report is empty")
    if len(data) > get_settings().pdca_upload_max_bytes:
        raise HTTPException(status_code=413, detail="Search-term report exceeds the configured limit")
    if b"\x00" in data[:8192]:
        raise HTTPException(status_code=415, detail="Binary content is not a supported CSV report")
    allowed_types = {
        "application/csv",
        "application/octet-stream",
        "application/vnd.ms-excel",
        "text/csv",
        "text/plain",
    }
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type and normalized_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Unsupported CSV content type")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV must be UTF-8 encoded") from exc
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",\t;")
    except csv.Error as exc:
        raise HTTPException(status_code=422, detail="CSV delimiter could not be identified") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""), dialect=dialect)
    if not reader.fieldnames:
        raise HTTPException(status_code=422, detail="CSV header is missing")
    mapping = _resolve_mapping(reader.fieldnames)
    parsed: list[dict[str, Any]] = []
    for source_row, raw in enumerate(reader, start=2):
        if len(parsed) >= get_settings().pdca_upload_max_rows:
            raise HTTPException(status_code=413, detail="Search-term report exceeds the row limit")
        if not any(str(value or "").strip() for value in raw.values()):
            continue
        parsed.append(_parse_row(raw, mapping, source_row))
    if not parsed:
        raise HTTPException(status_code=422, detail="CSV contains no usable search-term rows")
    return f"sha256:{hashlib.sha256(data).hexdigest()}", mapping, parsed


def _resolve_mapping(fieldnames: list[str]) -> dict[str, str]:
    normalized: dict[str, list[str]] = defaultdict(list)
    for original in fieldnames:
        normalized[_normalize_header(original)].append(original)
    mapping: dict[str, str] = {}
    missing: list[str] = []
    ambiguous: list[str] = []
    for canonical, aliases in _COLUMN_ALIASES.items():
        candidates: list[str] = []
        for alias in aliases:
            candidates.extend(normalized.get(_normalize_header(alias), []))
        if not candidates:
            missing.append(canonical)
        elif len(candidates) > 1:
            ambiguous.append(canonical)
        else:
            mapping[canonical] = candidates[0]
    if missing or ambiguous:
        details: list[str] = []
        if missing:
            details.append(f"missing required fields: {', '.join(missing)}")
        if ambiguous:
            details.append(f"ambiguous fields: {', '.join(ambiguous)}")
        detected = ", ".join(item.strip()[:80] for item in fieldnames[:50])
        details.append(f"detected headers: {detected}")
        raise HTTPException(status_code=422, detail="; ".join(details))
    return mapping


def _parse_row(raw: dict[str, Any], mapping: dict[str, str], source_row: int) -> dict[str, Any]:
    values = {key: str(raw.get(column) or "").strip() for key, column in mapping.items()}
    missing = [
        key
        for key in (
            "date",
            "campaign_name",
            "campaign_id",
            "ad_group_name",
            "ad_group_id",
            "targeting",
            "match_type",
            "search_term",
        )
        if not values[key]
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"CSV row {source_row} has empty required values: {', '.join(missing)}",
        )
    try:
        observed_date = _date_value(values["date"])
        impressions = _integer_value(values["impressions"], "impressions")
        clicks = _integer_value(values["clicks"], "clicks")
        orders = _integer_value(values["orders"], "orders")
        spend = _money_value(values["spend"], "spend")
        sales = _money_value(values["sales"], "sales")
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"CSV row {source_row}: {exc}") from exc
    if min(impressions, clicks, orders) < 0 or min(spend, sales) < 0:
        raise HTTPException(status_code=422, detail=f"CSV row {source_row}: metrics cannot be negative")
    return {
        **values,
        "date": observed_date,
        "impressions": impressions,
        "clicks": clicks,
        "orders": orders,
        "spend": spend,
        "sales": sales,
        "match_type": _normalize_match_type(values["match_type"]),
        "search_term_norm": _normalize_search_term(values["search_term"]),
        "source_row": source_row,
    }


def _aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregated: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = (
            row["campaign_id"],
            row["ad_group_id"],
            row["targeting"],
            row["match_type"],
            row["search_term_norm"],
        )
        item = aggregated.get(key)
        if not item:
            item = {
                **row,
                "date_start": row["date"],
                "date_end": row["date"],
                "source_rows": [],
            }
            aggregated[key] = item
        else:
            item["date_start"] = min(item["date_start"], row["date"])
            item["date_end"] = max(item["date_end"], row["date"])
            for metric in ("impressions", "clicks", "orders", "spend", "sales"):
                item[metric] += row[metric]
        item["source_rows"].append(row["source_row"])
    result = list(aggregated.values())
    result.sort(key=lambda item: (item["campaign_id"], item["ad_group_id"], item["search_term_norm"]))
    return result


def _account_summary(aggregates: list[dict[str, Any]]) -> dict[str, Any]:
    impressions = sum(item["impressions"] for item in aggregates)
    clicks = sum(item["clicks"] for item in aggregates)
    orders = sum(item["orders"] for item in aggregates)
    spend = sum((item["spend"] for item in aggregates), start=_ZERO)
    sales = sum((item["sales"] for item in aggregates), start=_ZERO)
    return {
        "impressions": impressions,
        "clicks": clicks,
        "orders": orders,
        "spend": _decimal_text(spend),
        "sales": _decimal_text(sales),
        "ctr": _ratio(clicks, impressions, "zero_impressions"),
        "cpc": _ratio(spend, clicks, "zero_clicks"),
        "cvr": _ratio(orders, clicks, "zero_clicks"),
        "acos": _ratio(spend, sales, "zero_sales"),
        "roas": _ratio(sales, spend, "zero_spend"),
    }


def _fact_row(run: PdcaSearchTermRun, aggregate: dict[str, Any]) -> PdcaFactSearchTerm:
    grain_key = _digest(
        [
            aggregate["campaign_id"],
            aggregate["ad_group_id"],
            aggregate["targeting"],
            aggregate["match_type"],
            aggregate["search_term_norm"],
        ]
    )
    metrics = {
        "ctr": _ratio(aggregate["clicks"], aggregate["impressions"], "zero_impressions"),
        "cpc": _ratio(aggregate["spend"], aggregate["clicks"], "zero_clicks"),
        "cvr": _ratio(aggregate["orders"], aggregate["clicks"], "zero_clicks"),
        "acos": _ratio(aggregate["spend"], aggregate["sales"], "zero_sales"),
        "roas": _ratio(aggregate["sales"], aggregate["spend"], "zero_spend"),
    }
    return PdcaFactSearchTerm(
        tenant_id=run.tenant_id,
        run_id=run.id,
        grain_key=grain_key,
        date_start=aggregate["date_start"],
        date_end=aggregate["date_end"],
        campaign_id=aggregate["campaign_id"],
        campaign_name=aggregate["campaign_name"],
        ad_group_id=aggregate["ad_group_id"],
        ad_group_name=aggregate["ad_group_name"],
        targeting=aggregate["targeting"],
        match_type=aggregate["match_type"],
        search_term=aggregate["search_term"],
        search_term_norm=aggregate["search_term_norm"],
        impressions=aggregate["impressions"],
        clicks=aggregate["clicks"],
        spend=aggregate["spend"],
        sales=aggregate["sales"],
        orders=aggregate["orders"],
        metric_snapshot_json=metrics,
        evidence_json={
            "source_type": run.source_type,
            "source_record_id": grain_key,
            "ingestion_batch_id": run.id,
            "observed_at": aggregate["date_end"].isoformat(),
            "metric_definition_version": run.metric_definition_version,
            "rule_or_prompt_version": run.rule_version,
            "freshness_status": "uploaded_snapshot",
            "source_sha256": run.source_sha256,
        },
        source_row_refs_json=aggregate["source_rows"],
    )


def _action_row(
    run: PdcaSearchTermRun,
    fact: PdcaFactSearchTerm,
    aggregate: dict[str, Any],
    total_spend: Decimal,
    target_acos: Decimal,
) -> PdcaAction:
    clicks = aggregate["clicks"]
    orders = aggregate["orders"]
    spend = aggregate["spend"]
    sales = aggregate["sales"]
    match_type = aggregate["match_type"]
    acos = spend / sales if sales else None
    spend_share = spend / total_spend if total_spend else _ZERO
    score = min(100, 30 + int((spend_share * 50).to_integral_value()) + min(clicks, 20))
    priority = "low"
    action_type = "observe"
    rationale = "Current evidence does not cross a protected deterministic action threshold."
    expected = "Collect another measurement window without changing account state."
    risk = "Do not infer a zero metric where its denominator is zero."
    verification_days = 7
    if orders == 0 and clicks >= 8:
        action_type = "manual_review"
        priority = "high"
        score = max(80, score)
        rationale = "High-click traffic has no attributed orders, but product and brand evidence is absent."
        expected = "Confirm relevance before choosing any negative keyword or bid change."
        risk = "A direct negative could suppress relevant or protected brand traffic."
    elif orders == 0 and clicks >= 4 and match_type in {"auto", "broad"}:
        action_type = "lower_bid"
        priority = "medium"
        score = max(60, score)
        rationale = "Broad or automatic traffic has repeated clicks without an attributed order."
        expected = "A manually reviewed small bid reduction may reduce inefficient exploration spend."
        risk = "Validate product relevance and current bid in Amazon Ads before any change."
    elif orders >= 2 and acos is not None and acos <= target_acos:
        action_type = "protect_scale" if match_type == "exact" else "convert_exact"
        priority = "medium"
        score = max(65, score)
        rationale = "The term has repeat orders and ACoS at or below the frozen target."
        expected = "Protect proven traffic or evaluate an exact-match structure without removing discovery traffic."
        risk = "This is not a budget or bid instruction; inventory and profit evidence remain required."
        verification_days = 14
    return PdcaAction(
        tenant_id=run.tenant_id,
        run_id=run.id,
        fact_id=fact.id,
        action_type=action_type,
        priority=priority,
        must_do_score=score,
        rationale=rationale,
        evidence_json={
            "fact_id": fact.id,
            "source_sha256": run.source_sha256,
            "source_row_count": len(aggregate["source_rows"]),
            "rule_version": run.rule_version,
        },
        thresholds_json={
            "target_acos": _decimal_text(target_acos),
            "manual_review_min_clicks": 8,
            "lower_bid_min_clicks": 4,
            "profitable_min_orders": 2,
            "product_attribution_required_for_negative": True,
        },
        current_values_json={
            "clicks": clicks,
            "orders": orders,
            "spend": _decimal_text(spend),
            "sales": _decimal_text(sales),
            "acos": _decimal_text(acos) if acos is not None else None,
            "acos_reason": None if acos is not None else "zero_sales",
            "match_type": match_type,
        },
        expected_effect=expected,
        risk_note=risk,
        verification_window_days=verification_days,
        execution_hint=(
            "Advice only: review evidence and, if appropriate, apply manually in Amazon Ads; "
            "this system did not execute a write."
        ),
        status="suggested",
        external_execution_allowed=False,
    )


def _run_read(db: Session, row: PdcaSearchTermRun) -> PdcaSearchTermRunRead:
    facts = db.exec(
        select(PdcaFactSearchTerm).where(
            PdcaFactSearchTerm.tenant_id == row.tenant_id,
            PdcaFactSearchTerm.run_id == row.id,
        )
    ).all()
    fact_by_id = {item.id: item for item in facts}
    actions = db.exec(
        select(PdcaAction)
        .where(PdcaAction.tenant_id == row.tenant_id, PdcaAction.run_id == row.id)
        .order_by(PdcaAction.must_do_score.desc())
        .limit(10)
    ).all()
    top_actions = []
    for action in actions:
        fact = fact_by_id[action.fact_id]
        top_actions.append(
            PdcaSearchTermActionRead(
                id=action.id,
                fact_id=action.fact_id,
                campaign_id=fact.campaign_id,
                ad_group_id=fact.ad_group_id,
                search_term=fact.search_term,
                match_type=fact.match_type,
                action_type=action.action_type,
                priority=action.priority,
                must_do_score=action.must_do_score,
                rationale=action.rationale,
                evidence=action.evidence_json,
                thresholds=action.thresholds_json,
                current_values=action.current_values_json,
                expected_effect=action.expected_effect,
                risk_note=action.risk_note,
                verification_window_days=action.verification_window_days,
                execution_hint=action.execution_hint,
                status="suggested",
                external_execution_allowed=False,
            )
        )
    return PdcaSearchTermRunRead(
        id=row.id,
        tenant_id=row.tenant_id,
        ad_account_resource_id=row.ad_account_resource_id,
        store_resource_id=row.store_resource_id,
        source_type="amazon_search_term_csv",
        source_label="local source file",
        source_sha256=row.source_sha256,
        input_digest=row.input_digest,
        attempt=row.attempt,
        mapping_version=row.mapping_version,
        rule_version=row.rule_version,
        metric_definition_version=row.metric_definition_version,
        mode="rules_only",
        state="succeeded",
        target_acos=_decimal_text(row.target_acos),
        currency=row.currency,
        source_row_count=row.source_row_count,
        fact_count=row.fact_count,
        action_count=row.action_count,
        quality_score=row.quality_score,
        mapping=row.mapping_snapshot_json,
        summary=row.summary_json,
        warnings=row.warnings_json,
        external_execution_allowed=False,
        top_actions=top_actions,
        created_at=row.created_at,
    )


def _ratio(numerator: int | Decimal, denominator: int | Decimal, reason: str) -> dict[str, Any]:
    if denominator == 0:
        return {"value": None, "reason": reason}
    value = (Decimal(numerator) / Decimal(denominator)).quantize(_RATIO_QUANTUM)
    return {"value": _decimal_text(value), "reason": None}


def _decimal_value(value: Any, name: str) -> Decimal:
    text = str(value).strip()
    if not re.fullmatch(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", text):
        raise ValueError(f"{name} must be a decimal number")
    try:
        parsed = Decimal(text.replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be a decimal number") from exc
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    return parsed


def _money_value(value: str, name: str) -> Decimal:
    parsed = _decimal_value(value, name)
    if abs(parsed) > _MAX_NUMERIC_VALUE:
        raise ValueError(f"{name} exceeds the supported numeric range")
    return parsed.quantize(_MONEY_QUANTUM)


def _integer_value(value: str, name: str) -> int:
    parsed = _decimal_value(value, name)
    if parsed != parsed.to_integral_value():
        raise ValueError(f"{name} must be an integer")
    if abs(parsed) > _MAX_NUMERIC_VALUE:
        raise ValueError(f"{name} exceeds the supported numeric range")
    return int(parsed)


def _date_value(value: str) -> date:
    normalized = value.replace("/", "-")
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        pass
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
    if match:
        try:
            return date(int(match[3]), int(match[1]), int(match[2]))
        except ValueError:
            pass
    raise ValueError("date must use YYYY-MM-DD, YYYY/MM/DD or MM/DD/YYYY")


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", value.strip().lower()).strip()


def _normalize_search_term(value: str) -> str:
    return " ".join(value.casefold().split())


def _normalize_match_type(value: str) -> str:
    normalized = _normalize_search_term(value)
    if normalized in {"automatic", "auto", "自动"}:
        return "auto"
    if normalized in {"exact", "exact match", "精准", "精确"}:
        return "exact"
    if normalized in {"phrase", "phrase match", "词组"}:
        return "phrase"
    if normalized in {"broad", "broad match", "广泛"}:
        return "broad"
    return normalized[:80]


def _decimal_text(value: Decimal) -> str:
    normalized = format(value, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def _digest(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


__all__ = ["create_pdca_search_term_run", "list_pdca_search_term_runs"]
