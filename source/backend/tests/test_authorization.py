from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select
from starlette.requests import Request

from app.config import Settings
from app.db.models import AuthorizationDecision, Tenant, User
from app.security.authorization import (
    authorize,
    enterprise_capabilities,
    require_enterprise_permission,
)


def _user(role: str) -> User:
    return User(
        id=f"user_{role}",
        tenant_id="tenant_demo",
        username=role,
        role=role,
        password_hash="disabled",
    )


def _business_user(business_role: str) -> User:
    return User(
        id=f"user_{business_role}",
        tenant_id="tenant_demo",
        username=business_role,
        role="member",
        business_role=business_role,
        authorization_source="oidc_groups",
        password_hash="disabled",
    )


def test_casbin_role_matrix_is_default_deny() -> None:
    settings = Settings(casbin_enabled=True)
    admin = _user("admin")
    member = _user("member")
    unknown = _user("unexpected")

    assert authorize(
        settings, user=admin, object_path="/api/enterprise/agents", action="POST"
    ).allowed
    assert authorize(
        settings, user=member, object_path="/api/enterprise/agents", action="GET"
    ).allowed
    assert not authorize(
        settings, user=member, object_path="/api/enterprise/agents", action="POST"
    ).allowed
    assert authorize(
        settings, user=member, object_path="/api/enterprise/teams", action="POST"
    ).allowed
    assert not authorize(
        settings,
        user=member,
        object_path="/api/enterprise/authorization-decisions",
        action="GET",
    ).allowed
    assert not authorize(
        settings, user=unknown, object_path="/api/enterprise/agents", action="GET"
    ).allowed


def test_business_role_matrix_applies_least_privilege() -> None:
    settings = Settings(casbin_enabled=True)
    supervisor = _business_user("operations_supervisor")
    after_sales = _business_user("after_sales_specialist")
    listing = _business_user("listing_compliance_specialist")
    logistics = _business_user("logistics_exception_specialist")
    designer = _business_user("designer")
    procurement = _business_user("procurement_specialist")

    assert authorize(
        settings, user=supervisor, object_path="/api/enterprise/sessions/export", action="POST"
    ).allowed
    assert not authorize(
        settings, user=supervisor, object_path="/api/enterprise/model-configs", action="POST"
    ).allowed
    assert authorize(
        settings, user=after_sales, object_path="/api/enterprise/feedback/case-1", action="POST"
    ).allowed
    assert not authorize(
        settings, user=after_sales, object_path="/api/enterprise/knowledge/documents", action="POST"
    ).allowed
    assert authorize(
        settings, user=listing, object_path="/api/enterprise/knowledge/documents", action="POST"
    ).allowed
    assert authorize(
        settings,
        user=logistics,
        object_path="/api/enterprise/scheduled-tasks/task-1",
        action="PATCH",
    ).allowed
    assert authorize(
        settings, user=designer, object_path="/api/enterprise/knowledge/documents", action="PUT"
    ).allowed
    assert not authorize(
        settings, user=procurement, object_path="/api/enterprise/tools/tool-1", action="DELETE"
    ).allowed
    assert authorize(
        settings,
        user=supervisor,
        object_path="/api/enterprise/work-tasks/advertising/automation-policies",
        action="PUT",
    ).allowed
    assert not authorize(
        settings,
        user=listing,
        object_path="/api/enterprise/work-tasks/advertising/automation-policies",
        action="PUT",
    ).allowed
    for user in (supervisor, after_sales, listing, logistics, designer, procurement):
        assert not authorize(
            settings,
            user=user,
            object_path="/api/enterprise/identity-role-mappings",
            action="GET",
        ).allowed


def test_capability_manifest_is_derived_from_business_role_policy() -> None:
    settings = Settings(casbin_enabled=True)
    supervisor = enterprise_capabilities(settings, user=_business_user("operations_supervisor"))
    listing = enterprise_capabilities(
        settings, user=_business_user("listing_compliance_specialist")
    )
    after_sales = enterprise_capabilities(settings, user=_business_user("after_sales_specialist"))

    assert supervisor["knowledge"] == ["view"]
    assert supervisor["scheduled_tasks"] == ["view", "create", "update", "delete"]
    assert "identity_roles" not in supervisor
    assert supervisor["accounts"] == []
    assert listing["knowledge"] == ["view", "create", "update"]
    assert listing["business_resources"] == ["view"]
    assert supervisor["business_resources"] == ["view", "create", "update", "delete"]
    assert supervisor["operations_reports"] == ["view", "create"]
    assert "operations_reports" not in listing
    assert "channels" not in after_sales
    assert after_sales["feedback"] == ["view"]


def test_business_resource_routes_separate_requesters_from_approvers() -> None:
    settings = Settings(casbin_enabled=True)
    supervisor = _business_user("operations_supervisor")
    listing = _business_user("listing_compliance_specialist")

    assert authorize(
        settings,
        user=listing,
        object_path="/api/enterprise/business-resources",
        action="GET",
    ).allowed
    assert authorize(
        settings,
        user=listing,
        object_path="/api/enterprise/business-action-requests",
        action="POST",
    ).allowed
    assert not authorize(
        settings,
        user=listing,
        object_path="/api/enterprise/business-approvals/request-1/approve",
        action="POST",
    ).allowed
    assert authorize(
        settings,
        user=supervisor,
        object_path="/api/enterprise/business-approvals/request-1/approve",
        action="POST",
    ).allowed


def test_denied_decision_is_committed_with_request_id() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Tenant(id="tenant_demo", name="Demo"))
        member = _user("member")
        db.add(member)
        db.commit()

        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/enterprise/agents",
                "headers": [],
            }
        )
        request.state.request_id = "req_test_denied"

        try:
            require_enterprise_permission(request, member, db)
        except HTTPException as error:
            assert error.status_code == 403
            assert error.detail == "Permission denied"
        else:
            raise AssertionError("member write to digital employees must be denied")

        decision = db.exec(select(AuthorizationDecision)).one()
        assert decision.tenant_id == "tenant_demo"
        assert decision.subject_id == member.id
        assert decision.role == "tenant_member"
        assert decision.object == "/api/enterprise/agents"
        assert decision.action == "POST"
        assert decision.effect == "deny"
        assert decision.request_id == "req_test_denied"
        assert decision.policy_version not in {"", "disabled"}
