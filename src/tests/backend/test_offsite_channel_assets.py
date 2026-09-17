from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db.models import (
    BusinessResource,
    BusinessResourceScope,
    OffsiteChannelEvidence,
    Tenant,
    User,
)
from app.offsite.schema import (
    OffsiteChannelAssetCreate,
    OffsiteChannelEvidenceCreate,
    OffsiteChannelReview,
)
from app.offsite.service import (
    add_channel_evidence,
    create_channel_asset,
    get_channel_asset,
    list_channel_assets,
    review_channel_asset,
)


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _user(user_id: str, role: str, *, tenant_id: str = "tenant_demo") -> User:
    return User(
        id=user_id,
        tenant_id=tenant_id,
        username=user_id,
        role="member",
        business_role=role,
        password_hash="disabled",
    )


@pytest.fixture
def db() -> Session:
    engine = _engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Tenant(id="tenant_demo", name="Demo"),
                Tenant(id="tenant_other", name="Other"),
            ]
        )
        yield session


@pytest.fixture
def workforce(db: Session) -> dict[str, User]:
    users = {
        "supervisor": _user("supervisor", "operations_supervisor"),
        "bd": _user("bd", "tiktok_bd_specialist"),
        "listing": _user("listing", "listing_compliance_specialist"),
        "other": _user("other", "operations_supervisor", tenant_id="tenant_other"),
    }
    db.add_all(users.values())
    db.commit()
    return users


@pytest.fixture
def stores(db: Session, workforce: dict[str, User]) -> dict[str, BusinessResource]:
    scoped = BusinessResource(
        tenant_id="tenant_demo",
        resource_type="store",
        code="AMZ-US-1",
        name="Amazon US scoped",
        created_by_user_id=workforce["supervisor"].id,
    )
    hidden = BusinessResource(
        tenant_id="tenant_demo",
        resource_type="store",
        code="AMZ-US-2",
        name="Amazon US hidden",
        created_by_user_id=workforce["supervisor"].id,
    )
    db.add_all([scoped, hidden])
    db.flush()
    db.add(
        BusinessResourceScope(
            tenant_id="tenant_demo",
            resource_id=scoped.id,
            business_role="tiktok_bd_specialist",
            access_level="operator",
        )
    )
    db.commit()
    return {"scoped": scoped, "hidden": hidden}


def _asset_request(store_id: str, *, stable_ref: str = "https://deals.example/channels/home"):
    return OffsiteChannelAssetCreate(
        tenant_id="tenant_demo",
        brand_key="brand.demo",
        store_resource_id=store_id,
        asset_type="deal_site",
        canonical_name="Example Deals",
        stable_external_ref=stable_ref,
        region="us",
        language="en-US",
        categories=["Home", "home", "Kitchen"],
    )


def _evidence_request(
    evidence_type: str,
    *,
    now: datetime,
    value=None,
    evidence_class: str = "observed_fact",
):
    return OffsiteChannelEvidenceCreate(
        tenant_id="tenant_demo",
        evidence_type=evidence_type,
        evidence_class=evidence_class,
        value=value or {"result": "reviewed", "sample_count": 3},
        source_type="authorized_import",
        source_record_id=f"import-20260908:{evidence_type}",
        ingestion_batch_id="batch-offsite-20260908",
        captured_at=now,
        expires_at=now + timedelta(days=30),
        confidence=0.9,
        rule_version="offsite-channel-evidence-v1",
    )


def _create_asset(
    db: Session,
    workforce: dict[str, User],
    stores: dict[str, BusinessResource],
):
    return create_channel_asset(
        db,
        request=_asset_request(stores["scoped"].id),
        idempotency_key="channel-create-001",
        user=workforce["bd"],
    )


def test_channel_creation_is_idempotent_normalized_and_store_scoped(
    db: Session,
    workforce: dict[str, User],
    stores: dict[str, BusinessResource],
) -> None:
    created = _create_asset(db, workforce, stores)
    replayed = create_channel_asset(
        db,
        request=_asset_request(stores["scoped"].id),
        idempotency_key="channel-create-001",
        user=workforce["bd"],
    )
    assert replayed.id == created.id
    assert created.categories == ["home", "kitchen"]
    assert created.region == "US"
    assert created.lifecycle_status == "discovered"
    assert created.execution_guard.status == "blocked"
    assert created.events[0].detail["stable_external_digest"].startswith("sha256:")

    create_channel_asset(
        db,
        request=OffsiteChannelAssetCreate(
            **{
                **_asset_request(stores["hidden"].id).model_dump(),
                "brand_key": "brand.hidden",
                "stable_external_ref": "https://other.example/deals",
            }
        ),
        idempotency_key="channel-create-hidden",
        user=workforce["supervisor"],
    )
    visible = list_channel_assets(db, tenant_id="tenant_demo", user=workforce["bd"])
    assert [item.id for item in visible] == [created.id]
    assert visible[0].evidence == []

    with pytest.raises(HTTPException) as hidden_store:
        create_channel_asset(
            db,
            request=OffsiteChannelAssetCreate(
                **{
                    **_asset_request(stores["hidden"].id).model_dump(),
                    "brand_key": "brand.denied",
                    "stable_external_ref": "https://denied.example/deals",
                }
            ),
            idempotency_key="channel-create-denied",
            user=workforce["bd"],
        )
    assert hidden_store.value.status_code == 404


