"""Opt-in RLS and rollback acceptance against a disposable local PostgreSQL cluster."""

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

MIGRATIONS = Path(__file__).resolve().parents[2] / "backend" / "migrations"
UP = MIGRATIONS / "20260924_tiktok_e03_unapproved_drafts_v1.sql"
DOWN = MIGRATIONS / "20260924_tiktok_e03_unapproved_drafts_v1.down.sql"

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
              ('pool_a', 'tenant_a'), ('pool_b', 'tenant_b');
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
          '["order:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]', 6000, 2000, 2000,
          'evidence:cccccccccccccccccccccccccccccccc', %s, 'sha256:test', %s, now()
        )
    """
    with _connection(port, dbname, "staffdeck_runtime") as runtime:
        assert runtime.execute("SELECT count(*) FROM public.tiktok_commission_drafts").fetchone()[0] == 0
        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_a', true)")
        runtime.execute(insert, (
            "draft_a", "tenant_a", "pool_a", "user_a", "user_a", "user_a",
            "1" * 32, "user_a",
        ))
        assert runtime.execute("SELECT count(*) FROM public.tiktok_commission_drafts").fetchone()[0] == 1
        runtime.execute("COMMIT")
        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_b', true)")
        assert runtime.execute("SELECT count(*) FROM public.tiktok_commission_drafts").fetchone()[0] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute("UPDATE public.tiktok_commission_drafts SET rule_version='other'")
        runtime.execute("ROLLBACK")

    with _connection(port, dbname, "postgres") as administrator:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            administrator.execute(insert, (
                "wrong_pool", "tenant_a", "pool_b", "user_a", "user_a", "user_a",
                "2" * 32, "user_a",
            ))
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            administrator.execute("DELETE FROM public.tiktok_commission_drafts WHERE id='draft_a'")
        administrator.execute("TRUNCATE public.tiktok_commission_drafts")
    with _connection(port, dbname, "staffdeck_migrator") as migrator:
        migrator.execute(DOWN.read_text(encoding="utf-8"))
        assert migrator.execute("SELECT to_regclass('public.tiktok_commission_drafts')").fetchone()[0] is None
