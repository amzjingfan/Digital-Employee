from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.business_resources.schema import BusinessResourceCreate
from app.business_resources.service import create_resource
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
    create_listing_rule_set,
    create_procurement_recommendation,
    evaluate_product_launch_gate,
    product_lifecycle_overview,
    publish_listing_rule_set,
    review_creative_asset_version,
    review_procurement_recommendation,
    run_listing_compliance_check,
    submit_product_launch,
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
            required_assets=["main_image", "secondary_image"],
            constraints={"background": "white", "safe_area_percent": 5},
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
    return brief, asset


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
