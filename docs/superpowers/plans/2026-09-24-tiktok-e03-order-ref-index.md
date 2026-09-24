# TikTok E03 Order Reference Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make unapproved commission-proposal overlap lookup indexable and verify concurrent-save reread behavior without adding financial authority.

**Architecture:** Retain immutable JSON snapshots; add a tenant-scoped relation of derived order references, maintained by a database trigger and queried through a B-tree equality index. Backfill within one migration transaction with temporary migrator RLS policies that are dropped before commit. SQLite retains a compatible scan fallback for unit tests.

**Tech Stack:** Python/SQLModel/SQLAlchemy, PostgreSQL 16, pytest.

**Spec:** `docs/superpowers/specs/2026-09-24-tiktok-e03-order-ref-index.md`

## Global constraints

- No approved D6 rule, order reservation, finance submission, freeze, payment, or external write.
- Preserve tenant checks, forced RLS, immutable proposal snapshots, and existing API response shape.
- Keep main's unrelated dirty paths and existing stashes intact; merge linearly after review and passing checks.

## Review focus

- An exact `order:` reference must not match a prefix or neighboring reference.
- A second tenant's identical reference must never enter the result.
- Concurrent commits may both succeed; reread must disclose both, without claiming exclusivity.
- A zero-proposal entry should avoid a tenant-wide scan.
- Rollback must remove only derived lookup data and its trigger, never proposal snapshots.

---

### Task 1: Indexed overlap lookup

**Files:** `src/backend/app/db/models.py`, `src/backend/app/tiktok/commission_drafts.py`, `src/tests/backend/test_tiktok_commission_drafts.py`.

- [x] Write failing functional and PostgreSQL query-shape tests for batched relational equality lookup, empty target, and isolation; run RED.
- [x] Implement candidate selection and one-pass overlap map; run GREEN and existing proposal/API tests.

### Task 2: Migration and concurrent PostgreSQL acceptance

**Files:** `src/backend/migrations/20260924_tiktok_e03_unapproved_drafts_v2_order_index.sql`, corresponding `.down.sql`, migration and isolated PostgreSQL tests.

- [x] Write failing migration and live tests for existing-row backfill, trigger-only writes, final RLS/grants, two committed overlapping transactions, B-tree use, and safe derived-data rollback; run RED.
- [x] Add minimal forward/down migrations and run GREEN on the disposable PostgreSQL cluster.

### Task 3: Documentation, review, integration

**Files:** `docs/README.md`, `docs/PROJECT_MEMORY.md`, `docs/SESSION_HANDOFF.md`, `docs/DEVELOPMENT_LOG.md`, this plan, ADR 0007.

- [x] Record design decision, changed files, evidence and remaining gates in indexed docs.
- [x] Run TikTok backend matrix, frontend suite/typecheck/build/i18n/config, Ruff, test layout and diff checks.
- [ ] Obtain whole-branch review, resolve important findings, and fast-forward into starting `main` while preserving its dirty paths; leave push and branch deletion untouched.
