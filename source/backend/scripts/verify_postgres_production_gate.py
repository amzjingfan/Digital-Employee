"""Verify PostgreSQL production prerequisites without changing the database."""

from __future__ import annotations

import argparse
import json
import os

from sqlalchemy import bindparam, create_engine, text

REQUIRED_TABLES = {
    "tenants",
    "users",
    "agent_profiles",
    "agent_releases",
    "agent_service_identities",
    "business_resources",
    "external_authorizations",
    "connector_sync_states",
    "tiktok_oauth_states",
    "tiktok_shadow_runs",
}
REQUIRED_ROLES = {"staffdeck_runtime", "staffdeck_worker", "staffdeck_migrator"}


def verify(database_url: str) -> dict[str, object]:
    if not database_url:
        raise RuntimeError("PostgreSQL runtime URL is required")
    engine = create_engine(database_url, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Production database URL must use PostgreSQL")
    with engine.connect() as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
        }
        missing_tables = sorted(REQUIRED_TABLES - tables)
        rls_query = text(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname IN :table_names"
        ).bindparams(bindparam("table_names", expanding=True))
        rls_rows = connection.execute(rls_query, {"table_names": list(REQUIRED_TABLES)}).all()
        rls = {
            str(row[0]): {"enabled": bool(row[1]), "forced": bool(row[2])}
            for row in rls_rows
        }
        missing_rls = sorted(
            table for table in REQUIRED_TABLES if not rls.get(table, {}).get("enabled")
        )
        unforced_rls = sorted(
            table for table in REQUIRED_TABLES if not rls.get(table, {}).get("forced")
        )
        role_query = text(
            "SELECT rolname, rolbypassrls FROM pg_roles WHERE rolname IN :role_names"
        ).bindparams(bindparam("role_names", expanding=True))
        role_rows = connection.execute(role_query, {"role_names": list(REQUIRED_ROLES)}).all()
        roles = {str(row[0]): {"bypass_rls": bool(row[1])} for row in role_rows}
        missing_roles = sorted(REQUIRED_ROLES - set(roles))
        bypass_roles = sorted(role for role, row in roles.items() if row["bypass_rls"])
        return {
            "ok": not (missing_tables or missing_rls or unforced_rls or missing_roles or bypass_roles),
            "missing_tables": missing_tables,
            "missing_rls": missing_rls,
            "unforced_rls": unforced_rls,
            "missing_roles": missing_roles,
            "bypass_rls_roles": bypass_roles,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify StaffDeck PostgreSQL production gate")
    parser.add_argument("--url-env", default="STAFFDECK_POSTGRES_RUNTIME_URL")
    args = parser.parse_args()
    result = verify(os.environ.get(args.url_env, "").strip())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if not result["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
