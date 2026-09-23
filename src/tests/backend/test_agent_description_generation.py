from __future__ import annotations

import asyncio
from threading import Event

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

            def generate_text_stream(
                self, prompt: str, payload: dict[str, object], *, cancellation=None
            ):
                seen["prompt"] = prompt
                seen["payload"] = payload
                yield "职责：\n负责财务资料整理。\n\n工作边界：\n"
                yield "异常事项交由授权人员确认。\n\n服务风格：\n清晰、审慎。\n\n执行重点：\n核对资料。"

        monkeypatch.setattr(agents, "resolve_model_config_for_runtime", resolve_model)
        monkeypatch.setattr(agents, "LLMClient", FakeLLMClient)
        response = agents.generate_agent_description(
            agents.AgentDescriptionGenerateRequest(
                tenant_id="tenant_demo",
                role_name="财务助理",
            ),
            db=db,
            current_user=user,
        )

        async def collect() -> list[str]:
            return [part async for part in response.body_iterator]

        events = asyncio.run(collect())
        assert response.media_type == "text/event-stream"
        assert response.headers["cache-control"] == "no-cache"
        assert len([part for part in events if "event: delta" in part]) == 2
        assert '"description": "职责：\\n负责财务资料整理。\\n\\n工作边界：' in events[-1]
        assert "服务风格：" in events[-1]
        assert "执行重点：" in events[-1]
        assert seen["model"] == ("tenant_demo", "default_model")
        assert seen["payload"] == {"role_name": "财务助理"}
        assert "工作边界" in str(seen["prompt"])
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

            def generate_text_stream(
                self, _prompt: str, _payload: dict[str, object], *, cancellation=None
            ):
                yield " "

        monkeypatch.setattr(agents, "LLMClient", EmptyLLMClient)
        response = agents.generate_agent_description(
            agents.AgentDescriptionGenerateRequest(tenant_id="tenant_demo", role_name="财务助理"),
            db=db,
            current_user=user,
        )

        async def collect() -> str:
            return "".join([part async for part in response.body_iterator])

        events = asyncio.run(collect())
        assert "event: error" in events
        assert "event: done" not in events


def test_description_requires_four_nonempty_sections_in_order() -> None:
    assert agents._normalize_agent_description(
        "职责：\n整理资料。\n\n工作边界：\n交给人工。\n\n服务风格：\n清晰。"
    ) is None
    assert agents._normalize_agent_description(
        "职责：\n整理资料。\n\n工作边界：\n交给人工。\n\n服务风格：\n清晰。\n\n执行重点：\n"
    ) is None


def test_cancelling_stream_cancels_model_and_closes_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = Event()
    seen: dict[str, object] = {}

    class ModelConnection:
        def close(self) -> None:
            release.set()

    class FakeLLMClient:
        def __init__(self, _config: object) -> None:
            self.client = ModelConnection()

        def generate_text_stream(self, _prompt: str, _payload: dict[str, object], *, cancellation):
            seen["cancellation"] = cancellation
            yield "职责：\n整理资料。"
            release.wait(timeout=2)

    with _session() as db:
        user, _source = _seed(db)
        monkeypatch.setattr(agents, "resolve_model_config_for_runtime", lambda *_: object())
        monkeypatch.setattr(agents, "LLMClient", FakeLLMClient)
        response = agents.generate_agent_description(
            agents.AgentDescriptionGenerateRequest(tenant_id="tenant_demo", role_name="财务助理"),
            db=db,
            current_user=user,
        )

        async def cancel_after_first_delta() -> None:
            await response.body_iterator.__anext__()
            pending = asyncio.create_task(response.body_iterator.__anext__())
            await asyncio.sleep(0.02)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending

        asyncio.run(cancel_after_first_delta())
        assert seen["cancellation"].cancelled
        assert release.is_set()
