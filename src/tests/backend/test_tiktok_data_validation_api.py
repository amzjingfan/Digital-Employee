from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.tiktok import (
    data_validation_bootstrap,
    data_validation_field_update,
    data_validation_mock_run,
    data_validation_scope_update,
    data_validation_workspace,
)
from app.db.models import BusinessResource, ExternalAuthorization, Tenant, User
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
