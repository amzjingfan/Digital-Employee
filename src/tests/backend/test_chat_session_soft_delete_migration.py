from pathlib import Path

from app.db.models import ChatSession, WorkTaskRun

ROOT = Path(__file__).resolve().parents[3]
UP = ROOT / "src/backend/migrations/20260922_chat_session_soft_delete_v1.sql"
DOWN = ROOT / "src/backend/migrations/20260922_chat_session_soft_delete_v1.down.sql"


def _normalized_sql(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def test_chat_session_soft_delete_migration_is_reversible() -> None:
    assert UP.is_file()
    assert DOWN.is_file()

    up_sql = _normalized_sql(UP)
    down_sql = _normalized_sql(DOWN)

    assert "alter table public.sessions" in up_sql
    assert "add column if not exists deleted_at timestamp without time zone" in up_sql
    assert "create index if not exists ix_sessions_deleted_at" in up_sql
    assert "on public.sessions (deleted_at)" in up_sql
    assert "constraint uq_sessions_tenant_id_id unique (tenant_id, id)" in up_sql
    assert "drop constraint if exists work_task_runs_session_fk" in up_sql
    assert "foreign key (tenant_id, session_id)" in up_sql
    assert "references public.sessions (tenant_id, id) on delete restrict" in up_sql
    assert "drop constraint if exists work_task_runs_session_fk" in down_sql
    assert "foreign key (session_id) references public.sessions (id) on delete restrict" in down_sql
    assert "drop constraint if exists uq_sessions_tenant_id_id" in down_sql
    assert "drop index if exists public.ix_sessions_deleted_at" in down_sql
    assert "alter table public.sessions" in down_sql
    assert "drop column if exists deleted_at" in down_sql


def test_chat_session_and_work_task_run_models_use_tenant_scoped_reference() -> None:
    session_unique_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in ChatSession.__table__.constraints
        if constraint.name == "uq_sessions_tenant_id_id"
    }
    run_foreign_keys = {
        (
            tuple(element.parent.name for element in constraint.elements),
            tuple(element.target_fullname for element in constraint.elements),
        )
        for constraint in WorkTaskRun.__table__.foreign_key_constraints
        if constraint.name == "work_task_runs_session_fk"
    }

    assert session_unique_constraints == {("tenant_id", "id")}
    assert run_foreign_keys == {
        (("tenant_id", "session_id"), ("sessions.tenant_id", "sessions.id"))
    }
