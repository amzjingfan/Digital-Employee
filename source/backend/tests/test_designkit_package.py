from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.creative.designkit_package import (
    API_TOOL_NAME,
    SKILL_ID,
    DesignKitPackageError,
    load_designkit_package,
    provision_designkit_package,
)
from app.db.models import (
    AgentProfile,
    AgentResourceBinding,
    GeneralSkill,
    Skill,
    Tenant,
    Tool,
    User,
)


def _zip_path(tmp_path: Path, *, unsafe_member: str | None = None) -> Path:
    path = tmp_path / "designkit-detail-page-1.0.6.zip"
    skill = """---\nname: detail-page\ndisplay_name: 详情模块图\ndescription: 电商详情页模块图 Skill\nversion: 1.0.7\n---\n# source\n"""
    form = {"form": {"fields": [{"key": "images", "required": True, "type": "file_upload"}]}}
    files = {
        "designkit-detail-page/README.md": "# package\n",
        "designkit-detail-page/MIGRATION.md": "当前 1.0.6\n",
        "designkit-detail-page/agents/designkit-detail-page.md": "---\nname: designkit-detail-page\n---\n",
        "designkit-detail-page/skills/detail-page/SKILL.md": skill,
        "designkit-detail-page/skills/detail-page/references/form.json": json.dumps(form),
        "designkit-detail-page/skills-as-standard/SKILL.md": skill,
        "designkit-detail-page/skills-as-standard/references/form.json": json.dumps(form),
    }
    if unsafe_member:
        files[unsafe_member] = "unsafe"
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    db = Session(engine)
    db.add(Tenant(id="tenant_demo", name="Demo"))
    db.add(
        AgentProfile(
            id="agent_designer",
            tenant_id="tenant_demo",
            name="美工设计",
            status="active",
            metadata_json={"business_role": "designer"},
        )
    )
    db.add(
        AgentProfile(
            id="agent_overall",
            tenant_id="tenant_demo",
            name="开放广场",
            is_overall=True,
            status="active",
        )
    )
    db.add(
        User(
            id="admin",
            tenant_id="tenant_demo",
            username="admin",
            role="admin",
            password_hash="disabled",
        )
    )
    db.commit()
    return db


def test_package_rejects_path_traversal(tmp_path: Path) -> None:
    package_path = _zip_path(tmp_path, unsafe_member="designkit-detail-page/../escape.txt")
    with pytest.raises(DesignKitPackageError, match="unsafe ZIP member path"):
        load_designkit_package(package_path)


def test_package_is_idempotent_and_binds_skill_general_skill_and_api(tmp_path: Path) -> None:
    package_path = _zip_path(tmp_path)
    with _session() as db:
        first = provision_designkit_package(
            db,
            tenant_id="tenant_demo",
            agent_id="agent_designer",
            zip_path=package_path,
            tool_base_url="http://localhost:5173",
        )
        second = provision_designkit_package(
            db,
            tenant_id="tenant_demo",
            agent_id="agent_designer",
            zip_path=package_path,
            tool_base_url="http://localhost:5173",
        )
        assert first == second
        assert db.exec(select(Skill).where(Skill.skill_id == SKILL_ID)).one()
        assert db.exec(select(GeneralSkill).where(GeneralSkill.slug == "designkit-detail-page")).one()
        tool = db.exec(select(Tool).where(Tool.name == API_TOOL_NAME)).one()
        assert tool.tool_type == "http"
        assert tool.config_json["mcp_configuration"]["enabled"] is False
        bindings = db.exec(
            select(AgentResourceBinding).where(AgentResourceBinding.agent_id == "agent_designer")
        ).all()
        assert {(row.resource_type, row.status) for row in bindings} >= {
            ("skill", "active"),
            ("general_skill", "active"),
            ("tool", "active"),
        }
