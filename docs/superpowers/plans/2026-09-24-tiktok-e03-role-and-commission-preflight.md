# TikTok E03 Role and Commission Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate creator fulfillment and maintenance responsibility and expose a safe commission draft preflight.

**Architecture:** Extend the existing creator pool revision and event boundary. Keep commission preflight stateless until PRD D6 defines approved rules and finance authority.

**Tech Stack:** FastAPI, SQLModel, PostgreSQL, React, TypeScript, pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-24-tiktok-e03-role-and-commission-preflight.md`

## Global Constraints

- Do not infer business percentages or a finance approver.
- Preserve tenant FKs, forced RLS, append-only transition history and least-privilege grants.
- No payments, external messages, or real TikTok writes.

## Review Focus

- Stale assignment revisions must fail without a partial event.
- Cross-tenant or inactive assignees must fail without disclosing another tenant.
- Releasing an Owner must not retain active fulfillment or maintenance assignments.
- Duplicate order scope and non-10,000 splits must produce explicit checks.
- User-supplied rule version must never be mistaken for an approved rule.

### Task 1: Role assignment persistence

- [x] Add failing service/API tests for separate roles, release cleanup, stale revision and tenant permissions.
- [x] Add model and reversible migration fields/events; implement the minimal service route and UI controls.
- [x] Run focused tests and PostgreSQL migration/RLS acceptance.

### Task 2: Commission preflight

- [x] Add failing tests for split, overlap, expiry, permission and unapproved-rule result.
- [x] Implement a supervisor-only stateless API and UI input without a finance submission path.
- [x] Run focused tests, frontend checks, release gate and diff review.

### Task 3: Integration

- [x] Record validation and residual gates in canonical docs.
- [ ] Review the branch, rebase as needed, and linearly merge into the starting target `main` while preserving unrelated changes.
