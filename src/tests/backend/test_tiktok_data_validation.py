from __future__ import annotations

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import (
    BusinessResource,
    Tenant,
    TikTokCapabilityEvidence,
    TikTokFieldContract,
    User,
)
from app.tiktok.data_validation import (
    DATA_VALIDATION_CATALOG_VERSION,
    bootstrap_data_validation_workspace,
    get_data_validation_workspace,
)


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_tenant(db: Session, tenant_id: str) -> User:
    admin = User(
        id=f"admin_{tenant_id}",
        tenant_id=tenant_id,
        username=f"admin_{tenant_id}",
        role="admin",
        business_role="platform_admin",
        password_hash="disabled",
    )
    member = User(
        id=f"member_{tenant_id}",
        tenant_id=tenant_id,
        username=f"member_{tenant_id}",
        role="member",
        business_role="member",
        password_hash="disabled",
    )
    db.add(Tenant(id=tenant_id, name=tenant_id))
    db.add(admin)
    db.add(member)
    db.add(
        BusinessResource(
            id=f"store_{tenant_id}",
            tenant_id=tenant_id,
            resource_type="store",
            code=f"TT-US-{tenant_id}",
            name=f"TikTok Shop US {tenant_id}",
            created_by_user_id=admin.id,
            metadata_json={"platform": "tiktok", "market": "US"},
        )
    )
    db.commit()
    db.refresh(admin)
    return admin


def test_bootstrap_is_idempotent_and_does_not_overwrite_tenant_edits() -> None:
    with _session() as db:
        admin = _seed_tenant(db, "tenant_a")
        first = bootstrap_data_validation_workspace(db, admin)
        contract = db.exec(
            select(TikTokFieldContract).where(
                TikTokFieldContract.tenant_id == "tenant_a",
                TikTokFieldContract.field_code == "order.order_id",
            )
        ).one()
        contract.label = "租户自定义订单编号"
        db.add(contract)
        db.commit()

        second = bootstrap_data_validation_workspace(db, admin)

        assert DATA_VALIDATION_CATALOG_VERSION == "p3-b0.v1"
        assert first.created_field_count == 30
        assert first.created_evidence_count == 31
        assert second.created_field_count == 0
        assert second.created_evidence_count == 0
        assert db.get(TikTokFieldContract, contract.id).label == "租户自定义订单编号"


def test_workspace_read_is_tenant_scoped_even_when_codes_match() -> None:
    with _session() as db:
        admin_a = _seed_tenant(db, "tenant_a")
        admin_b = _seed_tenant(db, "tenant_b")
        bootstrap_data_validation_workspace(db, admin_a)
        bootstrap_data_validation_workspace(db, admin_b)

        workspace_a = get_data_validation_workspace(db, admin_a)

        assert workspace_a.tenant_id == "tenant_a"
        assert len(workspace_a.field_contracts) == 30
        assert len(workspace_a.capability_evidence) == 31
        assert {item.tenant_id for item in workspace_a.field_contracts} == {"tenant_a"}
        assert {option.id for option in workspace_a.store_options} == {"store_tenant_a"}
        assert {option.id for option in workspace_a.owner_options} == {
            "admin_tenant_a",
            "member_tenant_a",
        }


def test_bootstrap_uses_only_mock_sources_and_unverified_evidence() -> None:
    with _session() as db:
        admin = _seed_tenant(db, "tenant_a")
        bootstrap_data_validation_workspace(db, admin)

        contracts = db.exec(
            select(TikTokFieldContract).where(TikTokFieldContract.tenant_id == "tenant_a")
        ).all()
        evidence = db.exec(
            select(TikTokCapabilityEvidence).where(
                TikTokCapabilityEvidence.tenant_id == "tenant_a"
            )
        ).all()

        assert len(contracts) == 30
        assert all(
            len(item.sources_json) == 1
            and item.sources_json[0]["source_type"] == "mock_fixture"
            and item.sources_json[0]["usage"] == "mock"
            and item.sources_json[0]["decision"] == "use"
            and item.sources_json[0]["authorization_state"] == "not_required"
            for item in contracts
        )
        assert len(evidence) == 31
        assert all(
            item.evidence_level == "E0"
            and item.evidence_type == "unverified"
            and item.status == "unverified"
            and item.checked_by_user_id is None
            and item.checked_at is None
            for item in evidence
        )
