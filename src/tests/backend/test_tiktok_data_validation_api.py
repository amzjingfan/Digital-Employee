from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select
from starlette.requests import Request

from app.api.tiktok import (
    data_validation_bootstrap,
    data_validation_field_update,
    data_validation_mock_run,
    data_validation_recorded_run,
    data_validation_scope_update,
    data_validation_workspace,
)
from app.db.models import (
    BusinessResource,
    ExternalAuthorization,
    Tenant,
    TikTokDataValidationRun,
    User,
)
from app.tiktok.data_validation import FIELD_CATALOG, MOCK_DATASET
from app.tiktok.recorded_validation import MAX_RECORDED_REQUEST_BYTES
from app.tiktok.schema import (
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


def _seed_users(db: Session) -> tuple[User, User]:
    admin = User(
        id="admin_tenant_a",
        tenant_id="tenant_a",
        username="admin",
        role="admin",
        business_role="platform_admin",
        password_hash="disabled",
    )
    member = User(
        id="member_tenant_a",
        tenant_id="tenant_a",
        username="member",
        role="member",
        business_role="member",
        password_hash="disabled",
    )
    db.add(Tenant(id="tenant_a", name="Tenant A"))
    db.add(admin)
    db.add(member)
    db.add(
        BusinessResource(
            id="store_tenant_a",
            tenant_id="tenant_a",
            resource_type="store",
            code="TT-US-A",
            name="TikTok Shop US",
            created_by_user_id=admin.id,
            metadata_json={"platform": "tiktok", "market": "US"},
        )
    )
    db.commit()
    db.refresh(admin)
    db.refresh(member)
    return admin, member


def _scope_request() -> TikTokDataValidationScopeUpdate:
    return TikTokDataValidationScopeUpdate(
        revision=0,
        store_resource_id="store_tenant_a",
        creator_scope_summary="US pilot creators",
        business_owner_user_id="admin_tenant_a",
        data_owner_user_id="member_tenant_a",
        status="active",
    )


def _field_request(*, revision: int) -> TikTokFieldContractUpdate:
    return TikTokFieldContractUpdate(
        revision=revision,
        owner_user_id="admin_tenant_a",
        business_key="order_id",
        freshness_sla_seconds=3600,
        missing_behavior="block_stage",
        sources=[
            TikTokFieldSource(
                source_key="mock.order.id",
                source_type="mock_fixture",
                object_name="order",
                field_path="order.order_id",
                priority=1,
                usage="mock",
                decision="use",
                authorization_state="not_required",
            )
        ],
        status="confirmed",
    )


def test_member_can_read_but_cannot_bootstrap_edit_or_run() -> None:
    with _session() as db:
        admin, member = _seed_users(db)
        data_validation_bootstrap(current_user=admin, db=db)
        workspace = data_validation_workspace(current_user=member, db=db)
        assert workspace.tenant_id == member.tenant_id

        for call in (
            lambda: data_validation_bootstrap(current_user=member, db=db),
            lambda: data_validation_scope_update(
                request=_scope_request(), current_user=member, db=db
            ),
            lambda: data_validation_mock_run(current_user=member, db=db),
        ):
            with pytest.raises(HTTPException) as error:
                call()
            assert error.value.status_code == 403


def test_api_maps_unknown_code_and_revision_conflict_without_cross_tenant_leak() -> None:
    with _session() as db:
        admin, _member = _seed_users(db)
        data_validation_bootstrap(current_user=admin, db=db)
        with pytest.raises(HTTPException) as missing:
            data_validation_field_update(
                field_code="other-tenant-field",
                request=_field_request(revision=1),
                current_user=admin,
                db=db,
            )
        assert missing.value.status_code == 404
        assert missing.value.detail["code"] == "catalog_entry_not_found"

        data_validation_field_update(
            field_code="order.order_id",
            request=_field_request(revision=1),
            current_user=admin,
            db=db,
        )
        with pytest.raises(HTTPException) as conflict:
            data_validation_field_update(
                field_code="order.order_id",
                request=_field_request(revision=1),
                current_user=admin,
                db=db,
            )
        assert conflict.value.status_code == 409
        assert conflict.value.detail["code"] == "revision_conflict"


def test_workspace_response_never_serializes_credentials_or_fixture_values() -> None:
    with _session() as db:
        admin, _member = _seed_users(db)
        db.add(
            ExternalAuthorization(
                tenant_id="tenant_a",
                authorization_type="seller",
                subject_id="seller-us",
                resource_id="store_tenant_a",
                scopes_json=["shop.read"],
                credential_ref="secret://credential",
                token_fingerprint="sha256:sensitive-fingerprint",
                metadata_json={"raw": "sensitive-authorization-payload"},
                status="active",
                expires_at=datetime(2026, 10, 1, tzinfo=UTC),
            )
        )
        db.commit()
        data_validation_bootstrap(current_user=admin, db=db)

        serialized = data_validation_workspace(current_user=admin, db=db).model_dump_json()

        for forbidden in (
            "credential_ref",
            "token_fingerprint",
            "metadata_json",
            "secret://credential",
            "sensitive-authorization-payload",
            "mock-order-001",
            "mock-creator-001",
        ):
            assert forbidden not in serialized


def _configure_recorded_validation(db: Session, admin: User) -> None:
    data_validation_bootstrap(current_user=admin, db=db)
    data_validation_scope_update(request=_scope_request(), current_user=admin, db=db)
    for item in FIELD_CATALOG:
        data_validation_field_update(
            field_code=item.code,
            request=TikTokFieldContractUpdate(
                revision=1,
                owner_user_id=admin.id,
                business_key=item.business_key,
                freshness_sla_seconds=86400 * 7,
                missing_behavior="block_stage",
                sources=[
                    TikTokFieldSource(
                        source_key=f"mock.{item.code}",
                        source_type="mock_fixture",
                        object_name=item.domain,
                        field_path=item.code,
                        priority=1,
                        usage="mock",
                        decision="use",
                        authorization_state="not_required",
                    )
                ],
                status="confirmed",
            ),
            current_user=admin,
            db=db,
        )


def _recorded_body(
    *,
    scope_revision: int = 1,
    approver_id: str = "member_tenant_a",
    empty_orders: bool = False,
    marker: str | None = None,
) -> bytes:
    dataset = deepcopy(MOCK_DATASET)
    for row in dataset["attribution"]:
        row.pop("product_id", None)
    if empty_orders:
        dataset["orders"] = []
    if marker:
        dataset["samples"][0]["status"] = marker
    payload = {
        "scope_revision": scope_revision,
        "source_label": "approved-sanitized-export",
        "approval_ref": "approval:recorded-api-001",
        "approved_by_user_id": approver_id,
        "approved_at": "2026-09-22T01:00:00Z",
        "approval_valid_until": "2026-10-02T00:00:00Z",
        "data_period_start": "2026-09-20T00:00:00Z",
        "data_period_end": "2026-09-21T23:30:00Z",
        "replay_as_of": "2026-09-22T00:00:00Z",
        "sanitization_attested": True,
        "dataset": dataset,
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def _recorded_http_request(
    body: bytes, *, content_type: str = "application/json"
) -> Request:
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
            "path": "/api/enterprise/tiktok/data-validation/runs/recorded",
            "raw_path": b"/api/enterprise/tiktok/data-validation/runs/recorded",
            "query_string": b"",
            "headers": [(b"content-type", content_type.encode())],
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 80),
        },
        receive,
    )


