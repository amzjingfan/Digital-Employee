"""Opt-in RLS and rollback acceptance against a disposable local PostgreSQL cluster."""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlmodel import Session, select

from app.db.models import TikTokCommissionDraft
from app.tiktok.commission_drafts import _overlap_index

MIGRATIONS = Path(__file__).resolve().parents[2] / "backend" / "migrations"
UP = MIGRATIONS / "20260924_tiktok_e03_unapproved_drafts_v1.sql"
DOWN = MIGRATIONS / "20260924_tiktok_e03_unapproved_drafts_v1.down.sql"
INDEX_UP = MIGRATIONS / "20260924_tiktok_e03_unapproved_drafts_v2_order_index.sql"
INDEX_DOWN = MIGRATIONS / "20260924_tiktok_e03_unapproved_drafts_v2_order_index.down.sql"
ORDER_REF = "order:" + "a" * 32
ORDER_JSON = f'["{ORDER_REF}"]'

pytestmark = pytest.mark.skipif(
    os.getenv("JOUKIR_RUN_E03_DRAFT_PG") != "1",
    reason="requires a disposable local PostgreSQL cluster explicitly selected by the caller",
)


def _connection(port: int, dbname: str, user: str) -> psycopg.Connection:
    return psycopg.connect(
        host="127.0.0.1", port=port, dbname=dbname, user=user,
        connect_timeout=5, autocommit=True,
    )


