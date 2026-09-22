from __future__ import annotations

from pathlib import Path

from app.db.models import TikTokDataValidationRun

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "src" / "backend" / "migrations" / "20260922_tiktok_recorded_validation_v1.sql"
DOWN_MIGRATION = (
    ROOT
    / "src"
    / "backend"
    / "migrations"
    / "20260922_tiktok_recorded_validation_v1.down.sql"
)

RECORDED_FIELDS = (
    "source_label",
    "approval_ref",
    "approved_by_user_id",
    "approved_at",
    "approval_valid_until",
    "data_period_start",
    "data_period_end",
    "replay_as_of",
    "scope_id",
    "scope_revision",
    "contract_digest",
    "attestation_version",
)


def test_recorded_migration_adds_safe_metadata_and_conditional_constraints() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "ADD COLUMN approval_ref" in sql
    assert "ADD COLUMN approved_by_user_id" in sql
    assert "mode IN ('mock', 'recorded')" in sql
    assert "approved_by_user_id <> started_by_user_id" in sql
    assert "FOREIGN KEY (tenant_id, approved_by_user_id)" in sql
    assert "FOREIGN KEY (tenant_id, scope_id)" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "dataset_json" not in sql
    assert "file_name" not in sql


def test_recorded_down_migration_refuses_to_drop_existing_audit_rows() -> None:
    sql = DOWN_MIGRATION.read_text(encoding="utf-8")

    assert "WHERE mode = 'recorded'" in sql
    assert "RAISE EXCEPTION" in sql
    assert "DROP COLUMN approval_ref" in sql
    assert "mode = 'mock'" in sql


def test_validation_run_model_exposes_nullable_recorded_metadata() -> None:
    run = TikTokDataValidationRun(
        tenant_id="tenant_demo",
        catalog_version="p3-b0.v1",
        dataset_digest="sha256:synthetic",
        status="passed",
        started_by_user_id="user_demo",
    )

    assert run.mode == "mock"
    assert {field for field in RECORDED_FIELDS if not hasattr(run, field)} == set()
    assert all(getattr(run, field) is None for field in RECORDED_FIELDS)
