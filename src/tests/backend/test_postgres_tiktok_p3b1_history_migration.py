from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
UP = ROOT / "src/backend/migrations/20260923_tiktok_p3b1_history_v1.sql"
DOWN = ROOT / "src/backend/migrations/20260923_tiktok_p3b1_history_v1.down.sql"
TABLES = (
    "tiktok_history_batches",
    "tiktok_history_facts",
    "tiktok_history_metric_definitions",
    "tiktok_history_reconciliations",
    "tiktok_history_signoffs",
)


def test_history_migration_enforces_tenant_and_append_only_boundaries() -> None:
    up = UP.read_text(encoding="utf-8")
    down = DOWN.read_text(encoding="utf-8")
    for table in TABLES:
        assert f"CREATE TABLE IF NOT EXISTS public.{table}" in up
        assert f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY" in up
        assert f"DROP TABLE IF EXISTS public.{table}" in down
        assert f"GRANT SELECT, INSERT ON public.{table} TO staffdeck_runtime" in up
        assert f"GRANT SELECT, INSERT ON public.{table} TO staffdeck_worker" in up
    assert "FOREIGN KEY (tenant_id, recorded_run_id)" in up
    assert "FOREIGN KEY (tenant_id, batch_id)" in up
    assert "FOREIGN KEY (tenant_id, fact_id)" in up
    assert "app.current_staffdeck_tenant_id()" in up
    assert "BEFORE UPDATE OR DELETE ON public.tiktok_history_facts" in up
    assert "BEFORE UPDATE OR DELETE ON public.tiktok_history_reconciliations" in up
    assert "scope_revision integer NOT NULL" in up
