from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "backend" / "migrations"
UP = MIGRATIONS / "20260924_tiktok_e03_unapproved_drafts_v1.sql"
DOWN = MIGRATIONS / "20260924_tiktok_e03_unapproved_drafts_v1.down.sql"


def test_unapproved_draft_migration_preserves_tenant_and_immutability() -> None:
    up = UP.read_text(encoding="utf-8")
    down = DOWN.read_text(encoding="utf-8")
    assert "FOREIGN KEY (tenant_id, pool_id)" in up
    assert "FOREIGN KEY (tenant_id, owner_user_id)" in up
    assert "UNIQUE (tenant_id, idempotency_key)" in up
    assert "approval_state = 'unapproved'" in up
    assert "FORCE ROW LEVEL SECURITY" in up
    assert "tenant_id = app.current_staffdeck_tenant_id()" in up
    assert "BEFORE UPDATE OR DELETE ON public.tiktok_commission_drafts" in up
    assert "GRANT SELECT, INSERT ON public.tiktok_commission_drafts" in up
    assert "GRANT UPDATE" not in up
    assert "DROP TABLE public.tiktok_commission_drafts" in down
