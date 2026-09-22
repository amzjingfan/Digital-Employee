from __future__ import annotations

from pathlib import Path

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import (
    Tenant,
    TikTokCapabilityEvidence,
    TikTokDataValidationRun,
    TikTokDataValidationScope,
    TikTokFieldContract,
)

ROOT = Path(__file__).resolve().parents[3]
UP = ROOT / "src/backend/migrations/20260922_tiktok_data_validation_workbench_v1.sql"
DOWN = ROOT / "src/backend/migrations/20260922_tiktok_data_validation_workbench_v1.down.sql"
TABLES = (
    "tiktok_data_validation_scopes",
    "tiktok_field_contracts",
    "tiktok_capability_evidence",
    "tiktok_data_validation_runs",
)


def test_sqlmodel_tables_are_tenant_scoped() -> None:
    assert {
        TikTokDataValidationScope.__tablename__,
        TikTokFieldContract.__tablename__,
        TikTokCapabilityEvidence.__tablename__,
        TikTokDataValidationRun.__tablename__,
    } == set(TABLES)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Tenant(id="tenant_a", name="Tenant A"))
        db.add(
            TikTokFieldContract(
                tenant_id="tenant_a",
                field_code="order.order_id",
                domain="order",
                label="订单 ID",
                data_type="string",
                required=True,
                business_key="order_id",
                missing_behavior="block_stage",
                sources_json=[],
            )
        )
        db.commit()
        assert db.exec(
            select(TikTokFieldContract).where(TikTokFieldContract.tenant_id == "tenant_a")
        ).one().field_code == "order.order_id"


def test_postgres_migration_has_force_rls_composite_constraints_and_append_only_runs() -> None:
    migration = UP.read_text(encoding="utf-8")
    rollback = DOWN.read_text(encoding="utf-8")
    for table in TABLES:
        assert f"CREATE TABLE IF NOT EXISTS public.{table}" in migration
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in migration
        assert f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY" in migration
        assert f"DROP TABLE IF EXISTS public.{table}" in rollback
    assert migration.count("app.current_staffdeck_tenant_id()") >= 4
    assert "FOREIGN KEY (tenant_id, store_resource_id)" in migration
    assert "FOREIGN KEY (tenant_id, owner_user_id)" in migration
    assert "FOREIGN KEY (tenant_id, checked_by_user_id)" in migration
    assert "reject_tiktok_data_validation_run_mutation" in migration
    assert "BEFORE UPDATE OR DELETE ON public.tiktok_data_validation_runs" in migration
    assert "GRANT SELECT, INSERT ON public.tiktok_data_validation_runs TO staffdeck_runtime" in migration
