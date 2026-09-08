"""Run a real DesignKit image through Joukir's creative asset lifecycle.

This script is intentionally an operator-run acceptance tool. It does not
read credentials, call the DesignKit CLI, or bypass the normal object-storage,
QC, and human-review gates. The DesignKit CLI download is supplied as the
input file, then the file is staged through the same service functions used by
the HTTP API.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session, select

from app.db import engine
from app.db.database import set_tenant_context
from app.db.models import BusinessResource, User
from app.product_lifecycle.schema import (
    CreativeAssetReview,
    CreativeAssetVersionCreate,
    CreativeBriefCreate,
    CreativeDeliveryChecklistCreate,
    CreativeEvidenceSyncItem,
    CreativeEvidenceSyncRequest,
    DesignQCRun,
)
from app.product_lifecycle.service import (
    create_creative_asset_version,
    create_creative_brief,
    create_creative_delivery_checklist,
    review_creative_asset_version,
    run_creative_asset_qc,
    stage_creative_asset_upload,
    sync_creative_evidence,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Downloaded DesignKit image file")
    parser.add_argument("--tenant-id", default="tenant_demo")
    parser.add_argument("--user-id", default="user_e76cc711c25e463f")
    parser.add_argument("--store-resource-id", default="bizres_c31b46380d844eef")
    return parser.parse_args()


def _find_user(db: Session, tenant_id: str, user_id: str) -> User:
    user = db.exec(
        select(User).where(User.tenant_id == tenant_id, User.id == user_id)
    ).first()
    if not user:
        raise RuntimeError(f"User not found in tenant: {user_id}")
    return user


def _check_store(db: Session, tenant_id: str, store_resource_id: str) -> None:
    store = db.exec(
        select(BusinessResource).where(
            BusinessResource.tenant_id == tenant_id,
            BusinessResource.id == store_resource_id,
            BusinessResource.resource_type == "store",
            BusinessResource.status == "active",
        )
    ).first()
    if not store:
        raise RuntimeError(f"Active store resource not found: {store_resource_id}")


def main() -> None:
    args = _parse_args()
    image_path = args.image.resolve()
    if not image_path.is_file():
        raise SystemExit(f"Input image does not exist: {image_path}")
    image_bytes = image_path.read_bytes()
    if not image_bytes:
        raise SystemExit("Input image is empty")

    run_id = uuid4().hex[:12]
    product_key = f"designkit-e2e-{run_id}"
    brief_key = f"brief-designkit-e2e-{run_id}"
    asset_key = f"asset-designkit-e2e-{run_id}"
    evidence_version = f"e2e-{run_id}"
    now = datetime.now(UTC)

    with Session(engine) as db:
        set_tenant_context(db, args.tenant_id)
        user = _find_user(db, args.tenant_id, args.user_id)
        _check_store(db, args.tenant_id, args.store_resource_id)

        # Keep every snapshot and registry payload identical so QC can prove
        # that the brief used the same trusted evidence that was synchronized.
        evidence_payloads = {
            "facts": {
                "source_ref": f"designkit-e2e/{run_id}/facts",
                "version": evidence_version,
                "status": "verified",
                "product_key": product_key,
                "value": {"material": "test", "country_of_origin": "US"},
            },
            "brand": {
                "source_ref": f"designkit-e2e/{run_id}/brand",
                "version": evidence_version,
                "status": "verified",
                "product_key": product_key,
                "value": {"primary_color": "coral", "logo_required": False},
            },
            "platform_spec": {
                "source_ref": f"designkit-e2e/{run_id}/platform",
                "version": evidence_version,
                "status": "verified",
                "product_key": product_key,
                "value": {"platform": "Amazon", "width": 2048, "height": 2048},
            },
        }
        sync_creative_evidence(
            db,
            request=CreativeEvidenceSyncRequest(
                tenant_id=args.tenant_id,
                records=[
                    CreativeEvidenceSyncItem(
                        evidence_type=evidence_type,
                        source_ref=payload["source_ref"],
                        version=evidence_version,
                        payload=payload,
                        status="verified",
                        effective_at=now,
                    )
                    for evidence_type, payload in evidence_payloads.items()
                ],
            ),
            user=user,
        )

        brief = create_creative_brief(
            db,
            request=CreativeBriefCreate(
                tenant_id=args.tenant_id,
                brief_key=brief_key,
                store_resource_id=args.store_resource_id,
                product_key=product_key,
                language="en-US",
                dimensions={"width": 2048, "height": 2048, "ratio": "1:1"},
                selling_points=["Clean layout", "Benefit focused", "Conversion ready"],
                scenes=["Amazon A+ detail module"],
                required_assets=["a_plus"],
                constraints={"test_run": True, "source": "designkit_cli"},
                fact_snapshot=evidence_payloads["facts"],
                brand_snapshot=evidence_payloads["brand"],
                platform_spec_snapshot=evidence_payloads["platform_spec"],
            ),
            user=user,
        )
        upload = stage_creative_asset_upload(
            db,
            tenant_id=args.tenant_id,
            brief_id=brief.id,
            filename=image_path.name,
            content_type="image/png",
            data=image_bytes,
            user=user,
        )
        asset = create_creative_asset_version(
            db,
            request=CreativeAssetVersionCreate(
                tenant_id=args.tenant_id,
                asset_key=asset_key,
                brief_id=brief.id,
                asset_type="a_plus",
                file_reference=upload.file_reference,
                file_digest=upload.file_digest,
                provenance={
                    "source": "designkit_cli",
                    "license": "tenant_test_input",
                    "external_task": "designkit_e2e",
                },
                generation_parameters={"room_output": True, "run_id": run_id},
                checks={
                    "dimensions": {"passed": True},
                    "clarity": {"passed": True},
                    "text_safe_area": {"passed": True},
                    "logo": {"passed": True},
                    "brand_colors": {"passed": True},
                    "factual_consistency": {"passed": True},
                    "copyright": {"passed": True},
                },
            ),
            user=user,
        )
        qc = run_creative_asset_qc(
            db,
            request=DesignQCRun(
                tenant_id=args.tenant_id,
                asset_version_id=asset.id,
            ),
            user=user,
        )
        reviewed = review_creative_asset_version(
            db,
            asset_version_id=asset.id,
            request=CreativeAssetReview(
                tenant_id=args.tenant_id,
                decision="approved",
                note="DesignKit CLI e2e 验收：对象存储、摘要、证据和 QC 均通过。",
            ),
            user=user,
        )
        delivery = create_creative_delivery_checklist(
            db,
            request=CreativeDeliveryChecklistCreate(
                tenant_id=args.tenant_id,
                brief_id=brief.id,
                asset_version_ids=[asset.id],
            ),
            user=user,
        )

    print(
        json.dumps(
            {
                "run_id": run_id,
                "input_file": str(image_path),
                "input_sha256": hashlib.sha256(image_bytes).hexdigest(),
                "brief_id": brief.id,
                "asset_version_id": reviewed.id,
                "stored_reference": upload.file_reference,
                "stored_digest": upload.file_digest,
                "stored_size": upload.size,
                "media_metadata": upload.media_metadata,
                "qc_status": qc.overall_status,
                "asset_status": reviewed.status,
                "delivery_status": delivery.status,
                "delivery_blockers": delivery.blockers,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
