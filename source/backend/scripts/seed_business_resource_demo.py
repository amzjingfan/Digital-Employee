from __future__ import annotations

from sqlmodel import Session, select

from app.business_resources.schema import BusinessResourceCreate
from app.business_resources.service import create_resource
from app.db import engine, set_tenant_context
from app.db.models import BusinessResource, User

DEMO_RESOURCES = (
    ("store", "AMZ-US-FLAGSHIP", "Amazon 美国旗舰店", {"marketplace": "Amazon US", "region": "US"}),
    ("carrier", "UPS-FBA-US", "UPS 美国 FBA 承运商", {"service_level": "Ground", "region": "US"}),
    ("ad_account", "AMZ-ADS-US", "Amazon Ads 美国站", {"marketplace": "Amazon US", "currency": "USD"}),
    ("supplier", "SUP-SZ-001", "深圳核心供应商", {"region": "CN", "category": "核心供应链"}),
)


def main() -> None:
    with Session(engine) as db:
        set_tenant_context(db, "tenant_demo")
        actor = db.exec(
            select(User).where(
                User.tenant_id == "tenant_demo",
                User.business_role == "operations_supervisor",
            )
        ).first()
        if actor is None:
            actor = db.exec(
                select(User).where(User.tenant_id == "tenant_demo", User.role == "admin")
            ).first()
        if actor is None:
            raise RuntimeError("tenant_demo needs an operations supervisor or administrator")

        created = 0
        for resource_type, code, name, metadata in DEMO_RESOURCES:
            existing = db.exec(
                select(BusinessResource).where(
                    BusinessResource.tenant_id == "tenant_demo",
                    BusinessResource.resource_type == resource_type,
                    BusinessResource.code == code,
                )
            ).first()
            if existing:
                continue
            create_resource(
                db,
                request=BusinessResourceCreate(
                    tenant_id="tenant_demo",
                    resource_type=resource_type,
                    code=code,
                    name=name,
                    metadata=metadata,
                ),
                user=actor,
            )
            created += 1
        print(f"Business resource demo seed complete: created={created}, total={len(DEMO_RESOURCES)}")


if __name__ == "__main__":
    main()
