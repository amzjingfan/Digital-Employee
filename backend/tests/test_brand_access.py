from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.brands.schema import BrandCreate, BrandMembershipPut, StoreAccessPut
from app.brands.service import (
    create_brand,
    list_brand_access_events,
    list_brand_stores,
    list_brands,
    put_brand_membership,
    put_store_access,
    require_brand_store_access,
)
from app.db.models import (
    BrandAccessEvent,
    BrandMembership,
    BusinessResource,
    StoreAccess,
    Tenant,
    User,
)


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Tenant(id="tenant_demo", name="Demo"))
        session.add(Tenant(id="tenant_other", name="Other"))
        session.add(_user("admin", tenant_id="tenant_demo", account_role="admin"))
        session.add(_user("member_a", tenant_id="tenant_demo"))
        session.add(_user("member_b", tenant_id="tenant_demo"))
        session.add(_user("foreign_member", tenant_id="tenant_other"))
        session.commit()
        yield session


def test_members_only_list_explicitly_assigned_active_brands(db: Session) -> None:
    admin = _get_user(db, "admin")
    member = _get_user(db, "member_a")
    brand_a = create_brand(
        db,
        request=BrandCreate(
            tenant_id="tenant_demo",
            code="ACME-US",
            name="Acme US",
            timezone="America/Los_Angeles",
        ),
        user=admin,
    )
    create_brand(
        db,
        request=BrandCreate(tenant_id="tenant_demo", code="ACME-EU", name="Acme EU"),
        user=admin,
    )
    repeated_brand = create_brand(
        db,
        request=BrandCreate(
            tenant_id="tenant_demo",
            code="ACME-US",
            name="Acme US",
            timezone="America/Los_Angeles",
        ),
        user=admin,
    )

    assert repeated_brand.id == brand_a.id
    assert list_brands(db, tenant_id="tenant_demo", user=member) == []
    membership = put_brand_membership(
        db,
        brand_id=brand_a.id,
        subject_user_id=member.id,
        request=BrandMembershipPut(tenant_id="tenant_demo", access_level="viewer"),
        user=admin,
    )
    repeated = put_brand_membership(
        db,
        brand_id=brand_a.id,
        subject_user_id=member.id,
        request=BrandMembershipPut(tenant_id="tenant_demo", access_level="viewer"),
        user=admin,
    )

    assert repeated.id == membership.id
    assert [
        (row.code, row.access_level)
        for row in list_brands(db, tenant_id="tenant_demo", user=member)
    ] == [("ACME-US", "viewer")]
    assert {row.code for row in list_brands(db, tenant_id="tenant_demo", user=admin)} == {
        "ACME-US",
        "ACME-EU",
    }
    assert len(db.exec(select(BrandMembership)).all()) == 1
    assert len(db.exec(select(BrandAccessEvent)).all()) == 3


def test_membership_and_store_assignment_reject_cross_tenant_parents(db: Session) -> None:
    admin = _get_user(db, "admin")
    brand = _brand(db, admin, code="ACME-US")
    foreign_user = _get_user(db, "foreign_member")
    foreign_store = _resource(db, "foreign_store", tenant_id="tenant_other", resource_type="store")
    ad_account = _resource(db, "demo_ads", tenant_id="tenant_demo", resource_type="ad_account")

    with pytest.raises(HTTPException) as cross_tenant_user:
        put_brand_membership(
            db,
            brand_id=brand.id,
            subject_user_id=foreign_user.id,
            request=BrandMembershipPut(tenant_id="tenant_demo"),
            user=admin,
        )
    assert cross_tenant_user.value.status_code == 404

    with pytest.raises(HTTPException) as cross_tenant_store:
        put_store_access(
            db,
            brand_id=brand.id,
            resource_id=foreign_store.id,
            request=StoreAccessPut(tenant_id="tenant_demo"),
            user=admin,
        )
    assert cross_tenant_store.value.status_code == 404

    with pytest.raises(HTTPException) as wrong_resource_type:
        put_store_access(
            db,
            brand_id=brand.id,
            resource_id=ad_account.id,
            request=StoreAccessPut(tenant_id="tenant_demo"),
            user=admin,
        )
    assert wrong_resource_type.value.status_code == 400

    with pytest.raises(HTTPException) as forged_tenant:
        create_brand(
            db,
            request=BrandCreate(tenant_id="tenant_other", code="FORGED", name="Forged"),
            user=admin,
        )
    assert forged_tenant.value.status_code == 403


