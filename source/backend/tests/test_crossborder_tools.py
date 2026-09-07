from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.crossborder_tools import role_context
from app.crossborder.capability_pack import ROLE_PACKS, provision_crossborder_capabilities
from app.db.models import (
    AgentProfile,
    BusinessResource,
    BusinessResourceScope,
    HighRiskActionRequest,
    Tenant,
    WorkTask,
)


def test_role_context_is_role_scoped_and_credential_free() -> None:
    with _test_session() as db:
        db.add(Tenant(id="tenant_demo", name="Demo"))
        agents: dict[str, AgentProfile] = {}
        for index, spec in enumerate(ROLE_PACKS):
            agent = AgentProfile(
                id=f"agent-{index}",
                tenant_id="tenant_demo",
                name=f"role-{index}",
                status="active",
                metadata_json={"business_role": spec.role},
            )
            agents[spec.role] = agent
            db.add(agent)
        db.commit()
        provision_crossborder_capabilities(
            db, tenant_id="tenant_demo", tool_base_url="http://127.0.0.1:5173"
        )

        allowed = BusinessResource(
            id="store-allowed",
            tenant_id="tenant_demo",
            resource_type="store",
            code="US-1",
            name="US Store",
            created_by_user_id="admin",
            metadata_json={"api_token": "must-not-leak"},
        )
        blocked = BusinessResource(
            id="store-blocked",
            tenant_id="tenant_demo",
            resource_type="store",
            code="EU-2",
            name="EU Store",
            created_by_user_id="admin",
            metadata_json={"secret": "must-not-leak"},
        )
        db.add(allowed)
        db.add(blocked)
        db.add(
            BusinessResourceScope(
                tenant_id="tenant_demo",
                resource_id=allowed.id,
                business_role="listing_compliance_specialist",
                access_level="viewer",
            )
        )
        db.add(
            WorkTask(
                id="task-listing",
                tenant_id="tenant_demo",
                idempotency_key="listing-1",
                title="Review SKU",
                owner_business_role="listing_compliance_specialist",
                assigned_by_user_id="admin",
            )
        )
        db.add(
            WorkTask(
                id="task-logistics",
                tenant_id="tenant_demo",
                idempotency_key="logistics-1",
                title="Track shipment",
                owner_business_role="logistics_exception_specialist",
                assigned_by_user_id="admin",
            )
        )
        db.add(
            HighRiskActionRequest(
                id="approval-listing",
                tenant_id="tenant_demo",
                resource_id=allowed.id,
                resource_type="store",
                resource_name=allowed.name,
                action_type="publish_listing",
                summary="Publish SKU",
                payload_json={"credential": "must-not-leak"},
                requester_user_id="user-listing",
                requester_business_role="listing_compliance_specialist",
            )
        )
        db.commit()

        listing_spec = next(
            item for item in ROLE_PACKS if item.role == "listing_compliance_specialist"
        )
        result = role_context(
            limit=20,
            resource_type=None,
            tenant_id="tenant_demo",
            agent_id=agents[listing_spec.role].id,
            active_skill_id=listing_spec.skill_id,
            tool_name=f"crossborder.{listing_spec.role}.context_read",
            db=db,
        )

        assert [item["resource_id"] for item in result["resources"]] == ["store-allowed"]
        assert [item["task_id"] for item in result["open_tasks"]] == ["task-listing"]
        assert [item["request_id"] for item in result["pending_approvals"]] == ["approval-listing"]
        serialized = str(result).lower()
        assert "must-not-leak" not in serialized
        assert "metadata_json" not in serialized
        assert "payload_json" not in serialized
        assert result["data_quality"]["credentials_included"] is False


def test_role_context_rejects_cross_role_tool_spoofing() -> None:
    with _test_session() as db:
        db.add(Tenant(id="tenant_demo", name="Demo"))
        agents: dict[str, AgentProfile] = {}
        for index, spec in enumerate(ROLE_PACKS):
            agent = AgentProfile(
                id=f"agent-{index}",
                tenant_id="tenant_demo",
                name=f"role-{index}",
                status="active",
                metadata_json={"business_role": spec.role},
            )
            agents[spec.role] = agent
            db.add(agent)
        db.commit()
        provision_crossborder_capabilities(
            db, tenant_id="tenant_demo", tool_base_url="http://127.0.0.1:5173"
        )
        listing_spec = next(
            item for item in ROLE_PACKS if item.role == "listing_compliance_specialist"
        )
        logistics_spec = next(
            item for item in ROLE_PACKS if item.role == "logistics_exception_specialist"
        )

        with pytest.raises(HTTPException) as exc_info:
            role_context(
                limit=20,
                resource_type=None,
                tenant_id="tenant_demo",
                agent_id=agents[listing_spec.role].id,
                active_skill_id=listing_spec.skill_id,
                tool_name=f"crossborder.{logistics_spec.role}.context_read",
                db=db,
            )
        assert exc_info.value.status_code == 403


def test_role_context_rejects_cross_tenant_agent_spoofing() -> None:
    with _test_session() as db:
        db.add(Tenant(id="tenant_demo", name="Demo"))
        db.add(Tenant(id="tenant_other", name="Other"))
        listing_spec = next(
            item for item in ROLE_PACKS if item.role == "listing_compliance_specialist"
        )
        agents: dict[str, AgentProfile] = {}
        for index, spec in enumerate(ROLE_PACKS):
            agent = AgentProfile(
                id=f"agent-{index}",
                tenant_id="tenant_demo",
                name=spec.role,
                status="active",
                metadata_json={"business_role": spec.role},
            )
            agents[spec.role] = agent
            db.add(agent)
        db.commit()
        provision_crossborder_capabilities(
            db, tenant_id="tenant_demo", tool_base_url="http://127.0.0.1:5173"
        )

        with pytest.raises(HTTPException) as exc_info:
            role_context(
                limit=20,
                resource_type=None,
                tenant_id="tenant_other",
                agent_id=agents[listing_spec.role].id,
                active_skill_id=listing_spec.skill_id,
                tool_name=f"crossborder.{listing_spec.role}.context_read",
                db=db,
            )
        assert exc_info.value.status_code == 403


@contextmanager
def _test_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
