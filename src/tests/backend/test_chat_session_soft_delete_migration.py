from pathlib import Path

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
    assert "add column if not exists deleted_at timestamptz" in up_sql
    assert "create index if not exists ix_sessions_deleted_at" in up_sql
    assert "on public.sessions (deleted_at)" in up_sql
    assert "drop index if exists public.ix_sessions_deleted_at" in down_sql
    assert "alter table public.sessions" in down_sql
    assert "drop column if exists deleted_at" in down_sql