def test_recorded_route_returns_safe_pass_and_quality_failure() -> None:
    with _session() as db:
        admin, _member = _seed_users(db)
        _configure_recorded_validation(db, admin)

        passed = asyncio.run(
            data_validation_recorded_run(
                request=_recorded_http_request(
                    _recorded_body(marker="raw-sensitive-marker")
                ),
                current_user=admin,
                db=db,
            )
        )
        failed = asyncio.run(
            data_validation_recorded_run(
                request=_recorded_http_request(_recorded_body(empty_orders=True)),
                current_user=admin,
                db=db,
            )
        )

        assert passed.status == "passed"
        assert failed.status == "failed"
        assert "required_collection_empty" in {item["code"] for item in failed.issues}
        serialized = passed.model_dump_json()
        assert "raw-sensitive-marker" not in serialized
        assert "customer-export.json" not in serialized


def test_recorded_route_rejects_member_tenant_and_scope_without_persistence() -> None:
    with _session() as db:
        admin, member = _seed_users(db)
        _configure_recorded_validation(db, admin)
        cases = (
            (member, _recorded_body(), 403, None),
            (admin, _recorded_body(approver_id="member_other"), 404, "approver_not_found"),
            (admin, _recorded_body(scope_revision=2), 409, "scope_revision_conflict"),
        )
        for user, body, status_code, code in cases:
            before = len(db.exec(select(TikTokDataValidationRun)).all())
            with pytest.raises(HTTPException) as error:
                asyncio.run(
                    data_validation_recorded_run(
                        request=_recorded_http_request(body),
                        current_user=user,
                        db=db,
                    )
                )
            assert error.value.status_code == status_code
            if code:
                assert error.value.detail["code"] == code
            assert len(db.exec(select(TikTokDataValidationRun)).all()) == before


@pytest.mark.parametrize(
    ("body", "content_type", "status_code", "code"),
    (
        (b"{}", "text/plain", 415, "recorded_content_type_required"),
        (b'{"raw-parser-marker"', "application/json", 422, "recorded_json_invalid"),
        (
            json.dumps(
                {
                    "access_token": "raw-secret-marker",
                    "dataset": {},
                }
            ).encode(),
            "application/json",
            422,
            "sensitive_field_forbidden",
        ),
    ),
)
def test_recorded_route_maps_input_errors_without_leaking_values(
    body: bytes, content_type: str, status_code: int, code: str
) -> None:
    with _session() as db:
        admin, _member = _seed_users(db)
        with pytest.raises(HTTPException) as error:
            asyncio.run(
                data_validation_recorded_run(
                    request=_recorded_http_request(body, content_type=content_type),
                    current_user=admin,
                    db=db,
                )
            )
        assert error.value.status_code == status_code
        assert error.value.detail == {"code": code, "message": code}
        assert "raw-parser-marker" not in str(error.value.detail)
        assert "raw-secret-marker" not in str(error.value.detail)


def test_recorded_route_enforces_stream_limit_without_content_length() -> None:
    with _session() as db:
        admin, _member = _seed_users(db)
        body = _recorded_body()
        oversized = body + b" " * (MAX_RECORDED_REQUEST_BYTES + 1 - len(body))
        with pytest.raises(HTTPException) as error:
            asyncio.run(
                data_validation_recorded_run(
                    request=_recorded_http_request(oversized),
                    current_user=admin,
                    db=db,
                )
            )
        assert error.value.status_code == 413
        assert error.value.detail == {
            "code": "recorded_payload_too_large",
            "message": "recorded_payload_too_large",
        }
