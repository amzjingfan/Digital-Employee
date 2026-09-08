from __future__ import annotations

import base64
import hashlib
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.business_resources.schema import BusinessResourceCreate, ResourceScopeInput
from app.business_resources.service import create_resource
from app.config import get_settings
from app.db.models import (
    BusinessActionExecution,
    HighRiskActionRequest,
    Tenant,
    User,
    utc_now,
)
from app.product_lifecycle.schema import (
    CreativeAssetReview,
    CreativeAssetVersionCreate,
    CreativeBriefCreate,
    CreativeDeliveryChecklistCreate,
    CreativeEvidenceSyncItem,
    CreativeEvidenceSyncRequest,
    CreativeGenerationSubmit,
    DesignQCRun,
    ListingComplianceRun,
    ListingRuleSetCreate,
    ListingRuleSetPublish,
    ProcurementRecommendationCreate,
    ProcurementRecommendationReview,
    ProductLaunchGateCreate,
    ProductLaunchSubmit,
    RuleSourceReference,
)
from app.product_lifecycle.service import (
    create_creative_asset_version,
    create_creative_brief,
    create_creative_delivery_checklist,
    create_listing_rule_set,
    create_procurement_recommendation,
    evaluate_product_launch_gate,
    expire_creative_evidence_records,
    list_creative_assets,
    list_creative_briefs,
    product_lifecycle_overview,
    publish_listing_rule_set,
    review_creative_asset_version,
    review_procurement_recommendation,
    run_creative_asset_qc,
    run_listing_compliance_check,
    stage_creative_asset_upload,
    submit_creative_generation,
    submit_product_launch,
    sync_creative_evidence,
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


@pytest.fixture(autouse=True)
def local_creative_storage_for_unit_tests(monkeypatch: pytest.MonkeyPatch):
    """Keep SQLite unit tests independent from the production MinIO profile."""
    monkeypatch.setenv("CREATIVE_OBJECT_STORAGE_BACKEND", "local")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db() -> Session:
    engine = _engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [Tenant(id="tenant_demo", name="Demo"), Tenant(id="tenant_other", name="Other")]
        )
        session.commit()
        yield session


@pytest.fixture
def workforce(db: Session) -> dict[str, User]:
    users = {
        "supervisor": _user("supervisor", "operations_supervisor"),
        "listing": _user("listing", "listing_compliance_specialist"),
        "designer": _user("designer", "designer"),
        "procurement": _user("procurement", "procurement_specialist"),
        "advertising": _user("advertising", "advertising_inspection_specialist"),
        "other": _user("other", "operations_supervisor", tenant_id="tenant_other"),
    }
    db.add_all(users.values())
    db.commit()
    return users


@pytest.fixture
def resources(db: Session, workforce: dict[str, User]) -> dict[str, str]:
    store = create_resource(
        db,
        request=BusinessResourceCreate(
            tenant_id="tenant_demo",
            resource_type="store",
            code="AMZ-US",
            name="Amazon US",
        ),
        user=workforce["supervisor"],
    )
    supplier = create_resource(
        db,
        request=BusinessResourceCreate(
            tenant_id="tenant_demo",
            resource_type="supplier",
            code="SUP-001",
            name="Reviewed Supplier",
        ),
        user=workforce["supervisor"],
    )
    return {"store": store.id, "supplier": supplier.id}


