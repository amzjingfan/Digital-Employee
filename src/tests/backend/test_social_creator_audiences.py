from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.api.social import router as social_router
from app.db import get_session
from app.db.models import (
    AuthorizationDecision,
    BusinessResource,
    BusinessResourceScope,
    SocialAudienceSnapshot,
    SocialCreator,
    SocialCreatorEvidence,
    SocialDomainEvent,
    Tenant,
    User,
)
from app.security.auth import create_access_token
from app.security.authorization import require_enterprise_permission
from app.social.schema import (
    SocialAudienceCreate,
    SocialAudienceFilters,
    SocialCreatorCreate,
    SocialCreatorEvidenceInput,
)
from app.social.service import (
    add_creator_evidence,
    create_creator,
    freeze_audience,
    get_audience,
    list_creators,
)


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _user(user_id: str, tenant_id: str, business_role: str, *, admin: bool = False) -> User:
    return User(
        id=user_id,
        tenant_id=tenant_id,
        username=user_id,
        role="admin" if admin else "member",
        business_role=business_role,
        password_hash="disabled",
    )


@pytest.fixture
def seeded() -> tuple[Session, dict[str, User]]:
    engine = _engine()
    SQLModel.metadata.create_all(engine)
    db = Session(engine)
    users = {
        "admin": _user("admin", "tenant_demo", "platform_admin", admin=True),
        "bd": _user("bd", "tenant_demo", "tiktok_bd_specialist"),
        "tap": _user("tap", "tenant_demo", "tiktok_tap_manager"),
        "content": _user("content", "tenant_demo", "tiktok_content_specialist"),
        "other_bd": _user("other-bd", "tenant_other", "tiktok_bd_specialist"),
    }
    db.add_all([Tenant(id="tenant_demo", name="Demo"), Tenant(id="tenant_other", name="Other")])
    db.add_all(users.values())
    db.add_all(
        [
            BusinessResource(
                id="brand_demo",
                tenant_id="tenant_demo",
                resource_type="social_account",
                code="BRAND-DEMO",
                name="Demo Brand",
                created_by_user_id=users["admin"].id,
            ),
            BusinessResource(
                id="brand_other",
                tenant_id="tenant_other",
                resource_type="social_account",
                code="BRAND-OTHER",
                name="Other Brand",
                created_by_user_id=users["other_bd"].id,
            ),
            BusinessResourceScope(
                tenant_id="tenant_demo",
                resource_id="brand_demo",
                business_role="tiktok_bd_specialist",
                access_level="operator",
            ),
            BusinessResourceScope(
                tenant_id="tenant_demo",
                resource_id="brand_demo",
                business_role="tiktok_tap_manager",
                access_level="operator",
            ),
            BusinessResourceScope(
                tenant_id="tenant_other",
                resource_id="brand_other",
                business_role="tiktok_bd_specialist",
                access_level="operator",
            ),
        ]
    )
    db.commit()
    yield db, users
    db.close()


def _creator_payload(
    provider_id: str,
    *,
    name: str = "Creator One",
    expired: bool = False,
    category: str = "beauty",
    quality_score: int = 90,
) -> SocialCreatorCreate:
    now = datetime.now(UTC)
    observed = now - timedelta(days=40 if expired else 1)
    expires = now - timedelta(days=1) if expired else now + timedelta(days=29)
    return SocialCreatorCreate.model_validate(
        {
            "canonical_name": name,
            "identity": {
                "platform": "tiktok",
                "provider_identity_id": provider_id,
                "public_handle": f"@{provider_id}",
                "profile_url": f"https://www.tiktok.com/@{provider_id}",
                "verified": True,
            },
            "evidence": {
                "country_code": "us",
                "language_code": "en",
                "category": category,
                "followers_count": 50_000,
                "engagement_rate_bps": 550,
                "audience_country_code": "us",
                "estimated_cost_minor": 50_000,
                "currency": "usd",
                "quality_score": quality_score,
                "source_ref": f"contract-feed:{provider_id}:v1",
                "data_rights_basis": "contract_authorized",
                "contact_basis": "contract_authorized",
                "observed_at": observed.isoformat(),
                "expires_at": expires.isoformat(),
            },
        }
    )


def test_creator_identity_is_tenant_scoped_and_idempotent(seeded) -> None:
    db, users = seeded
    payload = _creator_payload("creator-001")

    first = create_creator(
        db,
        user=users["bd"],
        request=payload,
        idempotency_key="creator-demo-0001",
        request_id="req-create-1",
    )
    replay = create_creator(
        db,
        user=users["bd"],
        request=payload,
        idempotency_key="creator-demo-0001",
        request_id="req-create-replay",
    )
    other_tenant = create_creator(
        db,
        user=users["other_bd"],
        request=payload,
        idempotency_key="creator-demo-0001",
        request_id="req-create-other",
    )

    assert replay.id == first.id
    assert other_tenant.id != first.id
    assert len(db.exec(select(SocialCreator)).all()) == 2
    assert len(db.exec(select(SocialDomainEvent)).all()) == 2
    assert [
        row.id for row in list_creators(db, user=users["bd"], filters=SocialAudienceFilters())
    ] == [first.id]
    assert [
        row.id for row in list_creators(db, user=users["other_bd"], filters=SocialAudienceFilters())
    ] == [other_tenant.id]

    changed = payload.model_copy(update={"canonical_name": "Different Name"})
    with pytest.raises(HTTPException) as conflict:
        create_creator(
            db,
            user=users["bd"],
            request=changed,
            idempotency_key="creator-demo-0001",
            request_id="req-create-conflict",
        )
    assert conflict.value.status_code == 409


