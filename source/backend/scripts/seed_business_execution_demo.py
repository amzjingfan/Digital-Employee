from __future__ import annotations

import os

from sqlmodel import Session, select

from app.business_execution.service import request_compensation
from app.business_execution.worker import run_execution_cycle
from app.business_resources.schema import HighRiskActionCreate
from app.business_resources.service import create_action_request, decide_action_request
from app.config import get_settings
from app.db import engine
from app.db.models import (
    BusinessActionExecution,
    BusinessResource,
    HighRiskActionRequest,
    User,
)

TENANT_ID = "tenant_demo"
DEMO_SUMMARY = "StaffDeck 外部执行 Saga 沙箱验证"


def main() -> None:
    settings = get_settings()
    with Session(engine) as db:
        db.info["staffdeck_tenant_id"] = TENANT_ID
        supervisor = db.exec(
            select(User).where(
                User.tenant_id == TENANT_ID,
                User.business_role == "operations_supervisor",
            )
        ).first()
        if not supervisor:
            raise RuntimeError("No operations supervisor exists in tenant_demo")
        requester = db.exec(
            select(User).where(
                User.tenant_id == TENANT_ID,
                User.username == "staffdeck-sandbox-listing",
            )
        ).first()
        if not requester:
            requester = User(
                tenant_id=TENANT_ID,
                username="staffdeck-sandbox-listing",
                display_name="StaffDeck 沙箱 Listing 专员",
                role="member",
                business_role="listing_compliance_specialist",
                authorization_source="system_demo",
                password_hash="disabled",
            )
            db.add(requester)
            db.commit()
            db.refresh(requester)
        resource = db.exec(
            select(BusinessResource).where(
                BusinessResource.tenant_id == TENANT_ID,
                BusinessResource.resource_type == "store",
                BusinessResource.status == "active",
            )
        ).first()
        if not resource:
            raise RuntimeError("No active store resource exists in tenant_demo")
        action = db.exec(
            select(HighRiskActionRequest).where(
                HighRiskActionRequest.tenant_id == TENANT_ID,
                HighRiskActionRequest.summary == DEMO_SUMMARY,
            )
        ).first()
        if not action:
            created = create_action_request(
                db,
                request=HighRiskActionCreate(
                    tenant_id=TENANT_ID,
                    resource_id=resource.id,
                    action_type="publish_listing",
                    summary=DEMO_SUMMARY,
                    payload={
                        "listing_id": "STAFFDECK-SANDBOX-001",
                        "marketplace": "Amazon US",
                        "product_type": "PRODUCT",
                        "attributes": {
                            "item_name": [{"value": "StaffDeck Sandbox Listing"}]
                        },
                    },
                ),
                user=requester,
            )
            action = db.exec(
                select(HighRiskActionRequest).where(HighRiskActionRequest.id == created.id)
            ).one()
        if action.status == "pending":
            decide_action_request(
                db,
                tenant_id=TENANT_ID,
                request_id=action.id,
                decision="approved",
                reason="系统集成验证：仅在 StaffDeck sandbox 执行，不访问 Amazon",
                user=supervisor,
            )

    run_execution_cycle(db_engine=engine, settings=settings)
    if os.getenv("STAFFDECK_DEMO_COMPENSATE") == "1":
        with Session(engine) as db:
            db.info["staffdeck_tenant_id"] = TENANT_ID
            action = db.exec(
                select(HighRiskActionRequest).where(
                    HighRiskActionRequest.tenant_id == TENANT_ID,
                    HighRiskActionRequest.summary == DEMO_SUMMARY,
                )
            ).one()
            execution = db.exec(
                select(BusinessActionExecution).where(
                    BusinessActionExecution.tenant_id == TENANT_ID,
                    BusinessActionExecution.request_id == action.id,
                )
            ).one()
            if execution.status == "succeeded":
                request_compensation(
                    db,
                    tenant_id=TENANT_ID,
                    execution_id=execution.id,
                    reason="系统集成验证：验证批准后语义补偿和回执链路",
                    user=supervisor,
                )
        run_execution_cycle(db_engine=engine, settings=settings)
    with Session(engine) as db:
        db.info["staffdeck_tenant_id"] = TENANT_ID
        action = db.exec(
            select(HighRiskActionRequest).where(
                HighRiskActionRequest.tenant_id == TENANT_ID,
                HighRiskActionRequest.summary == DEMO_SUMMARY,
            )
        ).one()
        execution = db.exec(
            select(BusinessActionExecution).where(
                BusinessActionExecution.tenant_id == TENANT_ID,
                BusinessActionExecution.request_id == action.id,
            )
        ).one()
        print(
            f"approval={action.id} approval_status={action.status} "
            f"execution={execution.id} execution_status={execution.status} "
            f"environment={execution.environment} attempts={execution.attempt_count}"
        )


if __name__ == "__main__":
    main()
