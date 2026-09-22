from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from typing import Any

from fastapi import Request
from pydantic import ValidationError

from app.db.models import TikTokFieldContract
from app.tiktok.schema import TikTokRecordedValidationRequest

MAX_RECORDED_REQUEST_BYTES = 2 * 1024 * 1024
ATTESTATION_VERSION = "p3-b0-recorded.v1"
COLLECTION_LIMIT = 500
TOTAL_RECORD_LIMIT = 3000
MAX_RECORD_STRING_LENGTH = 512
MAX_RECORDED_JSON_DEPTH = 8

RECORDED_COLLECTION_FIELDS: dict[str, frozenset[str]] = {
    "samples": frozenset(
        {
            "application_id",
            "creator_id",
            "product_id",
            "status",
            "applied_at",
            "fulfillment_due_at",
            "observed_at",
        }
    ),
    "orders": frozenset(
        {
            "order_id",
            "creator_id",
            "product_id",
            "status",
            "created_at",
            "completed_at",
            "observed_at",
        }
    ),
    "logistics": frozenset(
        {"order_id", "tracking_number", "status", "occurred_at", "observed_at"}
    ),
    "videos": frozenset(
        {
            "video_id",
            "creator_id",
            "product_id",
            "published_at",
            "view_count",
            "like_count",
            "observed_at",
        }
    ),
    "attribution": frozenset(
        {
            "pid",
            "order_id",
            "window_start",
            "window_end",
            "observed_at",
        }
    ),
    "gmv": frozenset({"order_id", "amount", "currency", "occurred_at", "observed_at"}),
}

_SENSITIVE_KEYS = frozenset(
    {
        "name",
        "fullname",
        "phone",
        "phonenumber",
        "email",
        "address",
        "accesstoken",
        "refreshtoken",
        "token",
        "cookie",
        "secret",
        "password",
        "oauthcode",
        "oauthstate",
        "authorizationpayload",
        "authorizationheader",
    }
)


class TikTokRecordedValidationInputError(ValueError):
    """Stable, secret-free rejection for recorded validation input."""

    def __init__(self, code: str, status_code: int = 422) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


def _reject_non_finite_json_constant(_value: str) -> None:
    raise TikTokRecordedValidationInputError("recorded_json_invalid")


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _reject_sensitive_keys(value: object, *, depth: int = 0) -> None:
    if depth > MAX_RECORDED_JSON_DEPTH:
        raise TikTokRecordedValidationInputError("recorded_depth_exceeded")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TikTokRecordedValidationInputError("recorded_schema_invalid")
            if _normalized_key(key) in _SENSITIVE_KEYS:
                raise TikTokRecordedValidationInputError("sensitive_field_forbidden")
            _reject_sensitive_keys(child, depth=depth + 1)
    elif isinstance(value, list):
        for child in value:
            _reject_sensitive_keys(child, depth=depth + 1)


def _validate_dataset_shape(raw: object) -> None:
    if not isinstance(raw, dict):
        raise TikTokRecordedValidationInputError("recorded_schema_invalid")
    dataset = raw.get("dataset")
    if not isinstance(dataset, dict) or set(dataset) != set(RECORDED_COLLECTION_FIELDS):
        raise TikTokRecordedValidationInputError("recorded_schema_invalid")
    total = 0
    for collection, allowed_fields in RECORDED_COLLECTION_FIELDS.items():
        records = dataset.get(collection)
        if not isinstance(records, list):
            raise TikTokRecordedValidationInputError("recorded_schema_invalid")
        if len(records) > COLLECTION_LIMIT:
            raise TikTokRecordedValidationInputError("recorded_collection_limit_exceeded")
        total += len(records)
        for record in records:
            if not isinstance(record, dict) or not set(record).issubset(allowed_fields):
                raise TikTokRecordedValidationInputError("recorded_schema_invalid")
            for value in record.values():
                if isinstance(value, (dict, list)):
                    raise TikTokRecordedValidationInputError(
                        "recorded_nested_value_forbidden"
                    )
                if isinstance(value, str) and len(value) > MAX_RECORD_STRING_LENGTH:
                    raise TikTokRecordedValidationInputError("recorded_string_too_long")
    if total > TOTAL_RECORD_LIMIT:
        raise TikTokRecordedValidationInputError("recorded_total_limit_exceeded")


def validate_recorded_payload(raw: object) -> TikTokRecordedValidationRequest:
    _reject_sensitive_keys(raw)
    _validate_dataset_shape(raw)
    try:
        return TikTokRecordedValidationRequest.model_validate(raw)
    except ValidationError:
        raise TikTokRecordedValidationInputError("recorded_schema_invalid") from None


async def read_recorded_validation_request(
    request: Request,
) -> TikTokRecordedValidationRequest:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise TikTokRecordedValidationInputError("recorded_content_type_required", 415)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_RECORDED_REQUEST_BYTES:
            raise TikTokRecordedValidationInputError("recorded_payload_too_large", 413)
    try:
        raw = json.loads(body, parse_constant=_reject_non_finite_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TikTokRecordedValidationInputError("recorded_json_invalid") from None
    finally:
        body.clear()
    return validate_recorded_payload(raw)


def normalize_recorded_dataset(
    request: TikTokRecordedValidationRequest,
) -> dict[str, list[dict[str, object]]]:
    dumped = request.dataset.model_dump(mode="json", exclude_unset=True)
    return {name: list(records) for name, records in dumped.items()}


def compute_contract_digest(contracts: Sequence[TikTokFieldContract]) -> str:
    canonical: list[dict[str, Any]] = []
    for row in sorted(contracts, key=lambda item: item.field_code):
        sources = [
            {
                "source_key": source.get("source_key"),
                "priority": source.get("priority"),
                "usage": source.get("usage"),
                "decision": source.get("decision"),
                "authorization_state": source.get("authorization_state"),
            }
            for source in sorted(
                row.sources_json,
                key=lambda source: (source.get("priority", 0), source.get("source_key", "")),
            )
        ]
        canonical.append(
            {
                "field_code": row.field_code,
                "domain": row.domain,
                "data_type": row.data_type,
                "required": row.required,
                "business_key": row.business_key,
                "freshness_sla_seconds": row.freshness_sla_seconds,
                "missing_behavior": row.missing_behavior,
                "status": row.status,
                "revision": row.revision,
                "sources": sources,
            }
        )
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
