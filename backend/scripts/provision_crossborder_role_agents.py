from __future__ import annotations

import argparse
import hashlib

from sqlmodel import Session, select

from app.db.database import engine, set_tenant_context
from app.db.models import AgentProfile
from app.security.business_roles import BUSINESS_ROLE_BY_KEY

ROLE_DESCRIPTIONS = {
    "operations_supervisor": "汇总六个生产岗位结果，生成日报、周报并组织人工复核。",
    "after_sales_specialist": "只处理跨境客服、退款、退换货和售后工单。",
    "listing_compliance_specialist": "只检查 Listing 内容、证据和平台规则。",
    "logistics_exception_specialist": "只监控履约、物流轨迹和承运商异常。",
    "advertising_inspection_specialist": "只分析广告数据并提出受控操作建议。",
    "designer": "处理商品视觉素材、设计需求和素材版本协作。",
    "procurement_specialist": "处理供应商、采购资料、补货与采购协作任务。",
}


def provision(tenant_id: str) -> list[AgentProfile]:
    created: list[AgentProfile] = []
    with Session(engine) as db:
        set_tenant_context(db, tenant_id)
        agents = db.exec(select(AgentProfile).where(AgentProfile.tenant_id == tenant_id)).all()
        assigned_roles = {
            str((agent.metadata_json or {}).get("business_role", "")) for agent in agents
        }
        for role, description in ROLE_DESCRIPTIONS.items():
            if role in assigned_roles:
                continue
            definition = BUSINESS_ROLE_BY_KEY[role]
            digest = hashlib.sha256(f"{tenant_id}:{role}".encode()).hexdigest()[:16]
            row = AgentProfile(
                id=f"agent_role_{digest}",
                tenant_id=tenant_id,
                name=definition.label,
                description=description,
                persona_prompt=(
                    f"你是{definition.label}。严格限定在岗位职责内工作；所有结论引用来源，"
                    "高风险外部写操作必须进入审批，不得自行越权执行。"
                ),
                status="active",
                metadata_json={
                    "business_role": role,
                    "role_name": definition.label,
                    "role_queue_enabled": True,
                    "managed_by_platform": True,
                    "owner_user_id": "admin",
                    "owner_username": "admin",
                    "created_by": "system",
                },
            )
            db.add(row)
            created.append(row)
        db.commit()
    return created


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", default="tenant_demo")
    args = parser.parse_args()
    created = provision(args.tenant_id)
    print(f"provisioned={len(created)} tenant={args.tenant_id}")


if __name__ == "__main__":
    main()
