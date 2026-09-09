from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db.database import set_tenant_context as bind_tenant_context
from app.db.models import A2ATaskRun, Tool
from app.tools import a2a_recovery


def test_a2a_recovery_binds_run_tenant_before_tool_execution(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    tenant_contexts: list[str] = []
    captured: dict[str, object] = {}

    with Session(engine) as db:
        db.add(
            Tool(
                id="tool_a2a_recovery",
                tenant_id="tenant_demo",
                name="a2a.recover",
                method="POST",
                url="https://agent.example.test/a2a",
                tool_type="a2a",
            )
        )
        db.add(
            A2ATaskRun(
                id="a2arun_recovery",
                direction="client",
                tenant_id="tenant_demo",
                tool_id="tool_a2a_recovery",
                invocation_id="call-recovery",
                endpoint_url="https://agent.example.test/a2a",
                status="working",
                request_json={"arguments": {"query": "继续"}},
            )
        )
        db.commit()

    def record_tenant_context(db: Session, tenant_id: str) -> None:
        tenant_contexts.append(tenant_id)
        bind_tenant_context(db, tenant_id)

    def fake_execute(self, tenant_id, tool_call, **kwargs):
        captured.update(
            {
                "session_tenant_context": self.db.info.get("staffdeck_tenant_id"),
                "tenant_id": tenant_id,
                "tool_name": tool_call.name,
                "arguments": tool_call.arguments,
                "kwargs": kwargs,
            }
        )

    monkeypatch.setattr(a2a_recovery, "engine", engine)
    monkeypatch.setattr(a2a_recovery, "set_tenant_context", record_tenant_context)
    monkeypatch.setattr(a2a_recovery.ToolExecutor, "execute", fake_execute)

    a2a_recovery._recover_one("a2arun_recovery")

    assert tenant_contexts == ["tenant_demo"]
    assert captured == {
        "session_tenant_context": "tenant_demo",
        "tenant_id": "tenant_demo",
        "tool_name": "a2a.recover",
        "arguments": {"query": "继续"},
        "kwargs": {
            "agent_id": None,
            "session_id": None,
            "invocation_id": "call-recovery",
        },
    }


def test_a2a_recovery_rejects_tool_from_another_tenant(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    tenant_contexts: list[str] = []

    with Session(engine) as db:
        db.add(
            Tool(
                id="tool_a2a_other_tenant",
                tenant_id="tenant_other",
                name="a2a.other",
                method="POST",
                url="https://agent.example.test/a2a",
                tool_type="a2a",
            )
        )
        db.add(
            A2ATaskRun(
                id="a2arun_tool_mismatch",
                direction="client",
                tenant_id="tenant_demo",
                tool_id="tool_a2a_other_tenant",
                invocation_id="call-mismatch",
                endpoint_url="https://agent.example.test/a2a",
                status="submitted",
            )
        )
        db.commit()

    def record_tenant_context(db: Session, tenant_id: str) -> None:
        tenant_contexts.append(tenant_id)
        bind_tenant_context(db, tenant_id)

    execute_called = False

    def fail_execute(*args, **kwargs):
        nonlocal execute_called
        execute_called = True
        raise AssertionError("cross-tenant tool must not execute")

    monkeypatch.setattr(a2a_recovery, "engine", engine)
    monkeypatch.setattr(a2a_recovery, "set_tenant_context", record_tenant_context)
    monkeypatch.setattr(a2a_recovery.ToolExecutor, "execute", fail_execute)

    a2a_recovery._recover_one("a2arun_tool_mismatch")

    with Session(engine) as db:
        run = db.get(A2ATaskRun, "a2arun_tool_mismatch")

    assert tenant_contexts == ["tenant_demo"]
    assert execute_called is False
    assert run is not None and run.status == "failed"
    assert run.error_json["code"] == "A2A_RECOVERY_TOOL_MISSING"
    assert run.error_json["tool_tenant_mismatch"] is True