def test_stale_evidence_is_not_silently_used_and_refresh_is_append_only(seeded) -> None:
    db, users = seeded
    stale = create_creator(
        db,
        user=users["bd"],
        request=_creator_payload("creator-stale", expired=True),
        idempotency_key="creator-stale-01",
        request_id="req-stale",
    )
    assert stale.status == "needs_review"
    assert list_creators(db, user=users["tap"], filters=SocialAudienceFilters()) == []
    included = list_creators(
        db,
        user=users["tap"],
        filters=SocialAudienceFilters(include_stale=True),
    )
    assert included[0].identities[0].latest_evidence is not None
    assert included[0].identities[0].latest_evidence.stale is True

    identity_id = stale.identities[0].id
    now = datetime.now(UTC)
    refresh = SocialCreatorEvidenceInput(
        country_code="US",
        language_code="en",
        category="beauty",
        followers_count=60_000,
        engagement_rate_bps=600,
        audience_country_code="US",
        estimated_cost_minor=55_000,
        currency="USD",
        quality_score=95,
        source_ref="contract-feed:creator-stale:v2",
        data_rights_basis="contract_authorized",
        contact_basis="contract_authorized",
        observed_at=now,
        expires_at=now + timedelta(days=30),
    )
    evidence = add_creator_evidence(
        db,
        user=users["bd"],
        creator_id=stale.id,
        identity_id=identity_id,
        request=refresh,
        idempotency_key="evidence-refresh-01",
        request_id="req-refresh",
    )
    replay = add_creator_evidence(
        db,
        user=users["bd"],
        creator_id=stale.id,
        identity_id=identity_id,
        request=refresh,
        idempotency_key="evidence-refresh-01",
        request_id="req-refresh-replay",
    )
    assert replay.id == evidence.id
    assert evidence.stale is False
    assert len(db.exec(select(SocialCreatorEvidence)).all()) == 2
    assert (
        list_creators(db, user=users["tap"], filters=SocialAudienceFilters())[0].status == "active"
    )


def test_multidimensional_filter_freezes_immutable_brand_scoped_snapshot(seeded) -> None:
    db, users = seeded
    eligible = create_creator(
        db,
        user=users["bd"],
        request=_creator_payload("creator-eligible"),
        idempotency_key="creator-eligible-01",
        request_id="req-eligible",
    )
    create_creator(
        db,
        user=users["bd"],
        request=_creator_payload("creator-low-quality", quality_score=40),
        idempotency_key="creator-low-quality-01",
        request_id="req-low-quality",
    )
    create_creator(
        db,
        user=users["bd"],
        request=_creator_payload("creator-expired", expired=True),
        idempotency_key="creator-expired-01",
        request_id="req-expired",
    )
    request = SocialAudienceCreate(
        brand_id="brand_demo",
        filters=SocialAudienceFilters(
            platform="tiktok",
            country_code="US",
            language_code="en",
            category="Beauty",
            min_followers=10_000,
            max_followers=100_000,
            min_engagement_rate_bps=500,
            audience_country_code="US",
            max_estimated_cost_minor=60_000,
            currency="USD",
            min_quality_score=80,
            require_contactable=True,
        ),
    )
    snapshot = freeze_audience(
        db,
        user=users["tap"],
        request=request,
        idempotency_key="audience-beauty-01",
        request_id="req-audience",
    )
    replay = freeze_audience(
        db,
        user=users["tap"],
        request=request,
        idempotency_key="audience-beauty-01",
        request_id="req-audience-replay",
    )

    assert snapshot.id == replay.id
    assert snapshot.creator_ids == [eligible.id]
    assert snapshot.creator_count == 1
    assert snapshot.audience_hash.startswith("sha256:")
    assert len(db.exec(select(SocialAudienceSnapshot)).all()) == 1
    event = db.exec(
        select(SocialDomainEvent).where(SocialDomainEvent.event_type == "audience_frozen")
    ).one()
    assert event.detail_json["outreach_authorized"] is False

    changed_request = request.model_copy(
        update={"filters": request.filters.model_copy(update={"min_quality_score": 91})}
    )
    with pytest.raises(HTTPException) as mismatch:
        freeze_audience(
            db,
            user=users["tap"],
            request=changed_request,
            idempotency_key="audience-beauty-01",
            request_id="req-audience-mismatch",
        )
    assert mismatch.value.status_code == 409

    with pytest.raises(HTTPException) as foreign_brand:
        freeze_audience(
            db,
            user=users["bd"],
            request=SocialAudienceCreate(brand_id="brand_other", filters=request.filters),
            idempotency_key="audience-foreign-01",
            request_id="req-audience-foreign",
        )
    assert foreign_brand.value.status_code == 404

    with pytest.raises(HTTPException) as foreign_snapshot:
        get_audience(db, user=users["other_bd"], audience_id=snapshot.id)
    assert foreign_snapshot.value.status_code == 404