def test_channel_identity_rejects_secret_urls_and_idempotency_drift(
    db: Session,
    workforce: dict[str, User],
    stores: dict[str, BusinessResource],
) -> None:
    _create_asset(db, workforce, stores)
    with pytest.raises(HTTPException) as drift:
        create_channel_asset(
            db,
            request=OffsiteChannelAssetCreate(
                **{
                    **_asset_request(stores["scoped"].id).model_dump(),
                    "canonical_name": "Changed name",
                }
            ),
            idempotency_key="channel-create-001",
            user=workforce["bd"],
        )
    assert drift.value.status_code == 409
    db.rollback()

    with pytest.raises(HTTPException) as secret:
        create_channel_asset(
            db,
            request=_asset_request(
                stores["scoped"].id,
                stable_ref="https://deals.example/list?access_token=must-not-persist",
            ),
            idempotency_key="channel-create-secret",
            user=workforce["bd"],
        )
    assert secret.value.status_code == 422

    with pytest.raises(HTTPException) as invalid_port:
        create_channel_asset(
            db,
            request=_asset_request(
                stores["scoped"].id,
                stable_ref="https://deals.example:invalid/list",
            ),
            idempotency_key="channel-create-invalid-port",
            user=workforce["bd"],
        )
    assert invalid_port.value.status_code == 422


def test_evidence_is_append_only_idempotent_and_blocks_direct_contact_data(
    db: Session,
    workforce: dict[str, User],
    stores: dict[str, BusinessResource],
) -> None:
    asset = _create_asset(db, workforce, stores)
    now = datetime.now(UTC)
    first = add_channel_evidence(
        db,
        asset_id=asset.id,
        request=_evidence_request("identity", now=now),
        idempotency_key="evidence-identity-001",
        user=workforce["bd"],
    )
    replay = add_channel_evidence(
        db,
        asset_id=asset.id,
        request=_evidence_request("identity", now=now),
        idempotency_key="evidence-identity-001",
        user=workforce["bd"],
    )
    assert len(first.evidence) == 1
    assert len(replay.evidence) == 1
    assert first.evidence[0].raw_hash.startswith("sha256:")

    with pytest.raises(HTTPException) as direct_contact:
        add_channel_evidence(
            db,
            asset_id=asset.id,
            request=_evidence_request(
                "contact_basis",
                now=now,
                value={"public_email": "person@example.com"},
            ),
            idempotency_key="evidence-contact-pii",
            user=workforce["bd"],
        )
    assert direct_contact.value.status_code == 422
    db.rollback()
    assert db.get(OffsiteChannelEvidence, first.evidence[0].id) is not None


