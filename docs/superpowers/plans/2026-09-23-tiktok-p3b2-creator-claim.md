# TikTok P3-B2 Creator Claim Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver an internal, auditable creator claim and supervisor-approved reflow loop without external sending.

**Architecture:** Reuse canonical social creator and verified platform identity records. Keep mutable current assignment in one tenant-scoped pool row and transition evidence in an append-only event table. Use compare-and-swap revisions for concurrent actions and explicit role/tenant checks at the service boundary.

**Tech Stack:** FastAPI, SQLModel, PostgreSQL migration/RLS, React/TypeScript, pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-23-tiktok-p3b2-creator-claim-design.md`

## Global constraints

- No external TikTok calls, creator messages, platform writes, commission payments, or contact storage.
- An explicit supervisor-owned SLA version/window is required; no global deadline is inferred.
- All reads and writes are tenant scoped. PostgreSQL retains forced RLS as a separate boundary.
- Keep executable tests under `src/tests/` and append evidence to the canonical development log.

## Review focus

- Two BDs claim the same revision: exactly one wins and the loser sees a refreshable conflict.
- A claimed creator belongs to another tenant: return 404 without revealing the record.
- An unverified or non-TikTok identity: reject intake even if the creator profile exists.
- A page view or empty evidence reference: cannot extend the deadline.
- A supervisor reflow approval racing an owner follow-up: only one revision transition wins.

### Task 1: Persistence and migration

**Files:** `src/backend/app/db/models.py`, `src/backend/migrations/20260923_tiktok_p3b2_creator_pool_v1.sql`, matching down migration, `src/tests/backend/test_postgres_tiktok_p3b2_creator_pool_migration.py`.

- [x] Write a static migration test for tenant composite references, unique `(tenant_id, creator_id)`, forced RLS, minimum grants and append-only event trigger; run it to confirm red.
- [x] Add pool and event SQLModel classes and forward/down SQL migration; rerun the static test and Ruff.

### Task 2: Claim service

**Files:** `src/backend/app/tiktok/creator_pool.py`, `src/tests/backend/test_tiktok_creator_pool.py`.

- [x] Write red tests for intake, tenant/identity validation, concurrent/stale claim, owner-only effective action, overdue proposal and supervised reflow.
- [x] Implement the smallest service that passes those tests using server time, explicit rule versions and revision compare-and-swap; run the focused tests.

### Task 3: API and role grants

**Files:** `src/backend/app/api/tiktok.py`, `src/backend/app/security/casbin_policy.csv`, `src/tests/backend/test_tiktok_creator_pool_api.py`.

- [x] Add a failing BD claim route/default-grant test; cover supervisor intake/reflow, unrelated access and ownership at the service boundary.
- [x] Add narrow API routes and Casbin grants; run focused tests and the TikTok external-write freeze gate.

### Task 4: Console and handoff

**Files:** `src/frontend-enterprise/src/pages/tiktok/TikTokCreatorPoolPanel.tsx`, `src/frontend-enterprise/src/pages/TikTokBusinessUnitPage.tsx`, `src/frontend-enterprise/src/i18n/en.json`, `src/tests/frontend/TikTokCreatorPoolPanel.test.tsx`, `docs/DEVELOPMENT_LOG.md`, `docs/SESSION_HANDOFF.md`.

- [x] Write a failing panel test for role-gated controls, creator selection and conflict refresh.
- [x] Add the internal pool tab and panel, then run Vitest, typecheck, i18n, config and build.
- [x] Run the TikTok backend matrix, migration/static guard, Ruff and test-layout check; document real browser/PostgreSQL gates separately and commit the branch.