def _rule(db: Session, workforce: dict[str, User]):
    draft = create_listing_rule_set(
        db,
        request=ListingRuleSetCreate(
            tenant_id="tenant_demo",
            platform="Amazon",
            marketplace="US",
            category="Electronics",
            version="2026.09.1",
            rules={
                "banned_terms": ["cure"],
                "restricted_terms": [
                    {
                        "term": "FDA approved",
                        "required_certification": "FDA",
                        "gate": "block",
                    }
                ],
                "required_certifications": ["FCC"],
                "required_labels": ["Made in China"],
                "intellectual_property_terms": ["Apple AirTag"],
                "optimization_terms": ["wireless"],
                "max_title_chars": 180,
                "required_content_fields": ["title", "bullets", "description"],
            },
            source_references=[
                RuleSourceReference(
                    source_id="amazon-style-guide-electronics-2026-09",
                    title="Amazon US Electronics style guide",
                    url="https://sellercentral.amazon.com/help/example",
                    retrieved_at=utc_now(),
                )
            ],
            effective_at=utc_now() - timedelta(days=1),
            expires_at=utc_now() + timedelta(days=90),
        ),
        user=workforce["listing"],
    )
    return publish_listing_rule_set(
        db,
        rule_set_id=draft.id,
        request=ListingRuleSetPublish(
            tenant_id="tenant_demo",
            expected_digest=draft.content_digest,
            review_note="Official source and controls reviewed by operations.",
        ),
        user=workforce["supervisor"],
    )


def _brief_and_asset(db: Session, workforce: dict[str, User], resources: dict[str, str]):
    brief = create_creative_brief(
        db,
        request=CreativeBriefCreate(
            tenant_id="tenant_demo",
            brief_key="BRIEF-SKU-1001",
            store_resource_id=resources["store"],
            product_key="PRODUCT-1001",
            language="en-US",
            dimensions={"width": 2000, "height": 2000, "unit": "px"},
            selling_points=["Wireless control", "Compact enclosure"],
            scenes=["Home office"],
            required_assets=["main_image"],
            constraints={"background": "white", "safe_area_percent": 5},
            fact_snapshot={
                "source_ref": "sku-facts/PRODUCT-1001",
                "version": "facts-v3",
                "status": "verified",
                "facts": {"material": "ABS"},
            },
            brand_snapshot={
                "source_ref": "brand-kit/joukir",
                "version": "brand-v2",
                "status": "verified",
                "logo": {"clear_space": 24},
            },
            platform_spec_snapshot={
                "source_ref": "amazon-us/electronics",
                "version": "spec-v5",
                "status": "verified",
                "module": "main_image",
            },
            due_at=utc_now() + timedelta(days=3),
        ),
        user=workforce["designer"],
    )
    asset = create_creative_asset_version(
        db,
        request=CreativeAssetVersionCreate(
            tenant_id="tenant_demo",
            asset_key="ASSET-SKU-1001-MAIN",
            brief_id=brief.id,
            asset_type="main_image",
            file_reference="s3://tenant-demo/reviewed/sku-1001-main-v1.png",
            file_digest="sha256:asset-main-v1",
            provenance={
                "source": "in-house-photo-and-controlled-ai-edit",
                "license": "tenant-owned",
                "model": "image-editor-v2",
            },
            generation_parameters={"background_cleanup": True, "seed": 42},
            checks={
                "dimensions": True,
                "clarity": True,
                "text_safe_area": True,
                "logo": True,
                "brand_colors": True,
                "factual_consistency": True,
                "copyright": True,
            },
        ),
        user=workforce["designer"],
    )
    sync_creative_evidence(
        db,
        request=CreativeEvidenceSyncRequest(
            tenant_id="tenant_demo",
            records=[
                CreativeEvidenceSyncItem(
                    evidence_type="facts",
                    source_ref="sku-facts/PRODUCT-1001",
                    version="facts-v3",
                    payload=brief.fact_snapshot,
                    effective_at=utc_now() - timedelta(days=1),
                    expires_at=utc_now() + timedelta(days=30),
                ),
                CreativeEvidenceSyncItem(
                    evidence_type="brand",
                    source_ref="brand-kit/joukir",
                    version="brand-v2",
                    payload=brief.brand_snapshot,
                    effective_at=utc_now() - timedelta(days=1),
                    expires_at=utc_now() + timedelta(days=30),
                ),
                CreativeEvidenceSyncItem(
                    evidence_type="platform_spec",
                    source_ref="amazon-us/electronics",
                    version="spec-v5",
                    payload=brief.platform_spec_snapshot,
                    effective_at=utc_now() - timedelta(days=1),
                    expires_at=utc_now() + timedelta(days=30),
                ),
            ],
        ),
        user=workforce["supervisor"],
    )
    run_creative_asset_qc(
        db,
        request=DesignQCRun(tenant_id="tenant_demo", asset_version_id=asset.id),
        user=workforce["designer"],
    )
    return brief, asset


