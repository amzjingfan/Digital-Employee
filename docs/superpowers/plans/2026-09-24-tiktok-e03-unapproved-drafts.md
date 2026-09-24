# TikTok E03 Unapproved Drafts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save internal, immutable commission proposals and reveal overlap across saved proposals without creating finance approval or order facts.

**Architecture:** One tenant-scoped append-only snapshot table stores one proposed scope and its source pool revision. A focused domain service reuses existing preflight, performs idempotent save and computes current overlap/staleness checks; API and supervisor UI expose only that service.

**Tech Stack:** FastAPI, SQLModel/SQLAlchemy, explicit PostgreSQL migration with forced RLS, React/TypeScript, pytest and Vitest.

**Spec:** `docs/superpowers/specs/2026-09-24-tiktok-e03-unapproved-drafts.md`

## Global Constraints

- Save exactly one scope with at most 100 opaque `order:` references and one opaque `evidence:` reference.
- Never infer approved percentages, order verification, financial approval, exclusive reservation or payment from saved data.
- PostgreSQL is authoritative; retain same-tenant foreign keys, forced RLS, least-privilege grants and append-only draft rows.
- Supervisor and tenant admin only; BD cannot read draft detail even though its general TikTok GET policy is broad.

## Review Focus

- An unknown outcome/retry with the same key must not duplicate a draft; different content under that key must fail.
- Two overlapping drafts, including concurrent saves, must both remain labeled unapproved and display overlap on subsequent reads.
- A responsibility change after save must mark the snapshot stale without rewriting its historical actors.
- A foreign tenant or BD must not see another user's financial proposal details.
- Malformed or personally identifying refs must fail before storage.

---

### Task 1: Persistence and domain service

**Files:** `src/backend/app/db/models.py`, `src/backend/migrations/20260924_tiktok_e03_unapproved_drafts_v1.sql`, corresponding `.down.sql`, `src/backend/app/tiktok/commission_drafts.py`, `src/tests/backend/test_tiktok_commission_drafts.py`, migration tests.

**Interfaces:** Consume `CommissionPreflightRequest`, `preflight_commission_draft`, creator-pool `_manager` and `_entry`; produce `CommissionDraftSaveRequest`, `CommissionDraftRead`, `save_commission_draft` and `list_commission_drafts`.

- [x] Write focused failing tests for save/read, cross-draft overlap, staleness, invalid input, same-tenant access, and idempotency.
- [x] Run those tests and confirm the feature is absent or the expected assertion fails.
- [x] Add the immutable model/migration and smallest service implementation; re-run focused tests.
- [x] Add static migration checks and an isolated PostgreSQL acceptance test for RLS, same-tenant FK, append-only behavior and rollback.

### Task 2: API and supervisor UI

**Files:** `src/backend/app/api/tiktok.py`, `src/backend/app/tiktok/release_gate.py`, `src/tests/backend/test_tiktok_creator_pool_api.py`, `src/frontend-enterprise/src/pages/tiktok/TikTokCommissionPreflight.tsx`, parent panel, `src/tests/frontend/TikTokCreatorPoolPanel.test.tsx`.

**Interfaces:** GET/POST `/commission-drafts/{entry_id}` expose Task 1's read/save types; the existing preflight route is unchanged.

- [x] Write failing permission/API and UI tests for save, history/overlap display and BD concealment.
- [x] Run focused tests and confirm the expected failures.
- [x] Add routes/release-gate surface and UI controls with clear unapproved labeling; re-run focused tests.

### Task 3: Documentation, verification and integration

**Files:** `docs/README.md`, `docs/PROJECT_MEMORY.md`, `docs/SESSION_HANDOFF.md`, `docs/DEVELOPMENT_LOG.md`, this plan, and an ADR if a new lasting boundary is introduced.

- [x] Record the durable boundary and exact tests, limitations and next stage in indexed docs.
- [x] Run TikTok backend tests, frontend tests/typecheck/build/i18n/config, Ruff, test-layout, migration acceptance where available, and diff checks.
- [ ] Review the branch and linearly integrate into the starting target `main`, preserving unrelated dirty changes; leave push and branch deletion untouched.
