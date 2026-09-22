from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import pytest
from starlette.requests import Request

from app.db.models import TikTokFieldContract
from app.tiktok.data_validation import FIELD_CODES, MOCK_DATASET
from app.tiktok.recorded_validation import (
    MAX_RECORDED_REQUEST_BYTES,
    RECORDED_COLLECTION_FIELDS,
    TikTokRecordedValidationInputError,
    compute_contract_digest,
    normalize_recorded_dataset,
    read_recorded_validation_request,
    validate_recorded_payload,
)


def _valid_payload_dict() -> dict[str, Any]:
    payload = {
        "scope_revision": 1,
        "source_label": "approved-export",
        "approval_ref": "APPROVAL-001",
        "approved_by_user_id": "member_tenant_a",
        "approved_at": "2026-09-02T02:00:00Z",
        "approval_valid_until": "2026-10-02T02:00:00Z",
        "data_period_start": "2026-08-01T00:00:00Z",
        "data_period_end": "2026-08-31T23:59:59Z",
        "replay_as_of": "2026-09-01T02:00:00Z",
        "sanitization_attested": True,
        "dataset": deepcopy(MOCK_DATASET),
    }
    payload["dataset"]["attribution"][0].pop("product_id")
    return payload


def _body_bytes(*, pad_to: int | None = None) -> bytes:
    body = json.dumps(_valid_payload_dict(), separators=(",", ":")).encode()
    if pad_to is not None:
        assert len(body) <= pad_to
        body += b" " * (pad_to - len(body))
    return body


def _request(body: bytes, *, content_type: str = "application/json") -> Request:
    chunks = [body[index : index + 65536] for index in range(0, len(body), 65536)]
    position = 0

    async def receive() -> dict[str, object]:
        nonlocal position
        if position >= len(chunks):
            return {"type": "http.request", "body": b"", "more_body": False}
        chunk = chunks[position]
        position += 1
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": position < len(chunks),
        }

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [(b"content-type", content_type.encode())],
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 80),
        },
        receive,
    )


@pytest.mark.asyncio
async def test_stream_limit_uses_actual_bytes_without_content_length() -> None:
    accepted = await read_recorded_validation_request(
        _request(_body_bytes(pad_to=MAX_RECORDED_REQUEST_BYTES))
    )
    assert accepted.sanitization_attested is True

    with pytest.raises(TikTokRecordedValidationInputError) as error:
        await read_recorded_validation_request(
            _request(_body_bytes(pad_to=MAX_RECORDED_REQUEST_BYTES + 1))
        )
    assert (error.value.status_code, error.value.code) == (
        413,
        "recorded_payload_too_large",
    )


@pytest.mark.asyncio
async def test_content_type_and_invalid_json_return_stable_codes() -> None:
    with pytest.raises(TikTokRecordedValidationInputError) as wrong_type:
        await read_recorded_validation_request(_request(b"{}", content_type="text/plain"))
    assert (wrong_type.value.status_code, wrong_type.value.code) == (
        415,
        "recorded_content_type_required",
    )

    marker = "raw-parser-marker"
    with pytest.raises(TikTokRecordedValidationInputError) as invalid:
        await read_recorded_validation_request(_request(f'{{"{marker}"'.encode()))
    assert (invalid.value.status_code, invalid.value.code) == (422, "recorded_json_invalid")
    assert marker not in str(invalid.value)


@pytest.mark.parametrize(
    "key",
    ["access_token", "Access-Token", "OAuth.State", "cookie", "email", "phone"],
)
def test_sensitive_key_variants_are_rejected(key: str) -> None:
    body = _valid_payload_dict()
    body["dataset"]["orders"][0][key] = "forbidden-value"

    with pytest.raises(TikTokRecordedValidationInputError) as error:
        validate_recorded_payload(body)

    assert error.value.code == "sensitive_field_forbidden"
    assert "forbidden-value" not in str(error.value)
    assert key not in str(error.value)


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda body: body["dataset"].update({"unknown": []}), "recorded_schema_invalid"),
        (
            lambda body: body["dataset"]["orders"][0].update({"unknown": "value"}),
            "recorded_schema_invalid",
        ),
        (
            lambda body: body["dataset"]["orders"][0].update({"status": {"nested": True}}),
            "recorded_nested_value_forbidden",
        ),
        (lambda body: body.update({"sanitization_attested": False}), "recorded_schema_invalid"),
    ],
)
def test_schema_rejects_unknown_nested_and_unattested_input(mutate: Any, code: str) -> None:
    body = _valid_payload_dict()
    mutate(body)

    with pytest.raises(TikTokRecordedValidationInputError) as error:
        validate_recorded_payload(body)

    assert error.value.code == code