def test_creative_brief_and_asset_reads_follow_store_scope(
    db: Session, workforce: dict[str, User], resources: dict[str, str]
) -> None:
    """A tenant-wide user must not infer store access from a shared brief id."""
    restricted_store = create_resource(
        db,
        request=BusinessResourceCreate(
            tenant_id="tenant_demo",
            resource_type="store",
            code="AMZ-RESTRICTED",
            name="Restricted Amazon store",
            scopes=[
                ResourceScopeInput(
                    business_role="listing_compliance_specialist", access_level="operator"
                )
            ],
        ),
        user=workforce["supervisor"],
    )
    visible_brief, visible_asset = _brief_and_asset(db, workforce, resources)
    hidden_brief = create_creative_brief(
        db,
        request=CreativeBriefCreate(
            tenant_id="tenant_demo",
            brief_key="BRIEF-RESTRICTED-1001",
            store_resource_id=restricted_store.id,
            product_key="PRODUCT-RESTRICTED-1001",
            language="en-US",
            dimensions={"width": 1600, "height": 1600, "unit": "px"},
            selling_points=["Restricted store product"],
            scenes=["Product detail"],
            required_assets=["main_image"],
        ),
        user=workforce["supervisor"],
    )

    briefs = list_creative_briefs(db, tenant_id="tenant_demo", user=workforce["designer"])
    assets = list_creative_assets(db, tenant_id="tenant_demo", user=workforce["designer"])

    assert [item.id for item in briefs] == [visible_brief.id]
    assert [item.id for item in assets] == [visible_asset.id]
    with pytest.raises(HTTPException) as error:
        create_creative_asset_version(
            db,
            request=CreativeAssetVersionCreate(
                tenant_id="tenant_demo",
                asset_key="ASSET-RESTRICTED-MAIN",
                brief_id=hidden_brief.id,
                asset_type="main_image",
                file_reference="s3://restricted/main.png",
                file_digest="sha256:restricted",
                provenance={"source": "tenant-owned", "license": "tenant-owned"},
                checks={
                    "dimensions": True,
                    "clarity": True,
                    "text_safe_area": True,
                    "logo": True,
                    "brand_colors": True,
                    "factual_consistency": True,
                    "copyright": True,
                },
            ),
            user=workforce["designer"],
        )
    assert error.value.status_code == 404