def test_verified_review_requires_manager_current_complete_citations_and_becomes_stale(
    db: Session,
    workforce: dict[str, User],
    stores: dict[str, BusinessResource],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = _create_asset(db, workforce, stores)
    current = review_channel_asset(
        db,
        asset_id=asset.id,
        request=OffsiteChannelReview(
            tenant_id="tenant_demo",
            expected_version=asset.version,
            lifecycle_status="candidate",
            reason="Initial identity has been accepted for verification.",
        ),
        user=workforce["supervisor"],
    )
    current = review_channel_asset(
        db,
        asset_id=asset.id,
        request=OffsiteChannelReview(
            tenant_id="tenant_demo",
            expected_version=current.version,
            lifecycle_status="verifying",
            reason="Verification work is now in progress.",
        ),
        user=workforce["supervisor"],
    )
    now = datetime.now(UTC)
    evidence_ids: list[str] = []
    for index, evidence_type in enumerate(
        ["identity", "audience_fit", "terms", "fees", "contact_basis"]
    ):
        current = add_channel_evidence(
            db,
            asset_id=asset.id,
            request=_evidence_request(evidence_type, now=now),
            idempotency_key=f"evidence-required-{index:02d}",
            user=workforce["bd"],
        )
        evidence_ids.append(
            next(item.id for item in current.evidence if item.evidence_type == evidence_type)
        )

    with pytest.raises(HTTPException) as non_manager:
        review_channel_asset(
            db,
            asset_id=asset.id,
            request=OffsiteChannelReview(
                tenant_id="tenant_demo",
                expected_version=current.version,
                lifecycle_status="verified",
                tier="tier_2",
                evidence_ids=evidence_ids,
                reason="All mandatory evidence was checked by the operator.",
            ),
            user=workforce["bd"],
        )
    assert non_manager.value.status_code == 403
    db.rollback()

    reloaded = get_channel_asset(
        db,
        tenant_id="tenant_demo",
        asset_id=asset.id,
        user=workforce["supervisor"],
    )
    with pytest.raises(HTTPException) as incomplete:
        review_channel_asset(
            db,
            asset_id=asset.id,
            request=OffsiteChannelReview(
                tenant_id="tenant_demo",
                expected_version=reloaded.version,
                lifecycle_status="verified",
                tier="tier_2",
                evidence_ids=evidence_ids[:2],
                reason="This incomplete evidence set must not pass verification.",
            ),
            user=workforce["supervisor"],
        )
    assert incomplete.value.status_code == 409
    db.rollback()

    reloaded = get_channel_asset(
        db,
        tenant_id="tenant_demo",
        asset_id=asset.id,
        user=workforce["supervisor"],
    )
    verified = review_channel_asset(
        db,
        asset_id=asset.id,
        request=OffsiteChannelReview(
            tenant_id="tenant_demo",
            expected_version=reloaded.version,
            lifecycle_status="verified",
            tier="tier_2",
            evidence_ids=evidence_ids,
            reason="Identity, audience, terms, fees and contact basis are current.",
        ),
        user=workforce["supervisor"],
    )
    assert verified.execution_guard.status == "eligible_for_proposal"
    assert verified.freshness_status == "fresh"
    assert verified.last_verified_at is not None
    assert [event.event_type for event in verified.events].count("asset_reviewed") == 3
    assert verified.events[-1].detail["from_tier"] == "unassigned"
    assert verified.events[-1].detail["to_tier"] == "tier_2"
    assert all(event.detail.get("external_action") != "executed" for event in verified.events)

    future = verified.evidence[0].expires_at + timedelta(seconds=1)
    monkeypatch.setattr("app.offsite.service.utc_now", lambda: future)
    stale = get_channel_asset(
        db,
        tenant_id="tenant_demo",
        asset_id=asset.id,
        user=workforce["supervisor"],
    )
    assert stale.lifecycle_status == "verified"
    assert stale.effective_lifecycle_status == "needs_review"
    assert stale.execution_guard.status == "blocked"
    assert stale.expired_required_evidence


def test_human_judgment_does_not_satisfy_required_sourced_evidence(
    db: Session,
    workforce: dict[str, User],
    stores: dict[str, BusinessResource],
) -> None:
    asset = _create_asset(db, workforce, stores)
    current = review_channel_asset(
        db,
        asset_id=asset.id,
        request=OffsiteChannelReview(
            tenant_id="tenant_demo",
            expected_version=asset.version,
            lifecycle_status="candidate",
            reason="The channel is ready to enter evidence verification.",
        ),
        user=workforce["supervisor"],
    )
    current = review_channel_asset(
        db,
        asset_id=asset.id,
        request=OffsiteChannelReview(
            tenant_id="tenant_demo",
            expected_version=current.version,
            lifecycle_status="verifying",
            reason="The evidence collection phase has now started.",
        ),
        user=workforce["supervisor"],
    )
    judgment = add_channel_evidence(
        db,
        asset_id=asset.id,
        request=_evidence_request(
            "identity",
            now=datetime.now(UTC),
            evidence_class="human_judgment",
        ),
        idempotency_key="evidence-human-judgment-identity",
        user=workforce["bd"],
    )
    judgment_id = next(item.id for item in judgment.evidence if item.evidence_type == "identity")

    with pytest.raises(HTTPException) as unsupported:
        review_channel_asset(
            db,
            asset_id=asset.id,
            request=OffsiteChannelReview(
                tenant_id="tenant_demo",
                expected_version=judgment.version,
                lifecycle_status="verified",
                tier="tier_3",
                evidence_ids=[judgment_id],
                reason="Human judgment alone must not establish verified identity.",
            ),
            user=workforce["supervisor"],
        )
    assert unsupported.value.status_code == 409
    assert "identity" in unsupported.value.detail


def test_cross_tenant_bola_and_wrong_role_are_rejected(
    db: Session,
    workforce: dict[str, User],
    stores: dict[str, BusinessResource],
) -> None:
    asset = _create_asset(db, workforce, stores)
    with pytest.raises(HTTPException) as cross_tenant:
        get_channel_asset(
            db,
            tenant_id="tenant_demo",
            asset_id=asset.id,
            user=workforce["other"],
        )
    assert cross_tenant.value.status_code == 403
    with pytest.raises(HTTPException) as wrong_role:
        list_channel_assets(db, tenant_id="tenant_demo", user=workforce["listing"])
    assert wrong_role.value.status_code == 403


def test_postgres_migration_has_rls_append_only_and_composite_tenant_fks() -> None:
    migration = (
        Path(__file__).parents[2]
        / "backend"
        / "migrations"
        / "20260908_offsite_channel_assets_v1.sql"
    ).read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "offsite_channel_evidence_append_only" in migration
    assert "offsite_channel_events_append_only" in migration
    assert "FOREIGN KEY (tenant_id, brand_key, asset_id)" in migration
    assert "app.current_staffdeck_tenant_id()" in migration
