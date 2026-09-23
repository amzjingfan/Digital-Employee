"""Opt-in migration and RLS acceptance on a disposable local PostgreSQL cluster."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

MIGRATIONS = Path(__file__).resolve().parents[2] / "backend" / "migrations"
UP = MIGRATIONS / "20260923_tiktok_p3b2_creator_pool_v1.sql"
DOWN = MIGRATIONS / "20260923_tiktok_p3b2_creator_pool_v1.down.sql"
TRANSFER_UP = MIGRATIONS / "20260923_tiktok_p3b2_owner_transfer_v1.sql"
TRANSFER_DOWN = MIGRATIONS / "20260923_tiktok_p3b2_owner_transfer_v1.down.sql"

pytestmark = pytest.mark.skipif(
    os.getenv("JOUKIR_RUN_P3B2_ISOLATED_PG") != "1",
    reason="requires an explicitly selected disposable local PostgreSQL cluster",
)


def _connection(port: int, dbname: str, user: str) -> psycopg.Connection:
    return psycopg.connect(
        host="127.0.0.1", port=port, dbname=dbname, user=user,
        connect_timeout=5, autocommit=True,
    )


def test_creator_pool_forward_rls_constraints_and_rollback() -> None:
    port = int(os.environ["JOUKIR_P3B2_ISOLATED_PG_PORT"])
    dbname = f"joukir_p3b2_accept_{uuid4().hex[:12]}"
    with _connection(port, "postgres", "postgres") as admin:
        data_dir = Path(admin.execute("SHOW data_directory").fetchone()[0])
        assert data_dir.name.startswith("joukir-p3b2-pg-acceptance-")
        assert port != 55433  # The restored development service must never be used here.
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
            CREATE TABLE public.social_creators (
              id varchar PRIMARY KEY, tenant_id varchar NOT NULL,
              UNIQUE (tenant_id, id)
            );
            CREATE TABLE public.social_platform_identities (
              id varchar PRIMARY KEY, tenant_id varchar NOT NULL,
              creator_id varchar NOT NULL,
              UNIQUE (tenant_id, id, creator_id)
            );
            CREATE TABLE public.staffdeck_schema_migrations (
              migration_id varchar PRIMARY KEY, applied_at timestamptz NOT NULL,
              source_kind varchar NOT NULL, source_table_count integer NOT NULL,
              source_row_count integer NOT NULL
            );
            INSERT INTO public.tenants VALUES ('tenant_a'), ('tenant_b');
            INSERT INTO public.users VALUES
              ('user_a', 'tenant_a'), ('user_b', 'tenant_b');
            INSERT INTO public.social_creators VALUES
              ('creator_a', 'tenant_a'), ('creator_b', 'tenant_b');
            INSERT INTO public.social_platform_identities VALUES
              ('identity_a', 'tenant_a', 'creator_a'),
              ('identity_b', 'tenant_b', 'creator_b');
        """)
        migrator.execute(UP.read_text(encoding="utf-8"))
        migrator.execute(TRANSFER_UP.read_text(encoding="utf-8"))
        assert migrator.execute("""
            SELECT count(*) FROM pg_class
            WHERE relname IN ('tiktok_creator_pool', 'tiktok_creator_pool_events')
              AND relrowsecurity AND relforcerowsecurity
        """).fetchone()[0] == 2
        assert migrator.execute("""
            SELECT rolsuper, rolbypassrls FROM pg_roles
            WHERE rolname = 'staffdeck_runtime'
        """).fetchone() == (False, False)

    with _connection(port, dbname, "staffdeck_runtime") as runtime:
        assert runtime.execute("SELECT count(*) FROM public.tiktok_creator_pool").fetchone()[0] == 0
        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_a', true)")
        runtime.execute("""
            INSERT INTO public.tiktok_creator_pool (
              id, tenant_id, creator_id, identity_id, source_ref,
              sla_rule_version, follow_up_window_hours, created_by_user_id,
              created_at, updated_at
            ) VALUES (
              'pool_a', 'tenant_a', 'creator_a', 'identity_a',
              'social_evidence_aaaaaaaaaaaaaaaa', 'pilot-v1', 48,
              'user_a', now(), now()
            )
        """)
        runtime.execute("""
            INSERT INTO public.tiktok_creator_pool_events (
              id, tenant_id, pool_id, event_type, actor_user_id, created_at
            ) VALUES ('event_a', 'tenant_a', 'pool_a', 'entered', 'user_a', now())
        """)
        runtime.execute("COMMIT")
        assert runtime.execute("SELECT count(*) FROM public.tiktok_creator_pool").fetchone()[0] == 0

        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_b', true)")
        runtime.execute("""
            INSERT INTO public.tiktok_creator_pool (
              id, tenant_id, creator_id, identity_id, source_ref,
              sla_rule_version, follow_up_window_hours, created_by_user_id,
              created_at, updated_at
            ) VALUES (
              'pool_b', 'tenant_b', 'creator_b', 'identity_b',
              'social_evidence_bbbbbbbbbbbbbbbb', 'pilot-v1', 48,
              'user_b', now(), now()
            )
        """)
        runtime.execute("COMMIT")

        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_a', true)")
        assert runtime.execute("SELECT id FROM public.tiktok_creator_pool").fetchall() == [
            ("pool_a",)
        ]
        assert runtime.execute("SELECT id FROM public.tiktok_creator_pool_events").fetchall() == [
            ("event_a",)
        ]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute("UPDATE public.tiktok_creator_pool_events SET reason='changed'")
        runtime.execute("ROLLBACK")

        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_a', true)")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute("""
                INSERT INTO public.tiktok_creator_pool (
                  id, tenant_id, creator_id, identity_id, source_ref,
                  sla_rule_version, follow_up_window_hours, created_by_user_id,
                  created_at, updated_at
                ) VALUES (
                  'cross_tenant', 'tenant_b', 'creator_b', 'identity_b',
                  'social_evidence_bbbbbbbbbbbbbbbb', 'pilot-v1', 48,
                  'user_b', now(), now()
                )
            """)
        runtime.execute("ROLLBACK")

    with _connection(port, dbname, "postgres") as administrator:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            administrator.execute("""
                INSERT INTO public.tiktok_creator_pool_events (
                  id, tenant_id, pool_id, event_type, actor_user_id,
                  previous_owner_user_id, created_at
                ) VALUES (
                  'wrong_owner', 'tenant_a', 'pool_a', 'claimed',
                  'user_a', 'user_b', now()
                )
            """)
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            administrator.execute("""
                UPDATE public.tiktok_creator_pool_events SET reason='changed'
                WHERE id='event_a'
            """)

    with _connection(port, dbname, "staffdeck_runtime") as runtime:
        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_a', true)")
        runtime.execute("""
            INSERT INTO public.tiktok_creator_pool_events (
              id, tenant_id, pool_id, event_type, actor_user_id,
              previous_owner_user_id, new_owner_user_id, reason, created_at
            ) VALUES (
              'transfer_probe', 'tenant_a', 'pool_a', 'transferred',
              'user_a', 'user_a', 'user_a', 'staff_change', now()
            )
        """)
        runtime.execute("ROLLBACK")

    with _connection(port, dbname, "staffdeck_migrator") as migrator:
        migrator.execute(TRANSFER_DOWN.read_text(encoding="utf-8"))
        migrator.execute(DOWN.read_text(encoding="utf-8"))
        assert migrator.execute("SELECT to_regclass('public.tiktok_creator_pool')").fetchone()[0] is None
        assert migrator.execute("""
            SELECT count(*) FROM public.staffdeck_schema_migrations
            WHERE migration_id='20260923_tiktok_p3b2_creator_pool_v1'
        """).fetchone()[0] == 0