def test_creative_upload_manifest_is_server_verified_before_asset_registration(
    db: Session,
    workforce: dict[str, User],
    resources: dict[str, str],
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The asset API accepts an upload only when the staged bytes match its digest."""
    monkeypatch.setenv("ULTRARAG_DATA_DIR", str(tmp_path / "data"))
    brief, _ = _brief_and_asset(db, workforce, resources)
    creative_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    with pytest.raises(HTTPException) as invalid_upload:
        stage_creative_asset_upload(
            db,
            tenant_id="tenant_demo",
            brief_id=brief.id,
            filename="not-a-png.png",
            content_type="image/png",
            data=b"not actually a png",
            user=workforce["designer"],
        )
    assert invalid_upload.value.status_code == 422
    upload = stage_creative_asset_upload(
        db,
        tenant_id="tenant_demo",
        brief_id=brief.id,
        filename="main-v2.png",
        content_type="image/png",
        data=creative_bytes,
        user=workforce["designer"],
    )

    assert upload.file_reference == f"attachment://{upload.upload_id}"
    assert upload.file_digest == "sha256:" + hashlib.sha256(creative_bytes).hexdigest()
    asset = create_creative_asset_version(
        db,
        request=CreativeAssetVersionCreate(
            tenant_id="tenant_demo",
            asset_key="ASSET-SKU-1001-SECONDARY",
            brief_id=brief.id,
            asset_type="secondary_image",
            file_reference=upload.file_reference,
            file_digest=upload.file_digest,
            provenance={"source": "tenant-upload", "license": "tenant-owned"},
            checks={
                "dimensions": True,
                "clarity": True,
                "text_safe_area": True,
                "logo": True,
                "brand_colors": True,
                "factual_consistency": True,
                "copyright": True,
            },
        ),
        user=workforce["designer"],
    )
    assert asset.status == "pending_review"

    with pytest.raises(HTTPException) as error:
        create_creative_asset_version(
            db,
            request=CreativeAssetVersionCreate(
                tenant_id="tenant_demo",
                asset_key="ASSET-SKU-1001-ALTERED",
                brief_id=brief.id,
                asset_type="secondary_image",
                file_reference=upload.file_reference,
                file_digest="sha256:" + "0" * 64,
                provenance={"source": "tenant-upload", "license": "tenant-owned"},
                checks={
                    "dimensions": True,
                    "clarity": True,
                    "text_safe_area": True,
                    "logo": True,
                    "brand_colors": True,
                    "factual_consistency": True,
                    "copyright": True,
                },
            ),
            user=workforce["designer"],
        )
    assert error.value.status_code == 409


def test_creative_brief_captures_evidence_snapshots_and_digest(
    db: Session, workforce: dict[str, User], resources: dict[str, str]
) -> None:
    brief = create_creative_brief(
        db,
        request=CreativeBriefCreate(
            tenant_id="tenant_demo",
            brief_key="BRIEF-SNAPSHOT-1001",
            store_resource_id=resources["store"],
            product_key="PRODUCT-SNAPSHOT-1001",
            language="en-US",
            dimensions={"width": 2000, "height": 2000, "unit": "px"},
            selling_points=["Evidence-backed design"],
            scenes=["Main image"],
            required_assets=["main_image"],
            fact_snapshot={
                "source_ref": "catalog:product-snapshot-1001",
                "version": "facts-v2",
                "status": "verified",
                "facts": {"material": "ABS"},
            },
            brand_snapshot={
                "source_ref": "brand:joukir-v3",
                "version": "brand-v3",
                "status": "verified",
                "colors": ["#315EA8"],
            },
            platform_spec_snapshot={
                "source_ref": "amazon:us:electronics",
                "version": "spec-v5",
                "status": "verified",
                "module": "main_image",
                "width": 2000,
                "height": 2000,
            },
        ),
        user=workforce["designer"],
    )

    assert brief.fact_snapshot["version"] == "facts-v2"
    assert brief.brand_snapshot["version"] == "brand-v3"
    assert brief.platform_spec_snapshot["module"] == "main_image"
    assert brief.snapshot_digest.startswith("sha256:")


def _procurement(db: Session, workforce: dict[str, User], resources: dict[str, str]):
    return create_procurement_recommendation(
        db,
        request=ProcurementRecommendationCreate(
            tenant_id="tenant_demo",
            recommendation_key="PROC-SKU-1001-2026-09",
            supplier_resource_id=resources["supplier"],
            store_resource_id=None,
            product_key="PRODUCT-1001",
            sku="SKU-1001",
            forecast_daily_sales=10,
            planning_horizon_days=30,
            available_units=80,
            inbound_units=40,
            safety_stock_units=50,
            promotion_units=30,
            advertising_lift_units=20,
            moq=100,
            lead_time_days=15,
            quote_unit_cost=8,
            freight_unit_cost=1,
            duty_unit_cost=0.5,
            quote_observed_at=utc_now(),
            qc_failure_rate=0.01,
            cash_budget=5000,
            currency="USD",
        ),
        user=workforce["procurement"],
    )


def _clean_listing_request(
    *, store_id: str, rule_id: str, asset_ids: list[str], check_key: str = "CHECK-1001"
) -> ListingComplianceRun:
    return ListingComplianceRun(
        tenant_id="tenant_demo",
        check_key=check_key,
        store_resource_id=store_id,
        product_key="PRODUCT-1001",
        sku="SKU-1001",
        language="en-US",
        rule_set_id=rule_id,
        sku_fact_version="facts-v3",
        sku_facts={
            "material": "ABS",
            "dimensions": "10x8x3 cm",
            "country_of_origin": "China",
            "certifications": ["FCC"],
        },
        content={
            "title": "Wireless compact controller",
            "bullets": ["Made in China", "ABS enclosure"],
            "description": "Wireless controller for home office workflows.",
            "attributes": {"battery_required": False},
            "keywords": ["wireless", "controller"],
            "image_text": ["Compact controller"],
            "video_script": "Demonstrate setup without unsupported claims.",
            "declared_facts": {
                "material": "ABS",
                "dimensions": "10x8x3 cm",
                "country_of_origin": "China",
            },
            "translations": {
                "de-DE": {
                    "declared_facts": {
                        "material": "ABS",
                        "dimensions": "10x8x3 cm",
                        "country_of_origin": "China",
                    }
                }
            },
        },
        asset_version_ids=asset_ids,
    )


def test_listing_check_reports_rule_fact_ip_and_translation_findings(
    db: Session, workforce: dict[str, User], resources: dict[str, str]
) -> None:
    rule = _rule(db, workforce)
    request = _clean_listing_request(store_id=resources["store"], rule_id=rule.id, asset_ids=[])
    request.check_key = "CHECK-BLOCKED-1001"
    request.content["title"] = "Apple AirTag cure controller"
    request.content["declared_facts"]["material"] = "steel"
    request.content["translations"]["de-DE"]["declared_facts"]["dimensions"] = "20x20 cm"
    blocked = run_listing_compliance_check(db, request=request, user=workforce["listing"])
    assert blocked.gate_status == "block"
    assert {item.rule for item in blocked.findings} >= {
        "banned_term",
        "intellectual_property_review",
        "sku_fact_consistency",
    }
    assert blocked.rule_digest == rule.content_digest

    with pytest.raises(HTTPException) as cross_tenant:
        product_lifecycle_overview(db, tenant_id="tenant_demo", user=workforce["other"])
    assert cross_tenant.value.status_code == 403


def test_creative_asset_is_append_only_and_requires_human_review(
    db: Session, workforce: dict[str, User], resources: dict[str, str]
) -> None:
    brief, asset = _brief_and_asset(db, workforce, resources)
    assert asset.status == "pending_review"
    assert asset.required_human_approval is True
    with pytest.raises(HTTPException) as wrong_reviewer:
        review_creative_asset_version(
            db,
            asset_version_id=asset.id,
            request=CreativeAssetReview(
                tenant_id="tenant_demo", decision="approved", note="Looks correct"
            ),
            user=workforce["designer"],
        )
    assert wrong_reviewer.value.status_code == 403
    approved = review_creative_asset_version(
        db,
        asset_version_id=asset.id,
        request=CreativeAssetReview(
            tenant_id="tenant_demo",
            decision="approved",
            note="Dimensions, facts, brand and copyright evidence reviewed.",
        ),
        user=workforce["supervisor"],
    )
    assert approved.status == "approved"

    child = create_creative_asset_version(
        db,
        request=CreativeAssetVersionCreate(
            tenant_id="tenant_demo",
            asset_key=approved.asset_key,
            brief_id=brief.id,
            parent_version_id=approved.id,
            asset_type="main_image",
            file_reference="s3://tenant-demo/reviewed/sku-1001-main-v2.png",
            file_digest="sha256:asset-main-v2",
            provenance={"source": "human-retouch", "license": "tenant-owned"},
            checks={
                key: True
                for key in (
                    "dimensions",
                    "clarity",
                    "text_safe_area",
                    "logo",
                    "brand_colors",
                    "factual_consistency",
                    "copyright",
                )
            },
        ),
        user=workforce["designer"],
    )
    assert child.version == 2
    assert child.parent_version_id == approved.id
    assert child.file_digest != approved.file_digest


def test_creative_qc_blocks_unknown_brief_evidence_and_is_idempotent(
    db: Session, workforce: dict[str, User], resources: dict[str, str]
) -> None:
    brief = create_creative_brief(
        db,
        request=CreativeBriefCreate(
            tenant_id="tenant_demo",
            brief_key="BRIEF-QC-UNKNOWN-1001",
            store_resource_id=resources["store"],
            product_key="PRODUCT-QC-1001",
            language="en-US",
            dimensions={"width": 2000, "height": 2000, "unit": "px"},
            selling_points=["Verified selling point"],
            scenes=["White background"],
            required_assets=["main_image"],
        ),
        user=workforce["designer"],
    )
    asset = create_creative_asset_version(
        db,
        request=CreativeAssetVersionCreate(
            tenant_id="tenant_demo",
            asset_key="ASSET-QC-UNKNOWN-1001",
            brief_id=brief.id,
            asset_type="main_image",
            file_reference="s3://tenant-demo/reviewed/qc-unknown.png",
            file_digest="sha256:qc-unknown",
            provenance={"source": "human-retouch", "license": "tenant-owned"},
            checks={key: True for key in (
                "dimensions", "clarity", "text_safe_area", "logo", "brand_colors",
                "factual_consistency", "copyright",
            )},
        ),
        user=workforce["designer"],
    )
    report = run_creative_asset_qc(
        db,
        request=DesignQCRun(tenant_id="tenant_demo", asset_version_id=asset.id),
        user=workforce["designer"],
    )
    assert report.overall_status == "unknown"
    assert {item.check_key for item in report.findings if item.status == "unknown"} >= {
        "facts_evidence", "brand_evidence", "platform_spec_evidence",
    }
    same_report = run_creative_asset_qc(
        db,
        request=DesignQCRun(tenant_id="tenant_demo", asset_version_id=asset.id),
        user=workforce["designer"],
    )
    assert same_report.id == report.id
    with pytest.raises(HTTPException) as blocked:
        review_creative_asset_version(
            db,
            asset_version_id=asset.id,
            request=CreativeAssetReview(
                tenant_id="tenant_demo", decision="approved", note="Attempted approval"
            ),
            user=workforce["supervisor"],
        )
    assert blocked.value.status_code == 409
    assert "unknown" in str(blocked.value.detail)


def test_creative_delivery_checklist_requires_qc_and_current_evidence(
    db: Session, workforce: dict[str, User], resources: dict[str, str]
) -> None:
    brief, asset = _brief_and_asset(db, workforce, resources)
    approved = review_creative_asset_version(
        db,
        asset_version_id=asset.id,
        request=CreativeAssetReview(
            tenant_id="tenant_demo", decision="approved", note="QC and evidence reviewed"
        ),
        user=workforce["supervisor"],
    )
    ready = create_creative_delivery_checklist(
        db,
        request=CreativeDeliveryChecklistCreate(
            tenant_id="tenant_demo", brief_id=brief.id, asset_version_ids=[approved.id]
        ),
        user=workforce["supervisor"],
    )
    assert ready.status == "ready", ready.blockers
    assert ready.blockers == []

    sync_creative_evidence(
        db,
        request=CreativeEvidenceSyncRequest(
            tenant_id="tenant_demo",
            records=[
                CreativeEvidenceSyncItem(
                    evidence_type="facts",
                    source_ref="sku-facts/PRODUCT-1001",
                    version="facts-v3",
                    payload=brief.fact_snapshot,
                    effective_at=utc_now() - timedelta(days=2),
                    expires_at=utc_now() - timedelta(seconds=1),
                )
            ],
        ),
        user=workforce["supervisor"],
    )
    assert expire_creative_evidence_records(db) == 0
    blocked = create_creative_delivery_checklist(
        db,
        request=CreativeDeliveryChecklistCreate(
            tenant_id="tenant_demo", brief_id=brief.id, asset_version_ids=[approved.id]
        ),
        user=workforce["supervisor"],
    )
    assert blocked.status == "blocked"
    assert any(item["code"] == "evidence_not_verified" for item in blocked.blockers)


def test_creative_generation_provider_submission_is_idempotent(
    db: Session, workforce: dict[str, User], resources: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    brief, _ = _brief_and_asset(db, workforce, resources)
    monkeypatch.setattr(
        "app.product_lifecycle.service.submit_generation_request",
        lambda **_kwargs: {"external_request_id": "provider-request-1", "status": "submitted"},
    )
    request = CreativeGenerationSubmit(
        tenant_id="tenant_demo",
        brief_id=brief.id,
        provider_key="http",
        idempotency_key="generation-idempotency-1",
        instructions={"style": "clean product photography"},
    )
    first = submit_creative_generation(db, request=request, user=workforce["designer"])
    second = submit_creative_generation(db, request=request, user=workforce["designer"])
    assert first.status == "submitted"
    assert first.external_request_id == "provider-request-1"
    assert second.id == first.id


def test_procurement_is_explainable_and_never_creates_order(
    db: Session, workforce: dict[str, User], resources: dict[str, str]
) -> None:
    recommendation = _procurement(db, workforce, resources)
    assert recommendation.recommended_quantity == 300
    assert recommendation.estimated_landed_cost == 2850
    assert "ceil_to_MOQ" in recommendation.formula
    assert db.exec(select(HighRiskActionRequest)).all() == []
    assert db.exec(select(BusinessActionExecution)).all() == []
    reviewed = review_procurement_recommendation(
        db,
        recommendation_id=recommendation.id,
        request=ProcurementRecommendationReview(
            tenant_id="tenant_demo",
            decision="reviewed",
            note="Forecast, quote, MOQ and cash constraint reviewed.",
        ),
        user=workforce["supervisor"],
    )
    assert reviewed.status == "reviewed"
    assert db.exec(select(HighRiskActionRequest)).all() == []


def test_launch_gate_binds_approved_versions_and_only_requests_publish_approval(
    db: Session, workforce: dict[str, User], resources: dict[str, str]
) -> None:
    rule = _rule(db, workforce)
    _, asset = _brief_and_asset(db, workforce, resources)
    approved_asset = review_creative_asset_version(
        db,
        asset_version_id=asset.id,
        request=CreativeAssetReview(
            tenant_id="tenant_demo",
            decision="approved",
            note="Main image and provenance reviewed.",
        ),
        user=workforce["supervisor"],
    )
    recommendation = _procurement(db, workforce, resources)
    reviewed_procurement = review_procurement_recommendation(
        db,
        recommendation_id=recommendation.id,
        request=ProcurementRecommendationReview(
            tenant_id="tenant_demo",
            decision="reviewed",
            note="Supply plan reviewed; this is not a purchase order.",
        ),
        user=workforce["supervisor"],
    )
    check = run_listing_compliance_check(
        db,
        request=_clean_listing_request(
            store_id=resources["store"],
            rule_id=rule.id,
            asset_ids=[approved_asset.id],
            check_key="CHECK-LAUNCH-1001",
        ),
        user=workforce["listing"],
    )
    assert check.gate_status == "pass"
    gate = evaluate_product_launch_gate(
        db,
        request=ProductLaunchGateCreate(
            tenant_id="tenant_demo",
            launch_key="LAUNCH-PRODUCT-1001",
            store_resource_id=resources["store"],
            supplier_resource_id=resources["supplier"],
            product_key="PRODUCT-1001",
            sku="SKU-1001",
            sku_fact_version="facts-v3",
            bom_version="bom-v5",
            packaging_version="pack-v2",
            certification_ids=["FCC"],
            listing_check_id=check.id,
            asset_version_ids=[approved_asset.id],
            procurement_recommendation_id=reviewed_procurement.id,
            supplier_lead_time_confirmed=True,
        ),
        user=workforce["supervisor"],
    )
    assert gate.status == "ready"
    assert gate.blockers == []
    submitted = submit_product_launch(
        db,
        launch_gate_id=gate.id,
        request=ProductLaunchSubmit(
            tenant_id="tenant_demo",
            expected_version=gate.version,
            listing_id="ASIN-DRAFT-1001",
            marketplace="US",
            product_type="Electronics",
            attributes={"sku": "SKU-1001", "material": "ABS"},
            summary="Publish reviewed SKU-1001 listing through the controlled connector",
        ),
        user=workforce["supervisor"],
    )
    assert submitted.status == "waiting_approval"
    action = db.get(HighRiskActionRequest, submitted.approval_request_id)
    assert action is not None
    assert action.status == "pending"
    assert action.action_type == "publish_listing"
    assert action.payload_json["launch_evidence_digest"] == gate.evidence_digest
    assert db.exec(select(BusinessActionExecution)).all() == []


def test_launch_gate_blocks_missing_certification_and_unconfirmed_lead_time(
    db: Session, workforce: dict[str, User], resources: dict[str, str]
) -> None:
    rule = _rule(db, workforce)
    _, asset = _brief_and_asset(db, workforce, resources)
    approved_asset = review_creative_asset_version(
        db,
        asset_version_id=asset.id,
        request=CreativeAssetReview(
            tenant_id="tenant_demo", decision="approved", note="Reviewed for test"
        ),
        user=workforce["supervisor"],
    )
    recommendation = _procurement(db, workforce, resources)
    recommendation = review_procurement_recommendation(
        db,
        recommendation_id=recommendation.id,
        request=ProcurementRecommendationReview(
            tenant_id="tenant_demo", decision="reviewed", note="Reviewed for test"
        ),
        user=workforce["supervisor"],
    )
    check = run_listing_compliance_check(
        db,
        request=_clean_listing_request(
            store_id=resources["store"],
            rule_id=rule.id,
            asset_ids=[approved_asset.id],
            check_key="CHECK-BLOCK-GATE",
        ),
        user=workforce["listing"],
    )
    gate = evaluate_product_launch_gate(
        db,
        request=ProductLaunchGateCreate(
            tenant_id="tenant_demo",
            launch_key="LAUNCH-BLOCKED-1001",
            store_resource_id=resources["store"],
            supplier_resource_id=resources["supplier"],
            product_key="PRODUCT-1001",
            sku="SKU-1001",
            sku_fact_version="facts-v3",
            bom_version="bom-v5",
            packaging_version="pack-v2",
            certification_ids=[],
            listing_check_id=check.id,
            asset_version_ids=[approved_asset.id],
            procurement_recommendation_id=recommendation.id,
            supplier_lead_time_confirmed=False,
        ),
        user=workforce["supervisor"],
    )
    assert gate.status == "blocked"
    assert {item["code"] for item in gate.blockers} == {
        "certification_missing",
        "supplier_lead_time_unavailable",
    }
    with pytest.raises(HTTPException) as submit_blocked:
        submit_product_launch(
            db,
            launch_gate_id=gate.id,
            request=ProductLaunchSubmit(
                tenant_id="tenant_demo",
                expected_version=gate.version,
                listing_id="DRAFT",
                marketplace="US",
                product_type="Electronics",
                attributes={"sku": "SKU-1001"},
                summary="This blocked launch must not create an approval request",
            ),
            user=workforce["supervisor"],
        )
    assert submit_blocked.value.status_code == 409
