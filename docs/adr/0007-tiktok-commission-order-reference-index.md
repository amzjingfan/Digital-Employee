# ADR 0007: Index unapproved commission order references under forced RLS

Date: 2026-09-24

Status: Accepted for the P3-B2 internal pilot

## Context

ADR 0006 stored each proposal's opaque order references in an immutable JSON snapshot and detected overlap by scanning every proposal in the tenant. A PostgreSQL GIN expression index on `order_refs_json::jsonb` was tested in an isolated cluster. The index existed and returned correct data, but a runtime-role query under forced RLS did not use it even with sequential scans disabled. PostgreSQL's `jsonb_exists_any` (`?|`) function is not leakproof; [PostgreSQL documents that non-leakproof index operators cannot be moved ahead of RLS checks](https://www.postgresql.org/docs/16/rules-privileges.html). Keeping that index would not solve the runtime lookup cost.

## Decision

Retain the immutable JSON snapshot and add a derived, tenant-scoped `(tenant_id, draft_id, order_ref)` table indexed by `(tenant_id, order_ref, draft_id)`. The database fills rows from each new proposal with an `AFTER INSERT` security-definer trigger. The function has a fixed `pg_catalog` search path; the child table has a same-tenant foreign key, forced RLS, a format check and an update/delete guard. The runtime role can SELECT but cannot write child rows. The trigger owner can insert only where the row tenant matches the current transaction's tenant context.

The forward migration locks parent inserts, temporarily permits the migration role to read parent rows and insert derived rows, backfills all existing snapshots, and removes both temporary policies before committing. The down migration removes only the trigger, function and derived table, leaving all proposal snapshots intact. Invalid or duplicate historical references make the migration fail as a whole; they are not silently skipped.

The service first loads proposals for the requested creator, then uses a batched equality lookup on the child index to build overlap details. SQLite tests use the existing JSON scan because SQLModel test tables have no PostgreSQL trigger. No proposal reserves an order or gains priority. The table is an index of unverified references, not an authorized order ledger or financial allocation.

## Consequences and evidence

The migration holds a write-blocking parent lock during backfill; deployment requires a production database gate and an appropriate maintenance window. Isolated PostgreSQL 16 acceptance checks the legacy backfill, final grants and RLS policies, trigger-only writes, two concurrent same-reference commits, cross-tenant isolation, an index-backed runtime plan, and derived-data rollback. The PostgreSQL service query is exercised through SQLModel as well as raw SQL. D6 rules, an authorized order source, exclusivity, finance review and frozen allocation remain separate work.
