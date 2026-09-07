from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.crossborder.capability_pack import ROLE_PACKS, provision_crossborder_capabilities
from app.db.models import (
    AgentKnowledgeBranch,
    AgentProfile,
    AgentResourceBinding,
    AgentServiceIdentity,
    AgentSkillBranch,
    KnowledgeBase,
    KnowledgeBaseVersion,
    KnowledgeChunk,
    Skill,
    SkillVersion,
    Tenant,
    Tool,
)
from app.skills.skill_schema import SkillCard


def test_provision_crossborder_capabilities_is_reviewed_bound_and_idempotent() -> None:
    with _test_session() as db:
        db.add(Tenant(id="tenant_demo", name="Demo"))
        for index, spec in enumerate(ROLE_PACKS):
            db.add(
                AgentProfile(
                    id=f"agent-{index}",
                    tenant_id="tenant_demo",
                    name=f"role-{index}",
                    status="active",
                    metadata_json={"business_role": spec.role},
                )
            )
        db.commit()

        first = provision_crossborder_capabilities(
            db, tenant_id="tenant_demo", tool_base_url="http://127.0.0.1:5173"
        )
        second = provision_crossborder_capabilities(
            db, tenant_id="tenant_demo", tool_base_url="http://127.0.0.1:5173"
        )

        assert first == second
        assert len(first) == 7
        assert all(item["review_status"] == "approved" for item in first)
        assert all(item["approval_scope"] == "sandbox_read_only" for item in first)
        assert len(db.exec(select(Skill).where(Skill.tenant_id == "tenant_demo")).all()) == 7
        assert len(db.exec(select(SkillVersion)).all()) == 7
        assert len(db.exec(select(KnowledgeBase)).all()) == 7
        assert len(db.exec(select(KnowledgeBaseVersion)).all()) == 7
        assert len(db.exec(select(KnowledgeChunk)).all()) == 42
        assert len(db.exec(select(Tool)).all()) == 7
        assert len(db.exec(select(AgentResourceBinding)).all()) == 21
        assert len(db.exec(select(AgentServiceIdentity)).all()) == 7
        assert len(db.exec(select(AgentSkillBranch)).all()) == 7
        assert len(db.exec(select(AgentKnowledgeBranch)).all()) == 7

        for agent in db.exec(select(AgentProfile)).all():
            role = str((agent.metadata_json or {}).get("business_role") or "")
            assert agent.metadata_json["published_to_gallery"] is True
            assert agent.metadata_json["gallery_template_kind"] == "reviewed_production_role"
            assert agent.metadata_json["gallery_category"] == "跨境电商"
            assert role in agent.metadata_json["gallery_allowed_business_roles"]
            assert "operations_supervisor" in agent.metadata_json[
                "gallery_allowed_business_roles"
            ]
            assert "platform_admin" in agent.metadata_json[
                "gallery_allowed_business_roles"
            ]

        for skill in db.exec(select(Skill)).all():
            card = SkillCard.model_validate(skill.content_json)
            assert card.skill_id == skill.skill_id
            refs = [node.capability_refs for node in card.nodes]
            assert sum(bool(item.required_tool_ids) for item in refs) == 1
            assert sum(bool(item.required_knowledge_base_ids) for item in refs) == 1
            assert "不得跨店铺" in "".join(card.response_rules)

        for tool in db.exec(select(Tool)).all():
            assert tool.method == "GET"
            assert tool.capability_scope == "sop_specific"
            assert tool.auth_json == {}
            assert tool.headers_json == {}
            assert tool.config_json["production"]["risk_class"] == "read_only"
            assert tool.config_json["production"]["side_effect"] == "none"

        for identity in db.exec(select(AgentServiceIdentity)).all():
            assert identity.provider == "casdoor"
            assert identity.status == "active"
            assert identity.credential_ref.startswith("secret://")
            assert identity.metadata_json["external_writes"] is False


@contextmanager
def _test_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
