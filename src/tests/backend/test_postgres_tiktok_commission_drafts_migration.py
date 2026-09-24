from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "backend" / "migrations"
UP = MIGRATIONS / "20260924_tiktok_e03_unapproved_drafts_v1.sql"
DOWN = MIGRATIONS / "20260924_tiktok_e03_unapproved_drafts_v1.down.sql"
INDEX_UP = MIGRATIONS / "20260924_tiktok_e03_unapproved_drafts_v2_order_index.sql"
INDEX_DOWN = MIGRATIONS / "20260924_tiktok_e03_unapproved_drafts_v2_order_index.down.sql"


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


def test_order_reference_index_migration_preserves_proposal_data_on_rollback() -> None:
    up = INDEX_UP.read_text(encoding="utf-8")
    down = INDEX_DOWN.read_text(encoding="utf-8")
    assert "CREATE TABLE public.tiktok_commission_draft_order_refs" in up
    assert "FOREIGN KEY (tenant_id, draft_id)" in up
    assert "(tenant_id, order_ref, draft_id)" in up
    assert "FORCE ROW LEVEL SECURITY" in up
    assert "SECURITY DEFINER" in up
    assert "DROP POLICY migration_draft_order_ref_read" in up
    assert "DROP POLICY migration_draft_order_ref_insert" in up
    assert "GRANT SELECT ON public.tiktok_commission_draft_order_refs" in up
    assert "GRANT INSERT ON public.tiktok_commission_draft_order_refs TO staffdeck_runtime" not in up
    assert "DROP TABLE public.tiktok_commission_draft_order_refs" in down
    assert "DROP TABLE public.tiktok_commission_drafts" not in down
    assert "TRUNCATE" not in down
