"""Import the bundled native gallery into an existing tenant once, without demo accounts."""

from __future__ import annotations

import argparse
from collections import Counter

from sqlmodel import Session, select

from app.agents.branching import ensure_open_gallery_binding, open_gallery_metadata
from app.config import get_settings
from app.db import staffdeck_seed
from app.db.database import engine, set_tenant_context
from app.db.models import (
    AgentProfile,
    AgentResourceBinding,
    GeneralSkill,
    KnowledgeBase,
    Skill,
    Tenant,
    Tool,
    User,
)
from app.db.seed import (
    DEMO_TOOLS,
    EXCHANGE_SKILL,
    GRAPH_VISUAL_DEMO_SKILL,
    PRICE_COMPARE_SKILL,
    PURCHASE_SKILL,
    REFUND_SKILL,
    _skill_content_graph,
    _tool_config_with_base_url,
)

CORE_SKILLS = (
    REFUND_SKILL,
    EXCHANGE_SKILL,
    PURCHASE_SKILL,
    PRICE_COMPARE_SKILL,
    GRAPH_VISUAL_DEMO_SKILL,
)


def import_gallery(session: Session, tenant_id: str, admin_username: str) -> dict[str, int]:
    set_tenant_context(session, tenant_id)
    if tenant_id == "tenant_demo" or not session.get(Tenant, tenant_id):
        raise ValueError("Specify an existing non-demo tenant")
    admin = session.exec(
        select(User).where(User.tenant_id == tenant_id, User.username == admin_username)
    ).one_or_none()
    if admin is None or admin.role != "admin":
        raise ValueError("Specify an existing tenant administrator")

    overall = session.exec(
        select(AgentProfile).where(
            AgentProfile.tenant_id == tenant_id,
            AgentProfile.is_overall == True,
            AgentProfile.status != "archived",
        )
    ).first()
    if overall is None:
        overall = AgentProfile(
            id=f"agent_{tenant_id}_overall",
            tenant_id=tenant_id,
            name="整体智能体",
            description="全局资源池",
            is_overall=True,
            status="active",
        )
        session.add(overall)
        session.flush()

    # The existing seed is tenant_demo-only; override its target for this call.
    original = (
        staffdeck_seed.TENANT_ID,
        staffdeck_seed.ADMIN_USER_ID,
        staffdeck_seed.ADMIN_USERNAME,
        staffdeck_seed.ADMIN_DISPLAY_NAME,
    )
    try:
        staffdeck_seed.TENANT_ID = tenant_id
        staffdeck_seed.ADMIN_USER_ID = admin.id
        staffdeck_seed.ADMIN_USERNAME = admin.username
        staffdeck_seed.ADMIN_DISPLAY_NAME = admin.display_name or admin.username
        staffdeck_seed.seed_staffdeck_admin_gallery(session)
    finally:
        (
            staffdeck_seed.TENANT_ID,
            staffdeck_seed.ADMIN_USER_ID,
            staffdeck_seed.ADMIN_USERNAME,
            staffdeck_seed.ADMIN_DISPLAY_NAME,
        ) = original

    creator = open_gallery_metadata(
        {
            "owner_user_id": admin.id,
            "owner_username": admin.username,
            "created_by_user_id": admin.id,
            "created_by_username": admin.username,
            "created_by": admin.username,
            "seed_source": staffdeck_seed.SEED_SOURCE,
            "managed_by_seed": True,
        }
    )
    for raw in CORE_SKILLS:
        content = _skill_content_graph(raw)
        skill_id = content["skill_id"]
        row = session.exec(
            select(Skill).where(Skill.tenant_id == tenant_id, Skill.skill_id == skill_id)
        ).first()
        if row is None:
            row = Skill(
                tenant_id=tenant_id,
                skill_id=skill_id,
                version=content["version"],
                name=content["name"],
                business_domain=content.get("business_domain"),
                description=content.get("description"),
                content_json=content,
                status="published",
            )
            session.add(row)
            session.flush()
        ensure_open_gallery_binding(session, tenant_id, "skill", row.id, metadata_json=creator)

    settings = get_settings()
    for raw in DEMO_TOOLS:
        config = _tool_config_with_base_url(raw, settings.normalized_tool_base_url)
        row = session.exec(
            select(Tool).where(Tool.tenant_id == tenant_id, Tool.name == config["name"])
        ).first()
        if row is None:
            row = Tool(tenant_id=tenant_id, **config)
            session.add(row)
            session.flush()
        ensure_open_gallery_binding(session, tenant_id, "tool", row.id, metadata_json=creator)

    fixture = staffdeck_seed._load_seed_fixtures(
        (staffdeck_seed.FIXTURE_PATH, staffdeck_seed.EXPANDED_FIXTURE_PATH)
    )
    expected = {
        "agents": 10,
        "knowledge_bases": 19,
        "general_skills": 9,
        "skills": 25,
        "tools": 17,
    }
    resource_ids = {
        "knowledge_base": {
            row["id"] for row in fixture["knowledge_bases"]
            if (item := session.get(KnowledgeBase, row["id"])) and item.tenant_id == tenant_id
        },
        "general_skill": {
            row["id"] for row in fixture["general_skills"]
            if (item := session.get(GeneralSkill, row["id"])) and item.tenant_id == tenant_id
        },
        "skill": {
            row.id for row in session.exec(select(Skill).where(Skill.tenant_id == tenant_id)).all()
            if row.skill_id in {item["skill_id"] for item in fixture["skills"] + list(CORE_SKILLS)}
        },
        "tool": {
            row.id for row in session.exec(select(Tool).where(Tool.tenant_id == tenant_id)).all()
            if row.name in {item["name"] for item in fixture["tools"] + list(DEMO_TOOLS)}
        },
    }
    bindings = session.exec(
        select(AgentResourceBinding).where(
            AgentResourceBinding.tenant_id == tenant_id,
            AgentResourceBinding.agent_id == overall.id,
            AgentResourceBinding.status == "active",
        )
    ).all()
    published = Counter(
        row.resource_type for row in bindings
        if row.resource_id in resource_ids.get(row.resource_type, set())
    )
    actual = {
        "agents": len(
            [
                row
                for row in session.exec(
                    select(AgentProfile).where(
                        AgentProfile.tenant_id == tenant_id,
                        AgentProfile.name.in_(staffdeck_seed.SELECTED_AGENT_NAMES),
                        AgentProfile.status != "archived",
                    )
                ).all()
                if row.metadata_json.get("seed_source") == staffdeck_seed.SEED_SOURCE
                and row.metadata_json.get("published_to_gallery") is True
            ]
        ),
        "knowledge_bases": published["knowledge_base"],
        "general_skills": published["general_skill"],
        "skills": published["skill"],
        "tools": published["tool"],
    }
    if actual != expected:
        raise RuntimeError(f"Native gallery verification failed: {actual}")
    return actual


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--admin", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with Session(engine) as session:
        counts = import_gallery(session, args.tenant, args.admin)
        if args.apply:
            session.commit()
        else:
            session.rollback()
    print(("imported" if args.apply else "dry-run"), counts)


if __name__ == "__main__":
    main()