def test_deeply_nested_input_is_rejected_without_recursion_failure() -> None:
    body = _valid_payload_dict()
    nested: dict[str, object] = {}
    cursor = nested
    for _ in range(1100):
        child: dict[str, object] = {}
        cursor["nested"] = child
        cursor = child
    body["dataset"]["orders"][0]["status"] = nested

    with pytest.raises(TikTokRecordedValidationInputError) as error:
        validate_recorded_payload(body)

    assert error.value.code == "recorded_depth_exceeded"


def test_collection_and_total_record_limits_are_enforced() -> None:
    body = _valid_payload_dict()
    body["dataset"]["orders"] = [deepcopy(MOCK_DATASET["orders"][0]) for _ in range(501)]
    with pytest.raises(TikTokRecordedValidationInputError) as collection_error:
        validate_recorded_payload(body)
    assert collection_error.value.code == "recorded_collection_limit_exceeded"

    body = _valid_payload_dict()
    for name, rows in body["dataset"].items():
        body["dataset"][name] = [deepcopy(rows[0]) for _ in range(500)]
    normalized = normalize_recorded_dataset(validate_recorded_payload(body))
    assert sum(len(rows) for rows in normalized.values()) == 3000


def test_string_length_and_naive_datetime_are_rejected() -> None:
    body = _valid_payload_dict()
    body["dataset"]["orders"][0]["status"] = "x" * 513
    with pytest.raises(TikTokRecordedValidationInputError) as long_value:
        validate_recorded_payload(body)
    assert long_value.value.code == "recorded_string_too_long"

    body = _valid_payload_dict()
    body["approved_at"] = "2026-09-02T02:00:00"
    with pytest.raises(TikTokRecordedValidationInputError) as naive:
        validate_recorded_payload(body)
    assert naive.value.code == "recorded_schema_invalid"


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.asyncio
async def test_non_finite_json_numbers_are_rejected(constant: str) -> None:
    body = json.dumps(_valid_payload_dict(), separators=(",", ":"))
    body = body.replace('"view_count":100', f'"view_count":{constant}')

    with pytest.raises(TikTokRecordedValidationInputError) as error:
        await read_recorded_validation_request(_request(body.encode()))

    assert error.value.code == "recorded_json_invalid"


@pytest.mark.parametrize("field", ["source_label", "approval_ref", "approved_by_user_id"])
def test_audit_identity_fields_reject_whitespace_only(field: str) -> None:
    body = _valid_payload_dict()
    body[field] = "   "

    with pytest.raises(TikTokRecordedValidationInputError) as error:
        validate_recorded_payload(body)

    assert error.value.code == "recorded_schema_invalid"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("data_period_end", "2026-07-31T23:59:59Z"),
        ("replay_as_of", "2026-08-30T00:00:00Z"),
        ("approved_at", "2026-08-31T00:00:00Z"),
        ("approval_valid_until", "2026-09-02T01:00:00Z"),
    ],
)
def test_time_order_is_strict(field: str, value: str) -> None:
    body = _valid_payload_dict()
    body[field] = value
    with pytest.raises(TikTokRecordedValidationInputError) as error:
        validate_recorded_payload(body)
    assert error.value.code == "recorded_schema_invalid"


def test_contract_digest_is_order_independent_and_changes_with_semantics() -> None:
    first = TikTokFieldContract(
        tenant_id="tenant_a",
        field_code="order.order_id",
        domain="order",
        label="ignored label",
        data_type="string",
        required=True,
        business_key="order_id",
        freshness_sla_seconds=3600,
        missing_behavior="block_stage",
        sources_json=[
            {"source_key": "b", "priority": 2, "usage": "real", "decision": "use", "authorization_state": "authorized"},
            {"source_key": "a", "priority": 1, "usage": "real", "decision": "use", "authorization_state": "authorized"},
        ],
        status="confirmed",
        revision=2,
    )
    second = first.model_copy(deep=True)
    second.sources_json.reverse()
    assert compute_contract_digest([first]) == compute_contract_digest([second])

    second.freshness_sla_seconds = 7200
    assert compute_contract_digest([first]) != compute_contract_digest([second])


def test_recorded_business_allowlist_matches_field_catalog() -> None:
    domains = {
        "samples": "sample",
        "orders": "order",
        "logistics": "logistics",
        "videos": "video",
        "attribution": "attribution",
        "gmv": "gmv",
    }
    allowed_codes = {
        f"{domains[collection]}.{field}"
        for collection, fields in RECORDED_COLLECTION_FIELDS.items()
        for field in fields
        if field != "observed_at"
    }
    assert allowed_codes == set(FIELD_CODES)