def test_brand_and_store_access_are_intersected_and_default_deny(db: Session) -> None:
    admin = _get_user(db, "admin")
    member_a = _get_user(db, "member_a")
    member_b = _get_user(db, "member_b")
    brand_a = _brand(db, admin, code="ACME-US")
    brand_b = _brand(db, admin, code="ACME-EU")
    store_a = _resource(db, "store_us", tenant_id="tenant_demo", resource_type="store")
    store_b = _resource(db, "store_eu", tenant_id="tenant_demo", resource_type="store")
    put_brand_membership(
        db,
        brand_id=brand_a.id,
        subject_user_id=member_a.id,
        request=BrandMembershipPut(tenant_id="tenant_demo", access_level="viewer"),
        user=admin,
    )
    put_brand_membership(
        db,
        brand_id=brand_b.id,
        subject_user_id=member_b.id,
        request=BrandMembershipPut(tenant_id="tenant_demo", access_level="operator"),
        user=admin,
    )
    put_store_access(
        db,
        brand_id=brand_a.id,
        resource_id=store_a.id,
        request=StoreAccessPut(tenant_id="tenant_demo"),
        user=admin,
    )
    put_store_access(
        db,
        brand_id=brand_b.id,
        resource_id=store_b.id,
        request=StoreAccessPut(tenant_id="tenant_demo"),
        user=admin,
    )

    assert [
        row.resource_id
        for row in list_brand_stores(
            db, tenant_id="tenant_demo", brand_id=brand_a.id, user=member_a
        )
    ] == [store_a.id]
    assert (
        require_brand_store_access(
            db,
            tenant_id="tenant_demo",
            brand_id=brand_a.id,
            resource_id=store_a.id,
            user=member_a,
        ).id
        == store_a.id
    )

    with pytest.raises(HTTPException) as missing_operator_access:
        require_brand_store_access(
            db,
            tenant_id="tenant_demo",
            brand_id=brand_a.id,
            resource_id=store_a.id,
            user=member_a,
            required_access="operator",
        )
    assert missing_operator_access.value.status_code == 403

    with pytest.raises(HTTPException) as wrong_brand:
        require_brand_store_access(
            db,
            tenant_id="tenant_demo",
            brand_id=brand_b.id,
            resource_id=store_b.id,
            user=member_a,
        )
    assert wrong_brand.value.status_code == 403

    with pytest.raises(HTTPException) as store_outside_brand:
        require_brand_store_access(
            db,
            tenant_id="tenant_demo",
            brand_id=brand_a.id,
            resource_id=store_b.id,
            user=member_a,
        )
    assert store_outside_brand.value.status_code == 404


def test_database_constraints_reject_cross_tenant_membership_and_store(db: Session) -> None:
    admin = _get_user(db, "admin")
    foreign_user = _get_user(db, "foreign_member")
    brand = _brand(db, admin, code="ACME-US")
    db.add(
        BrandMembership(
            tenant_id="tenant_demo",
            brand_id=brand.id,
            user_id=foreign_user.id,
            created_by_user_id=admin.id,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    foreign_store = _resource(db, "foreign_store", tenant_id="tenant_other", resource_type="store")
    db.add(
        StoreAccess(
            tenant_id="tenant_demo",
            brand_id=brand.id,
            resource_id=foreign_store.id,
            created_by_user_id=admin.id,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_assignment_updates_are_idempotent_and_audited(db: Session) -> None:
    admin = _get_user(db, "admin")
    member = _get_user(db, "member_a")
    brand = _brand(db, admin, code="ACME-US")
    store = _resource(db, "store_us", tenant_id="tenant_demo", resource_type="store")
    put_brand_membership(
        db,
        brand_id=brand.id,
        subject_user_id=member.id,
        request=BrandMembershipPut(tenant_id="tenant_demo", access_level="viewer"),
        user=admin,
    )
    put_store_access(
        db,
        brand_id=brand.id,
        resource_id=store.id,
        request=StoreAccessPut(tenant_id="tenant_demo"),
        user=admin,
    )
    put_store_access(
        db,
        brand_id=brand.id,
        resource_id=store.id,
        request=StoreAccessPut(tenant_id="tenant_demo"),
        user=admin,
    )
    put_brand_membership(
        db,
        brand_id=brand.id,
        subject_user_id=member.id,
        request=BrandMembershipPut(
            tenant_id="tenant_demo",
            access_level="viewer",
            status="inactive",
        ),
        user=admin,
    )

    assert len(db.exec(select(StoreAccess)).all()) == 1
    events = list_brand_access_events(
        db,
        tenant_id="tenant_demo",
        brand_id=brand.id,
        user=admin,
    )
    assert [event.event_type for event in events] == [
        "brand_created",
        "membership_changed",
        "store_access_changed",
        "membership_changed",
    ]
    with pytest.raises(HTTPException) as revoked:
        list_brand_stores(
            db,
            tenant_id="tenant_demo",
            brand_id=brand.id,
            user=member,
        )
    assert revoked.value.status_code == 403


def test_postgres_migration_declares_composite_scope_rls_and_rollback() -> None:
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    up = (migrations / "20260908_brand_access_v1.sql").read_text(encoding="utf-8")
    down = (migrations / "20260908_brand_access_v1.down.sql").read_text(encoding="utf-8")

    assert "FOREIGN KEY (tenant_id, brand_id)" in up
    assert "FOREIGN KEY (tenant_id, resource_id)" in up
    assert "ENABLE ROW LEVEL SECURITY" in up
    assert "WITH CHECK (tenant_id = app.current_staffdeck_tenant_id())" in up
    assert "worker_tenant_isolation" in up
    assert "brand_access_events_append_only" in up
    assert "DROP TABLE IF EXISTS public.brands" in down


def _user(user_id: str, *, tenant_id: str, account_role: str = "member") -> User:
    return User(
        id=user_id,
        tenant_id=tenant_id,
        username=user_id,
        role=account_role,
        business_role="listing_compliance_specialist",
        password_hash="disabled",
    )


def _get_user(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    assert user is not None
    return user


def _brand(db: Session, admin: User, *, code: str):
    return create_brand(
        db,
        request=BrandCreate(tenant_id="tenant_demo", code=code, name=code),
        user=admin,
    )


def _resource(
    db: Session,
    resource_id: str,
    *,
    tenant_id: str,
    resource_type: str,
) -> BusinessResource:
    row = BusinessResource(
        id=resource_id,
        tenant_id=tenant_id,
        resource_type=resource_type,
        code=resource_id.upper(),
        name=resource_id,
        created_by_user_id="admin",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
