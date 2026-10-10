from __future__ import annotations

import runpy
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import AgentProfile, KnowledgeDocument, Tenant, User


def test_native_gallery_import_preserves_existing_tenant_and_is_idempotent() -> None:
    script = Path(__file__).resolve().parents[2] / "deploy" / "import_native_gallery.py"
    import_gallery = runpy.run_path(str(script))["import_gallery"]
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(Tenant(id="tenant_internal", name="Internal"))
        session.add(
            User(
                id="user_admin_internal",
                tenant_id="tenant_internal",
                username="joukir-admin",
                role="admin",
                password_hash="unused",
            )
        )
        session.add(AgentProfile(id="agent_existing", tenant_id="tenant_internal", name="测试"))
        session.commit()

        expected = {
            "agents": 10,
            "knowledge_bases": 19,
            "general_skills": 9,
            "skills": 25,
            "tools": 17,
        }
        for _ in range(2):
            assert import_gallery(session, "tenant_internal", "joukir-admin") == expected
            session.commit()

        assert session.get(Tenant, "tenant_demo") is None
        assert session.get(AgentProfile, "agent_existing") is not None
        assert len(session.exec(select(User)).all()) == 1
        assert len(session.exec(select(KnowledgeDocument)).all()) == 19
