from __future__ import annotations

import argparse
import os
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Table, create_engine, func, inspect, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.engine import make_url
from sqlmodel import SQLModel

import app.db.models  # noqa: F401

MIGRATION_ID = "20260830_sqlite_to_postgresql_v1"
CONTROL_TABLE = "staffdeck_schema_migrations"
SOURCE_ONLY_TABLES = {"app_data_migrations"}
TARGET_ONLY_TABLES = {"oidc_login_states", "user_identities"}


def _chunks(rows: list[dict[str, object]], size: int) -> Iterator[list[dict[str, object]]]:
    for offset in range(0, len(rows), size):
        yield rows[offset : offset + size]


def _require_url(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _table_count(connection: Connection, table: Table) -> int:
    return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def _prepare_control_table(connection: Connection) -> None:
    connection.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS public.{CONTROL_TABLE} (
              migration_id text PRIMARY KEY,
              applied_at timestamptz NOT NULL,
              source_kind text NOT NULL,
              source_table_count integer NOT NULL,
              source_row_count bigint NOT NULL
            )
            """
        )
    )


def _reset_sequences(connection: Connection) -> None:
    rows = connection.execute(
        text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND column_default LIKE 'nextval(%'
            ORDER BY table_name, ordinal_position
            """
        )
    ).all()
    quote = connection.dialect.identifier_preparer.quote
    for table_name, column_name in rows:
        qualified_table = f"public.{quote(str(table_name))}"
        quoted_column = quote(str(column_name))
        connection.execute(
            text(
                f"""
                SELECT setval(
                  pg_get_serial_sequence(:qualified_table, :column_name),
                  COALESCE((SELECT MAX({quoted_column}) FROM {qualified_table}), 1),
                  EXISTS (SELECT 1 FROM {qualified_table})
                )
                """
            ),
            {
                "qualified_table": f"public.{table_name}",
                "column_name": column_name,
            },
        )


def _source_columns(source_inspector, table_name: str) -> set[str]:
    return {str(column["name"]) for column in source_inspector.get_columns(table_name)}


def _sqlite_database_path(source_url: str) -> Path:
    database = make_url(source_url).database
    if not database or database == ":memory:":
        raise RuntimeError("STAFFDECK_SQLITE_URL must point to a file for a backup")
    return Path(database).resolve()


def backup_sqlite(source_url: str, backup_path: str) -> Path:
    source_path = _sqlite_database_path(source_url)
    destination = Path(backup_path).resolve()
    if source_path == destination:
        raise RuntimeError("SQLite backup path must differ from the source database")
    if not source_path.exists():
        raise RuntimeError(f"SQLite source database does not exist: {source_path}")
    if destination.exists():
        raise RuntimeError(f"Refusing to overwrite existing SQLite backup: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(source_path)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return destination


def migrate(*, apply: bool, batch_size: int, backup_path: str | None = None) -> None:
    source_url = _require_url("STAFFDECK_SQLITE_URL")
    target_url = _require_url("STAFFDECK_POSTGRES_MIGRATOR_URL")
    source_engine = create_engine(source_url)
    target_engine = create_engine(target_url, pool_pre_ping=True)

    if source_engine.dialect.name != "sqlite":
        raise RuntimeError("STAFFDECK_SQLITE_URL must use SQLite")
    if target_engine.dialect.name != "postgresql":
        raise RuntimeError("STAFFDECK_POSTGRES_MIGRATOR_URL must use PostgreSQL")

    source_inspector = inspect(source_engine)
    source_names = set(source_inspector.get_table_names())
    metadata_names = set(SQLModel.metadata.tables)
    unexpected = source_names - metadata_names - SOURCE_ONLY_TABLES
    if unexpected:
        raise RuntimeError(f"Unmodelled source tables: {', '.join(sorted(unexpected))}")

    copy_names = [
        table.name
        for table in SQLModel.metadata.sorted_tables
        if table.name in source_names and table.name not in TARGET_ONLY_TABLES
    ]
    missing_columns: dict[str, list[str]] = {}
    source_counts: dict[str, int] = {}

    with source_engine.connect() as source:
        for table_name in copy_names:
            table = SQLModel.metadata.tables[table_name]
            actual_columns = _source_columns(source_inspector, table_name)
            absent = [column.name for column in table.columns if column.name not in actual_columns]
            if absent:
                missing_columns[table_name] = absent
            source_counts[table_name] = _table_count(source, table)

    source_row_count = sum(source_counts.values())
    print(
        f"Preflight: {len(copy_names)} tables, {source_row_count} rows, "
        f"{len(missing_columns)} tables with target-only columns."
    )
    if not apply:
        print("Dry run complete. Re-run with --apply after stopping StaffDeck and backing up SQLite.")
        return
    if not backup_path:
        raise RuntimeError("--backup-path is required with --apply")
    backup = backup_sqlite(source_url, backup_path)
    print(f"SQLite backup created: {backup}")

    SQLModel.metadata.create_all(target_engine)
    with target_engine.begin() as target:
        _prepare_control_table(target)
        already_applied = target.execute(
            text(f"SELECT 1 FROM public.{CONTROL_TABLE} WHERE migration_id = :migration_id"),
            {"migration_id": MIGRATION_ID},
        ).first()
        if already_applied:
            raise RuntimeError(f"Migration {MIGRATION_ID} is already applied")

        nonempty: list[str] = []
        for table_name in metadata_names:
            table = SQLModel.metadata.tables[table_name]
            if _table_count(target, table):
                nonempty.append(table_name)
        if nonempty:
            raise RuntimeError(
                "Target StaffDeck tables must be empty before migration: "
                + ", ".join(sorted(nonempty))
            )

        with source_engine.connect() as source:
            for table_name in copy_names:
                table = SQLModel.metadata.tables[table_name]
                actual_columns = _source_columns(source_inspector, table_name)
                selected_columns = [column for column in table.columns if column.name in actual_columns]
                rows = [dict(row) for row in source.execute(select(*selected_columns)).mappings()]
                for chunk in _chunks(rows, batch_size):
                    target.execute(table.insert(), chunk)
                copied = _table_count(target, table)
                if copied != source_counts[table_name]:
                    raise RuntimeError(
                        f"Count mismatch for {table_name}: source={source_counts[table_name]}, "
                        f"target={copied}"
                    )
                print(f"Copied {table_name}: {copied}")

        _reset_sequences(target)
        target.execute(
            text(
                f"""
                INSERT INTO public.{CONTROL_TABLE} (
                  migration_id, applied_at, source_kind, source_table_count, source_row_count
                ) VALUES (
                  :migration_id, :applied_at, 'sqlite', :source_table_count, :source_row_count
                )
                """
            ),
            {
                "migration_id": MIGRATION_ID,
                "applied_at": datetime.now(UTC),
                "source_table_count": len(copy_names),
                "source_row_count": source_row_count,
            },
        )

    print(f"Migration {MIGRATION_ID} committed and row counts verified.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate StaffDeck SQLite data to PostgreSQL")
    parser.add_argument("--apply", action="store_true", help="perform the transactional copy")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--backup-path",
        default=None,
        help="new SQLite backup file; required with --apply and never overwritten",
    )
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    migrate(apply=args.apply, batch_size=args.batch_size, backup_path=args.backup_path)


if __name__ == "__main__":
    main()
