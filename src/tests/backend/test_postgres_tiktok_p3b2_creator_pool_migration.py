from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
UP = ROOT / "src/backend/migrations/20260923_tiktok_p3b2_creator_pool_v1.sql"
DOWN = ROOT / "src/backend/migrations/20260923_tiktok_p3b2_creator_pool_v1.down.sql"
TRANSFER_UP = ROOT / "src/backend/migrations/20260923_tiktok_p3b2_owner_transfer_v1.sql"
TRANSFER_DOWN = ROOT / "src/backend/migrations/20260923_tiktok_p3b2_owner_transfer_v1.down.sql"


def test_creator_pool_migration_preserves_tenant_and_event_boundaries() -> None:
    up = UP.read_text(encoding="utf-8")
    down = DOWN.read_text(encoding="utf-8")
    for table in ("tiktok_creator_pool", "tiktok_creator_pool_events"):
        assert f"CREATE TABLE IF NOT EXISTS public.{table}" in up
        assert f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY" in up
        assert f"DROP TABLE IF EXISTS public.{table}" in down
        assert "app.current_staffdeck_tenant_id()" in up
    assert "UNIQUE (tenant_id, creator_id)" in up
    assert "FOREIGN KEY (tenant_id, creator_id)" in up
    assert "FOREIGN KEY (tenant_id, identity_id, creator_id)" in up
    assert "FOREIGN KEY (tenant_id, pool_id)" in up
    assert "FOREIGN KEY (tenant_id, previous_owner_user_id)" in up
    assert "FOREIGN KEY (tenant_id, new_owner_user_id)" in up
    assert "BEFORE UPDATE OR DELETE ON public.tiktok_creator_pool_events" in up
    assert "GRANT SELECT, INSERT ON public.tiktok_creator_pool TO staffdeck_runtime" in up
    assert "GRANT UPDATE (state, owner_user_id, follow_up_due_at, revision, updated_at)" in up
    assert "GRANT SELECT, INSERT ON public.tiktok_creator_pool_events TO staffdeck_runtime" in up


def test_owner_transfer_migration_extends_event_constraint_reversibly() -> None:
    up = TRANSFER_UP.read_text(encoding="utf-8")
    down = TRANSFER_DOWN.read_text(encoding="utf-8")
    for event_type in ("'transferred'", "'released'"):
        assert event_type in up
        assert event_type not in down
    assert "tiktok_creator_pool_events_event_type_check" in up
    assert "tiktok_creator_pool_events_event_type_check" in down
    assert "20260923_tiktok_p3b2_owner_transfer_v1" in up
    assert "20260923_tiktok_p3b2_owner_transfer_v1" in down
