from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.business_resources.schema import (
    BusinessResourceCreate,
    BusinessResourceUpdate,
    HighRiskActionCreate,
)
from app.business_resources.service import (
    create_action_request,
    create_resource,
    decide_action_request,
    list_resources,
    update_resource,
)
from app.db.models import HighRiskActionRequest, Tenant, User


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _user(user_id: str, role: str, *, account_role: str = "member") -> User:
    return User(
        id=user_id,
        tenant_id="tenant_demo",
        username=user_id,
        role=account_role,
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


def test_role_scopes_isolate_resource_types_inside_a_tenant(db: Session) -> None:
    supervisor = _user("supervisor", "operations_supervisor")
    listing = _user("listing", "listing_compliance_specialist")
    procurement = _user("procurement", "procurement_specialist")
    db.add(supervisor)
    db.add(listing)
    db.add(procurement)
    db.commit()

    create_resource(
        db,
        request=BusinessResourceCreate(
            tenant_id="tenant_demo",
            resource_type="store",
            code="STORE-US",
            name="美国店铺",
        ),
        user=supervisor,
    )
    create_resource(
        db,
        request=BusinessResourceCreate(
            tenant_id="tenant_demo",
            resource_type="supplier",
            code="SUP-1",
            name="供应商一号",
        ),
        user=supervisor,
    )

    assert [row.resource_type for row in list_resources(db, tenant_id="tenant_demo", user=listing)] == [
        "store"
    ]
    assert [row.resource_type for row in list_resources(db, tenant_id="tenant_demo", user=procurement)] == [
        "supplier"
    ]
    assert len(list_resources(db, tenant_id="tenant_demo", user=supervisor)) == 2


def test_high_risk_request_enforces_action_role_and_separation_of_duties(db: Session) -> None:
    supervisor = _user("supervisor", "operations_supervisor")
    second_supervisor = _user("supervisor-2", "operations_supervisor")
    listing = _user("listing", "listing_compliance_specialist")
    db.add(supervisor)
    db.add(second_supervisor)
    db.add(listing)
    db.commit()
    store = create_resource(
        db,
        request=BusinessResourceCreate(
            tenant_id="tenant_demo",
            resource_type="store",
            code="STORE-US",
            name="美国店铺",
        ),
        user=supervisor,
    )

    request = create_action_request(
        db,
        request=HighRiskActionCreate(
            tenant_id="tenant_demo",
            resource_id=store.id,
            action_type="publish_listing",
            summary="发布美国站 Listing A100",
            payload={
                "listing_id": "A100",
                "marketplace": "Amazon US",
                "product_type": "PRODUCT",
                "attributes": {"item_name": [{"value": "Demo"}]},
            },
        ),
        user=listing,
    )
    assert request.status == "pending"
    assert [event.event_type for event in request.events] == ["requested"]

    decided = decide_action_request(
        db,
        tenant_id="tenant_demo",
        request_id=request.id,
        decision="approved",
        reason="合规材料齐全，批准发布",
        user=supervisor,
    )
    assert decided.status == "approved"
    assert [event.event_type for event in decided.events] == ["requested", "approved"]

    own_request = create_action_request(
        db,
        request=HighRiskActionCreate(
            tenant_id="tenant_demo",
            resource_id=store.id,
            action_type="publish_listing",
            summary="运营主管发起的紧急发布申请",
            payload={
                "listing_id": "A200",
                "marketplace": "Amazon US",
                "product_type": "PRODUCT",
                "attributes": {"item_name": [{"value": "Demo"}]},
            },
        ),
        user=supervisor,
    )
    with pytest.raises(HTTPException) as self_approval:
        decide_action_request(
            db,
            tenant_id="tenant_demo",
            request_id=own_request.id,
            decision="approved",
            reason="自行批准",
            user=supervisor,
        )
    assert self_approval.value.status_code == 403

    approved_by_second = decide_action_request(
        db,
        tenant_id="tenant_demo",
        request_id=own_request.id,
        decision="approved",
        reason="第二审批人确认",
        user=second_supervisor,
    )
    assert approved_by_second.decided_by_user_id == second_supervisor.id


def test_action_payload_rejects_wrong_role_and_embedded_secrets(db: Session) -> None:
    supervisor = _user("supervisor", "operations_supervisor")
    listing = _user("listing", "listing_compliance_specialist")
    db.add(supervisor)
    db.add(listing)
    db.commit()
    store = create_resource(
        db,
        request=BusinessResourceCreate(
            tenant_id="tenant_demo",
            resource_type="store",
            code="STORE-US",
            name="美国店铺",
        ),
        user=supervisor,
    )

    with pytest.raises(HTTPException) as wrong_role:
        create_action_request(
            db,
            request=HighRiskActionCreate(
                tenant_id="tenant_demo",
                resource_id=store.id,
                action_type="issue_refund",
                summary="尝试执行不属于 Listing 岗位的退款",
                payload={"order_id": "O-1", "amount": 12, "currency": "USD"},
            ),
            user=listing,
        )
    assert wrong_role.value.status_code == 403

    with pytest.raises(HTTPException) as secret:
        create_action_request(
            db,
            request=HighRiskActionCreate(
                tenant_id="tenant_demo",
                resource_id=store.id,
                action_type="publish_listing",
                summary="包含不应进入审批载荷的访问令牌",
                payload={
                    "listing_id": "A100",
                    "marketplace": "Amazon US",
                    "product_type": "PRODUCT",
                    "attributes": {"item_name": [{"value": "Demo"}]},
                    "access_token": "not-a-real-token",
                },
            ),
            user=listing,
        )
    assert secret.value.status_code == 400


def test_resource_change_invalidates_pending_approval_but_noop_update_does_not(
    db: Session,
) -> None:
    supervisor = _user("supervisor", "operations_supervisor")
    listing = _user("listing", "listing_compliance_specialist")
    db.add(supervisor)
    db.add(listing)
    db.commit()
    store = create_resource(
        db,
        request=BusinessResourceCreate(
            tenant_id="tenant_demo",
            resource_type="store",
            code="STORE-US",
            name="美国店铺",
        ),
        user=supervisor,
    )
    approval = create_action_request(
        db,
        request=HighRiskActionCreate(
            tenant_id="tenant_demo",
            resource_id=store.id,
            action_type="publish_listing",
            summary="发布美国站 Listing A100",
            payload={
                "listing_id": "A100",
                "marketplace": "Amazon US",
                "product_type": "PRODUCT",
                "attributes": {"item_name": [{"value": "Demo"}]},
            },
        ),
        user=listing,
    )

    unchanged = update_resource(
        db,
        resource_id=store.id,
        request=BusinessResourceUpdate(tenant_id="tenant_demo", name="美国店铺"),
        user=supervisor,
    )
    assert unchanged.revision == 1
    assert db.get(HighRiskActionRequest, approval.id).status == "pending"

    changed = update_resource(
        db,
        resource_id=store.id,
        request=BusinessResourceUpdate(tenant_id="tenant_demo", name="美国主店"),
        user=supervisor,
    )
    invalidated = db.get(HighRiskActionRequest, approval.id)
    assert changed.revision == 2
    assert invalidated is not None
    assert invalidated.status == "invalidated"
    assert invalidated.invalidation_reason == "business_resource_context_changed"
