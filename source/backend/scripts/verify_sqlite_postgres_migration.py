"""Verify a SQLite to PostgreSQL migration and an independent restore.

The script is intentionally read-only. It never changes either database and
expects PostgreSQL URLs for a privileged verification/backup role because
FORCE ROW LEVEL SECURITY can hide rows from a tenant runtime role.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine, make_url

from app.db.models import SQLModel

DEFAULT_MIGRATION_ID = "20260830_sqlite_to_postgresql_v1"
TARGET_ONLY_TABLES = {"oidc_login_states", "user_identities"}


def _env_url(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _sqlite_path(url: str) -> Path:
    database = make_url(url).database
    if not database or database == ":memory:":
        raise RuntimeError("SQLite verification URL must point to a file")
    return Path(database).resolve()


def _sqlite_integrity(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0] if row else "")


def _source_table_names(source: Engine) -> list[str]:
    source_names = set(inspect(source).get_table_names())
    return sorted(
        name
        for name in source_names
        if name in SQLModel.metadata.tables and name not in TARGET_ONLY_TABLES
    )


def _row_counts(engine: Engine, table_names: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        for table_name in table_names:
            table = SQLModel.metadata.tables[table_name]
            counts[table_name] = int(
                connection.execute(select(func.count()).select_from(table)).scalar_one()
            )
    return counts


def _postgres_rls(engine: Engine) -> dict[str, Any]:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("PostgreSQL verification URL is required")
    with engine.connect() as connection:
        tenant_tables = [
            str(row[0])
            for row in connection.execute(
                text(
                    "SELECT DISTINCT table_name "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND column_name = 'tenant_id' "
                    "ORDER BY table_name"
                )
            ).all()
        ]
        if not tenant_tables:
            return {"tenant_table_count": 0, "all_forced": False, "missing": []}
        query = text(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname IN :table_names"
        ).bindparams(bindparam("table_names", expanding=True))
        rows = connection.execute(query, {"table_names": tenant_tables}).all()
    policies = {str(row[0]): (bool(row[1]), bool(row[2])) for row in rows}
    missing = sorted(
        table_name
        for table_name in tenant_tables
        if not policies.get(table_name, (False, False))[0]
        or not policies.get(table_name, (False, False))[1]
    )
    return {
        "tenant_table_count": len(tenant_tables),
        "all_forced": not missing,
        "missing": missing,
    }


def _migration_marker(engine: Engine, migration_id: str) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT migration_id, source_table_count, source_row_count "
                "FROM public.staffdeck_schema_migrations "
                "WHERE migration_id = :migration_id"
            ),
            {"migration_id": migration_id},
        ).mappings().first()
    return dict(row) if row else None


def verify(
    *,
    source_url: str,
    target_url: str,
    restore_url: str,
    backup_path: str,
    migration_id: str = DEFAULT_MIGRATION_ID,
) -> dict[str, Any]:
    source = create_engine(source_url)
    target = create_engine(target_url, pool_pre_ping=True)
    restore = create_engine(restore_url, pool_pre_ping=True)
    try:
        if source.dialect.name != "sqlite":
            raise RuntimeError("source URL must use SQLite")
        if target.dialect.name != "postgresql" or restore.dialect.name != "postgresql":
            raise RuntimeError("target and restore URLs must use PostgreSQL")

        source_path = _sqlite_path(source_url)
        backup = Path(backup_path).expanduser().resolve()
        if not source_path.exists():
            raise RuntimeError(f"SQLite source does not exist: {source_path}")
        if not backup.exists():
            raise RuntimeError(f"SQLite backup does not exist: {backup}")

        source_table_names = _source_table_names(source)
        source_counts = _row_counts(source, source_table_names)
        backup_engine = create_engine(f"sqlite:///{backup.as_posix()}")
        try:
            backup_counts = _row_counts(backup_engine, source_table_names)
        finally:
            backup_engine.dispose()
        target_counts = _row_counts(target, source_table_names)
        restore_counts = _row_counts(restore, source_table_names)

        backup_mismatches = [
            name for name in source_table_names if source_counts[name] != backup_counts[name]
        ]
        target_mismatches = [
            name for name in source_table_names if source_counts[name] != target_counts[name]
        ]
        restore_mismatches = [
            name for name in source_table_names if target_counts[name] != restore_counts[name]
        ]
        target_rls = _postgres_rls(target)
        restore_rls = _postgres_rls(restore)
        target_marker = _migration_marker(target, migration_id)
        restore_marker = _migration_marker(restore, migration_id)
        source_integrity = _sqlite_integrity(source_path)
        backup_integrity = _sqlite_integrity(backup)
        result = {
            "ok": bool(
                source_integrity == "ok"
                and backup_integrity == "ok"
                and not backup_mismatches
                and not target_mismatches
                and not restore_mismatches
                and target_rls["all_forced"]
                and restore_rls["all_forced"]
                and target_marker is not None
                and restore_marker is not None
            ),
            "source": {
                "path": str(source_path),
                "integrity": source_integrity,
                "table_count": len(source_table_names),
                "row_count": sum(source_counts.values()),
            },
            "backup": {
                "path": str(backup),
                "integrity": backup_integrity,
                "row_count": sum(backup_counts.values()),
                "mismatches": backup_mismatches,
            },
            "target": {
                "row_count": sum(target_counts.values()),
                "mismatches": target_mismatches,
                "rls": target_rls,
                "migration_marker": target_marker,
            },
            "restore": {
                "row_count": sum(restore_counts.values()),
                "mismatches": restore_mismatches,
                "rls": restore_rls,
                "migration_marker": restore_marker,
            },
        }
        return result
    finally:
        source.dispose()
        target.dispose()
        restore.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a SQLite/PostgreSQL migration drill")
    parser.add_argument("--source-url-env", default="STAFFDECK_SQLITE_URL")
    parser.add_argument("--target-url-env", default="STAFFDECK_POSTGRES_MIGRATOR_URL")
    parser.add_argument("--restore-url-env", default="STAFFDECK_POSTGRES_RESTORE_URL")
    parser.add_argument("--backup-path", required=True)
    parser.add_argument("--migration-id", default=DEFAULT_MIGRATION_ID)
    args = parser.parse_args()
    result = verify(
        source_url=_env_url(args.source_url_env),
        target_url=_env_url(args.target_url_env),
        restore_url=_env_url(args.restore_url_env),
        backup_path=args.backup_path,
        migration_id=args.migration_id,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, default=str))
    if not result["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