def test_unapproved_draft_rls_fks_append_only_and_empty_rollback() -> None:
    port = int(os.environ["JOUKIR_E03_DRAFT_PG_PORT"])
    dbname = f"joukir_e03_draft_accept_{uuid4().hex[:12]}"
    with _connection(port, "postgres", "postgres") as admin:
        data_dir = Path(admin.execute("SHOW data_directory").fetchone()[0])
        assert data_dir.name.startswith("joukir-p3b2-pg-acceptance-")
        assert port != 55433
        for role in ("staffdeck_migrator", "staffdeck_runtime"):
            if admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone() is None:
                admin.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS").format(
                    sql.Identifier(role)
                ))
        admin.execute(sql.SQL("CREATE DATABASE {} OWNER staffdeck_migrator").format(
            sql.Identifier(dbname)
        ))

    with _connection(port, dbname, "staffdeck_migrator") as migrator:
        migrator.execute("""
            CREATE SCHEMA app;
            CREATE FUNCTION app.current_staffdeck_tenant_id() RETURNS text
              LANGUAGE sql STABLE AS $$
                SELECT NULLIF(current_setting('app.tenant_id', true), '')
              $$;
            REVOKE ALL ON FUNCTION app.current_staffdeck_tenant_id() FROM PUBLIC;
            GRANT USAGE ON SCHEMA app, public TO staffdeck_runtime;
            GRANT EXECUTE ON FUNCTION app.current_staffdeck_tenant_id()
              TO staffdeck_runtime;
            CREATE TABLE public.tenants (id varchar PRIMARY KEY);
            CREATE TABLE public.users (
              id varchar PRIMARY KEY, tenant_id varchar NOT NULL,
              UNIQUE (tenant_id, id)
            );
            CREATE TABLE public.tiktok_creator_pool (
              id varchar PRIMARY KEY, tenant_id varchar NOT NULL,
              UNIQUE (tenant_id, id)
            );
            CREATE TABLE public.staffdeck_schema_migrations (
              migration_id varchar PRIMARY KEY, applied_at timestamptz NOT NULL,
              source_kind varchar NOT NULL, source_table_count integer NOT NULL,
              source_row_count integer NOT NULL
            );
            INSERT INTO public.tenants VALUES ('tenant_a'), ('tenant_b');
            INSERT INTO public.users VALUES ('user_a', 'tenant_a'), ('user_b', 'tenant_b');
            INSERT INTO public.tiktok_creator_pool VALUES
              ('pool_a', 'tenant_a'), ('pool_a2', 'tenant_a'),
              ('pool_a3', 'tenant_a'), ('pool_b', 'tenant_b');
        """)
        migrator.execute(UP.read_text(encoding="utf-8"))
        assert migrator.execute("""
            SELECT relrowsecurity, relforcerowsecurity FROM pg_class
            WHERE relname='tiktok_commission_drafts'
        """).fetchone() == (True, True)

    insert = """
        INSERT INTO public.tiktok_commission_drafts (
          id, tenant_id, pool_id, pool_revision, owner_user_id,
          fulfillment_user_id, maintenance_user_id, rule_version,
          rule_expires_at, order_refs_json, development_bps, fulfillment_bps,
          maintenance_bps, calculation_evidence_ref, idempotency_key,
          request_digest, created_by_user_id, created_at
        ) VALUES (
          %s, %s, %s, 3, %s, %s, %s, 'proposal-v1', now() + interval '1 day',
          %s, 6000, 2000, 2000,
          'evidence:cccccccccccccccccccccccccccccccc', %s, 'sha256:test', %s, now()
        )
    """
    with _connection(port, dbname, "staffdeck_runtime") as runtime:
        assert runtime.execute("SELECT count(*) FROM public.tiktok_commission_drafts").fetchone()[0] == 0
        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_a', true)")
        runtime.execute(insert, (
            "draft_a", "tenant_a", "pool_a", "user_a", "user_a", "user_a",
            ORDER_JSON, "1" * 32, "user_a",
        ))
        assert runtime.execute("SELECT count(*) FROM public.tiktok_commission_drafts").fetchone()[0] == 1
        runtime.execute("COMMIT")

    for bad_json, expected_error in (
        ("not-json", psycopg.errors.InvalidTextRepresentation),
        (f'["{ORDER_REF}","{ORDER_REF}"]', psycopg.errors.UniqueViolation),
    ):
        with _connection(port, dbname, "staffdeck_runtime") as runtime:
            runtime.execute("BEGIN")
            runtime.execute("SELECT set_config('app.tenant_id', 'tenant_a', true)")
            runtime.execute(insert, (
                "draft_bad", "tenant_a", "pool_a", "user_a", "user_a", "user_a",
                bad_json, "6" * 32, "user_a",
            ))
            runtime.execute("COMMIT")
        with _connection(port, dbname, "staffdeck_migrator") as migrator:
            with pytest.raises(expected_error):
                migrator.execute(INDEX_UP.read_text(encoding="utf-8"))
            migrator.execute("ROLLBACK")
            assert migrator.execute("""
                SELECT to_regclass('public.tiktok_commission_draft_order_refs')
            """).fetchone()[0] is None
            assert migrator.execute("""
                SELECT count(*) FROM pg_policies
                WHERE policyname IN (
                  'migration_draft_order_ref_read', 'migration_draft_order_ref_insert'
                )
            """).fetchone()[0] == 0
        with _connection(port, dbname, "staffdeck_runtime") as runtime:
            runtime.execute("BEGIN")
            runtime.execute("SELECT set_config('app.tenant_id', 'tenant_a', true)")
            assert runtime.execute("SELECT count(*) FROM public.tiktok_commission_drafts").fetchone()[0] == 2
            runtime.execute("COMMIT")
        with _connection(port, dbname, "postgres") as administrator:
            administrator.execute("TRUNCATE public.tiktok_commission_drafts")
        with _connection(port, dbname, "staffdeck_runtime") as runtime:
            runtime.execute("BEGIN")
            runtime.execute("SELECT set_config('app.tenant_id', 'tenant_a', true)")
            runtime.execute(insert, (
                "draft_a", "tenant_a", "pool_a", "user_a", "user_a", "user_a",
                ORDER_JSON, "1" * 32, "user_a",
            ))
            runtime.execute("COMMIT")

    with _connection(port, dbname, "staffdeck_runtime") as blocker:
        blocker.execute("BEGIN")
        blocker.execute("SELECT set_config('app.tenant_id', 'tenant_a', true)")
        blocker.execute(insert, (
            "draft_held", "tenant_a", "pool_a", "user_a", "user_a", "user_a",
            ORDER_JSON, "7" * 32, "user_a",
        ))
        try:
            with _connection(port, dbname, "staffdeck_migrator") as migrator:
                migrator.execute("SET statement_timeout = '10s'")
                prior_lock_timeout = migrator.execute("SHOW lock_timeout").fetchone()[0]
                with pytest.raises(psycopg.errors.LockNotAvailable):
                    migrator.execute(INDEX_UP.read_text(encoding="utf-8"))
                migrator.execute("ROLLBACK")
                assert migrator.execute("SHOW lock_timeout").fetchone()[0] == prior_lock_timeout
                assert migrator.execute("""
                    SELECT to_regclass('public.tiktok_commission_draft_order_refs')
                """).fetchone()[0] is None
                assert migrator.execute("""
                    SELECT count(*) FROM public.staffdeck_schema_migrations
                    WHERE migration_id='20260924_tiktok_e03_unapproved_drafts_v2_order_index'
                """).fetchone()[0] == 0
        finally:
            blocker.execute("ROLLBACK")

    with _connection(port, dbname, "staffdeck_migrator") as migrator:
        prior_lock_timeout = migrator.execute("SHOW lock_timeout").fetchone()[0]
        migrator.execute(INDEX_UP.read_text(encoding="utf-8"))
        assert migrator.execute("SHOW lock_timeout").fetchone()[0] == prior_lock_timeout
        definition = migrator.execute("""
            SELECT indexdef FROM pg_indexes
            WHERE schemaname='public'
              AND indexname='ix_tiktok_commission_draft_order_ref_lookup'
        """).fetchone()[0]
        assert "btree" in definition.lower()
        assert "order_ref" in definition
        assert migrator.execute("""
            SELECT relrowsecurity, relforcerowsecurity FROM pg_class
            WHERE relname='tiktok_commission_draft_order_refs'
        """).fetchone() == (True, True)
        assert migrator.execute("""
            SELECT count(*) FROM pg_policies
            WHERE policyname IN (
              'migration_draft_order_ref_read', 'migration_draft_order_ref_insert'
            )
        """).fetchone()[0] == 0
    with _connection(port, dbname, "staffdeck_runtime") as runtime:
        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_a', true)")
        assert runtime.execute("""
            SELECT draft_id FROM public.tiktok_commission_draft_order_refs
            WHERE order_ref=%s
        """, (ORDER_REF,)).fetchone()[0] == "draft_a"
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute("""
                INSERT INTO public.tiktok_commission_draft_order_refs
                (tenant_id, draft_id, order_ref) VALUES ('tenant_a', 'draft_a', %s)
            """, (ORDER_REF,))
        runtime.execute("ROLLBACK")

    barrier = Barrier(2)

    def concurrent_save(draft_id: str, pool_id: str, key: str) -> None:
        with _connection(port, dbname, "staffdeck_runtime") as connection:
            connection.execute("BEGIN")
            connection.execute("SELECT set_config('app.tenant_id', 'tenant_a', true)")
            barrier.wait(timeout=10)
            connection.execute(insert, (
                draft_id, "tenant_a", pool_id, "user_a", "user_a", "user_a",
                ORDER_JSON, key, "user_a",
            ))
            connection.execute("COMMIT")

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(concurrent_save, "draft_a2", "pool_a2", "2" * 32)
        second = executor.submit(concurrent_save, "draft_a3", "pool_a3", "3" * 32)
        first.result(timeout=15)
        second.result(timeout=15)

    with _connection(port, dbname, "staffdeck_runtime") as runtime:
        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_b', true)")
        runtime.execute(insert, (
            "draft_b", "tenant_b", "pool_b", "user_b", "user_b", "user_b",
            ORDER_JSON, "5" * 32, "user_b",
        ))
        runtime.execute("COMMIT")

    with _connection(port, dbname, "staffdeck_runtime") as runtime:
        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_a', true)")
        matches = runtime.execute("""
            SELECT draft_id FROM public.tiktok_commission_draft_order_refs
            WHERE tenant_id='tenant_a' AND order_ref=%s
            ORDER BY draft_id
        """, (ORDER_REF,)).fetchall()
        assert [row[0] for row in matches] == ["draft_a", "draft_a2", "draft_a3"]
        runtime.execute("SET LOCAL enable_seqscan=off")
        plan = runtime.execute("""
            EXPLAIN SELECT draft_id FROM public.tiktok_commission_draft_order_refs
            WHERE tenant_id='tenant_a' AND order_ref=%s
        """, (ORDER_REF,)).fetchall()
        assert "ix_tiktok_commission_draft_order_ref_lookup" in "\n".join(
            row[0] for row in plan
        )
        runtime.execute("COMMIT")
        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_b', true)")
        assert runtime.execute("""
            SELECT draft_id FROM public.tiktok_commission_draft_order_refs
            WHERE order_ref=%s
        """, (ORDER_REF,)).fetchall() == [("draft_b",)]
        runtime.execute("COMMIT")

    engine = create_engine(f"postgresql+psycopg://staffdeck_runtime@127.0.0.1:{port}/{dbname}")
    try:
        with Session(engine) as db:
            db.exec(text("SELECT set_config('app.tenant_id', 'tenant_a', true)"))
            target = db.exec(select(TikTokCommissionDraft).where(
                TikTokCommissionDraft.id == "draft_a",
            )).one()
            assert _overlap_index(db, "tenant_a", [target])[ORDER_REF] == {
                "draft_a", "draft_a2", "draft_a3",
            }
    finally:
        engine.dispose()

    with _connection(port, dbname, "staffdeck_migrator") as migrator:
        migrator.execute(INDEX_DOWN.read_text(encoding="utf-8"))
        assert migrator.execute("""
            SELECT to_regclass('public.tiktok_commission_draft_order_refs')
        """).fetchone()[0] is None
        migrator.execute(INDEX_UP.read_text(encoding="utf-8"))
    with _connection(port, dbname, "staffdeck_runtime") as runtime:
        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_a', true)")
        assert runtime.execute("""
            SELECT count(*) FROM public.tiktok_commission_draft_order_refs
            WHERE order_ref=%s
        """, (ORDER_REF,)).fetchone()[0] == 3
        runtime.execute("COMMIT")
    with _connection(port, dbname, "staffdeck_migrator") as migrator:
        migrator.execute(INDEX_DOWN.read_text(encoding="utf-8"))
    with _connection(port, dbname, "staffdeck_runtime") as runtime:
        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_a', true)")
        assert runtime.execute("SELECT count(*) FROM public.tiktok_commission_drafts").fetchone()[0] == 3
        runtime.execute("COMMIT")
        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_b', true)")
        assert runtime.execute("SELECT count(*) FROM public.tiktok_commission_drafts").fetchone()[0] == 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute("UPDATE public.tiktok_commission_drafts SET rule_version='other'")
        runtime.execute("ROLLBACK")

    with _connection(port, dbname, "postgres") as administrator:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            administrator.execute(insert, (
                "wrong_pool", "tenant_a", "pool_b", "user_a", "user_a", "user_a",
                ORDER_JSON, "4" * 32, "user_a",
            ))
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            administrator.execute("DELETE FROM public.tiktok_commission_drafts WHERE id='draft_a'")
        administrator.execute("TRUNCATE public.tiktok_commission_drafts")
    with _connection(port, dbname, "staffdeck_migrator") as migrator:
        migrator.execute(DOWN.read_text(encoding="utf-8"))
        assert migrator.execute("SELECT to_regclass('public.tiktok_commission_drafts')").fetchone()[0] is None
