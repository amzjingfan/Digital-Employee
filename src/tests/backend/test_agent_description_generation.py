from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api import agents
from app.db.models import AgentProfile, ModelConfig, Tenant, User


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed(db: Session) -> tuple[User, AgentProfile]:
    db.add(Tenant(id="tenant_demo", name="Demo"))
    user = User(
        id="user_admin",
        tenant_id="tenant_demo",
        username="admin",
        role="admin",
        password_hash="x",
    )
    source = AgentProfile(
        id="source_agent",
        tenant_id="tenant_demo",
        name="现有助理",
        description="负责整理资料并提醒人工审核。",
        metadata_json={"owner_user_id": user.id},
    )
    db.add(user)
    db.add(source)
    db.add(
        ModelConfig(
            id="default_model",
            tenant_id="tenant_demo",
            name="默认模型",
            api_key_encrypted="",
            model="test-model",
            is_default=True,
            enabled=True,
        )
    )
    db.commit()
    return user, source


def test_generates_draft_from_role_without_copying_employee_data(monkeypatch: pytest.MonkeyPatch) -> None:
    with _session() as db:
        user, source = _seed(db)
        seen: dict[str, object] = {}

        def resolve_model(_db: Session, tenant_id: str, config_id: str) -> object:
            seen["model"] = (tenant_id, config_id)
            return object()

        class FakeLLMClient:
            def __init__(self, _config: object) -> None:
                pass

            def generate_json(self, prompt: str, payload: dict[str, object]) -> dict[str, str]:
                seen["prompt"] = prompt
                seen["payload"] = payload
                return {"description": "  负责财务资料整理；异常事项交由授权人员确认。  "}

        monkeypatch.setattr(agents, "resolve_model_config_for_runtime", resolve_model)
        monkeypatch.setattr(agents, "LLMClient", FakeLLMClient)
        result = agents.generate_agent_description(
            agents.AgentDescriptionGenerateRequest(
                tenant_id="tenant_demo",
                role_name="财务助理",
            ),
            db=db,
            current_user=user,
        )

        assert result.description == "负责财务资料整理；异常事项交由授权人员确认。"
        assert seen["model"] == ("tenant_demo", "default_model")
        assert seen["payload"] == {"role_name": "财务助理"}
        assert "岗位边界" in str(seen["prompt"])
        assert db.get(AgentProfile, source.id).description == source.description


def test_rejects_cross_tenant_request_before_model_call() -> None:
    with _session() as db:
        user, _source = _seed(db)
        with pytest.raises(HTTPException) as error:
            agents.generate_agent_description(
                agents.AgentDescriptionGenerateRequest(
                    tenant_id="other_tenant", role_name="财务助理"
                ),
                db=db,
                current_user=user,
            )
        assert error.value.status_code == 403


def test_generation_request_rejects_copied_employee_content() -> None:
    with pytest.raises(ValidationError):
        agents.AgentDescriptionGenerateRequest(
            tenant_id="tenant_demo",
            role_name="财务助理",
            source_description="已有员工的内部描述",
        )


def test_empty_model_output_does_not_create_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    with _session() as db:
        user, _source = _seed(db)
        monkeypatch.setattr(agents, "resolve_model_config_for_runtime", lambda *_: object())

        class EmptyLLMClient:
            def __init__(self, _config: object) -> None:
                pass

            def generate_json(self, _prompt: str, _payload: dict[str, object]) -> dict[str, str]:
                return {"description": " "}

        monkeypatch.setattr(agents, "LLMClient", EmptyLLMClient)
        with pytest.raises(HTTPException) as error:
            agents.generate_agent_description(
                agents.AgentDescriptionGenerateRequest(
                    tenant_id="tenant_demo", role_name="财务助理"
                ),
                db=db,
                current_user=user,
            )
        assert error.value.status_code == 502