def test_contact_plaintext_is_rejected_and_unrelated_role_cannot_read(seeded) -> None:
    db, users = seeded
    raw = _creator_payload("creator-private").model_dump(mode="json")
    raw["evidence"]["email"] = "creator@acme.com"
    with pytest.raises(ValidationError, match="extra_forbidden"):
        SocialCreatorCreate.model_validate(raw)

    raw = _creator_payload("creator-private-source").model_dump(mode="json")
    raw["evidence"]["source_ref"] = "supplier:creator@acme.com"
    with pytest.raises(ValidationError, match="contact address"):
        SocialCreatorCreate.model_validate(raw)

    raw = _creator_payload("creator-blank-source").model_dump(mode="json")
    raw["evidence"]["source_ref"] = "   "
    with pytest.raises(ValidationError, match="at least 3 characters"):
        SocialCreatorCreate.model_validate(raw)

    raw = _creator_payload("creator-wrong-source-type").model_dump(mode="json")
    raw["evidence"]["source_ref"] = 123
    with pytest.raises(ValidationError, match="valid string"):
        SocialCreatorCreate.model_validate(raw)

    create_creator(
        db,
        user=users["bd"],
        request=_creator_payload("creator-role-test"),
        idempotency_key="creator-role-test-01",
        request_id="req-role-test",
    )
    with pytest.raises(HTTPException) as forbidden:
        list_creators(db, user=users["content"], filters=SocialAudienceFilters())
    assert forbidden.value.status_code == 403


def test_social_api_enforces_policy_auth_idempotency_and_audit() -> None:
    engine = _engine()
    SQLModel.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(social_router, dependencies=[Depends(require_enterprise_permission)])

    def override_session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_session] = override_session
    with Session(engine) as db:
        db.add(Tenant(id="tenant_demo", name="Demo"))
        bd = _user("bd", "tenant_demo", "tiktok_bd_specialist")
        tap = _user("tap", "tenant_demo", "tiktok_tap_manager")
        db.add_all([bd, tap])
        db.commit()
        db.refresh(bd)
        db.refresh(tap)
        bd_token = create_access_token(bd)
        tap_token = create_access_token(tap)

    client = TestClient(app)
    payload = _creator_payload("creator-api").model_dump(mode="json")
    unauthenticated = client.post(
        "/api/v1/social/creators",
        json=payload,
        headers={"Idempotency-Key": "creator-api-0001"},
    )
    assert unauthenticated.status_code == 401

    forbidden = client.post(
        "/api/v1/social/creators",
        json=payload,
        headers={
            "Authorization": f"Bearer {tap_token}",
            "Idempotency-Key": "creator-api-tap-01",
        },
    )
    assert forbidden.status_code == 403

    created = client.post(
        "/api/v1/social/creators",
        json=payload,
        headers={
            "Authorization": f"Bearer {bd_token}",
            "Idempotency-Key": "creator-api-0001",
        },
    )
    assert created.status_code == 201
    assert created.json()["identities"][0]["latest_evidence"]["source_ref"] == (
        "contract-feed:creator-api:v1"
    )
    assert "email" not in str(created.json()).lower()

    invalid_filters = client.get(
        "/api/v1/social/creators?min_followers=20&max_followers=10",
        headers={"Authorization": f"Bearer {bd_token}"},
    )
    assert invalid_filters.status_code == 422
    with Session(engine) as db:
        decisions = db.exec(select(AuthorizationDecision)).all()
        assert {(row.role, row.effect) for row in decisions} == {
            ("tiktok_tap_manager", "deny"),
            ("tiktok_bd_specialist", "allow"),
        }


def test_postgres_migration_enforces_rls_tenant_links_and_append_only_records() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "migrations"
        / "20260908_social_creator_audiences_v1.sql"
    ).read_text(encoding="utf-8")

    assert migration.count("CREATE TABLE IF NOT EXISTS public.social_") == 5
    assert "created_at timestamptz NOT NULL" in migration
    assert "FOREIGN KEY (tenant_id, identity_id, creator_id)" in migration
    assert "FUNCTION public.enforce_social_brand_tenant_scope()" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "WITH CHECK (tenant_id = app.current_staffdeck_tenant_id())" in migration
    assert migration.count("EXECUTE FUNCTION public.reject_social_append_only_change()") == 3
    assert "GRANT SELECT, INSERT ON public.social_creator_evidence" in migration
