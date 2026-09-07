from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import Settings
from app.db.models import (
    AuthorizationPolicyEvent,
    AuthorizationPolicyRelease,
    BusinessResource,
    BusinessResourceScope,
    Tenant,
    User,
)
from app.security.authorization import (
    ContextPolicy,
    authorize,
    authorize_business_resource,
    authorize_context,
    default_policy_text,
    validate_policy_text,
)
from app.security.policy_lifecycle import (
    PolicyLifecycleError,
    create_policy_draft,
    publish_policy,
    rollback_policy,
    update_policy_draft,
)


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _admin() -> User:
    return User(
        id="user_admin",
        tenant_id="tenant_demo",
        username="admin",
        role="admin",
        password_hash="disabled",
    )


def _member(role: str) -> User:
    return User(
        id=f"user_{role}",
        tenant_id="tenant_demo",
        username=role,
        role="member",
        business_role=role,
        password_hash="disabled",
    )


def test_policy_validation_requires_admin_recovery_access() -> None:
    settings = Settings(casbin_enabled=True)
    valid = validate_policy_text(
        settings,
        tenant_id="tenant_demo",
        policy_text=default_policy_text(settings),
    )
    assert valid["valid"] is True
    assert int(valid["rule_count"]) > 20

    with pytest.raises(ValueError, match="recovery access"):
        validate_policy_text(
            settings,
            tenant_id="tenant_demo",
            policy_text="p, tenant_member, *, /api/enterprise/agents, GET, allow\n",
        )


def test_policy_release_publish_and_rollback_are_versioned_and_immutable() -> None:
    engine = _engine()
    SQLModel.metadata.create_all(engine)
    settings = Settings(casbin_enabled=True)
    with Session(engine) as db:
        admin = _admin()
        member = _member("member")
        db.add(Tenant(id="tenant_demo", name="Demo"))
        db.add(admin)
        db.add(member)
        db.commit()

        first = create_policy_draft(
            db,
            settings,
            tenant_id="tenant_demo",
            actor=admin,
            description="baseline",
        )
        assert first.version == 1
        published = publish_policy(
            db,
            settings,
            tenant_id="tenant_demo",
            release_id=first.id,
            actor=admin,
            reason="initial release",
        )
        assert published.status == "published"
        assert authorize(
            settings,
            user=member,
            object_path="/api/enterprise/teams",
            action="POST",
            db=db,
        ).allowed

        with pytest.raises(PolicyLifecycleError, match="immutable"):
            update_policy_draft(
                db,
                settings,
                tenant_id="tenant_demo",
                release_id=published.id,
                actor=admin,
                policy_text=published.policy_text,
                expected_digest=published.policy_digest,
            )

        restricted_text = "\n".join(
            (
                "p, tenant_admin, *, /api/enterprise/*, (GET|POST|PUT|PATCH|DELETE), allow",
                "p, tenant_member, *, /api/enterprise/agents, GET, allow",
            )
        )
        second = create_policy_draft(
            db,
            settings,
            tenant_id="tenant_demo",
            actor=admin,
            policy_text=restricted_text,
            description="restricted member",
        )
        publish_policy(
            db,
            settings,
            tenant_id="tenant_demo",
            release_id=second.id,
            actor=admin,
            reason="least privilege",
        )
        assert not authorize(
            settings,
            user=member,
            object_path="/api/enterprise/teams",
            action="POST",
            db=db,
        ).allowed

        restored = rollback_policy(
            db,
            settings,
            tenant_id="tenant_demo",
            target_release_id=published.id,
            actor=admin,
            reason="restore collaboration",
        )
        assert restored.version == 3
        assert restored.source_release_id == published.id
        assert authorize(
            settings,
            user=member,
            object_path="/api/enterprise/teams",
            action="POST",
            db=db,
        ).allowed
        assert len(db.exec(select(AuthorizationPolicyEvent)).all()) == 5
        active = db.exec(
            select(AuthorizationPolicyRelease).where(
                AuthorizationPolicyRelease.status == "published"
            )
        ).one()
        assert active.id == restored.id


def test_context_policy_fails_closed_for_each_authorization_dimension() -> None:
    policies = [
        ContextPolicy(
            subject="listing_compliance_specialist",
            tenant_id="tenant_demo",
            department_id="listing_compliance_specialist",
            store_id="STORE-US",
            resource_id="store_1",
            action_pattern="READ",
        ),
        ContextPolicy(
            subject="service:listing_compliance_specialist",
            tenant_id="tenant_demo",
            department_id="listing_compliance_specialist",
            store_id="STORE-US",
            resource_id="store_1",
            action_pattern="READ",
        ),
    ]
    base = {
        "policies": policies,
        "subject_type": "human",
        "role": "listing_compliance_specialist",
        "tenant_id": "tenant_demo",
        "department_id": "listing_compliance_specialist",
        "store_id": "STORE-US",
        "resource_id": "store_1",
        "action": "READ",
    }
    assert authorize_context(**base).allowed
    assert authorize_context(**{**base, "subject_type": "service"}).allowed
    assert not authorize_context(**{**base, "role": "designer"}).allowed
    assert not authorize_context(**{**base, "tenant_id": "tenant_other"}).allowed
    assert not authorize_context(**{**base, "department_id": "designer"}).allowed
    assert not authorize_context(**{**base, "store_id": "STORE-EU"}).allowed
    assert not authorize_context(**{**base, "resource_id": "store_2"}).allowed
    assert not authorize_context(**{**base, "action": "REQUEST"}).allowed


def test_business_resource_context_honors_viewer_and_service_identity() -> None:
    engine = _engine()
    SQLModel.metadata.create_all(engine)
    settings = Settings(casbin_enabled=True)
    with Session(engine) as db:
        listing = _member("listing_compliance_specialist")
        db.add(Tenant(id="tenant_demo", name="Demo"))
        db.add(listing)
        resource = BusinessResource(
            id="store_1",
            tenant_id="tenant_demo",
            resource_type="store",
            code="STORE-US",
            name="US Store",
            created_by_user_id=listing.id,
        )
        db.add(resource)
        db.add(
            BusinessResourceScope(
                tenant_id="tenant_demo",
                resource_id=resource.id,
                business_role="listing_compliance_specialist",
                access_level="viewer",
            )
        )
        db.commit()

        assert authorize_business_resource(
            settings, db=db, user=listing, resource=resource, action="READ"
        ).allowed
        assert authorize_business_resource(
            settings,
            db=db,
            user=listing,
            resource=resource,
            action="READ",
            subject_type="service",
        ).allowed
        assert not authorize_business_resource(
            settings, db=db, user=listing, resource=resource, action="REQUEST"
        ).allowed
