# `src/` Repository Layout Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Place all executable Joukir project areas under `src/` while preserving supported development and runtime behavior.

**Architecture:** Keep a thin repository root for governance, documentation, CI metadata, and repository-wide configuration. Move each existing executable subtree intact, then update active path consumers and validate the same commands against their `src/` locations.

**Tech Stack:** Python 3.11+, FastAPI, uv, React, TypeScript, Vite, npm, PowerShell, Bash, GitHub Actions

**Spec:** `docs/superpowers/specs/2026-09-17-src-layout-migration-design.md`

## Global Constraints

- Preserve ignored secrets and local runtime configuration without printing or staging them.
- Preserve historical evidence semantics.
- Keep `.dev/` at repository root.
- Do not weaken PostgreSQL, Casdoor, Casbin, RLS, tenant, or credential boundaries.

---

### Task 1: Move executable project areas

**Files:** `backend/`, `deploy/`, `frontend-enterprise/`, `packaging/`, `scripts/`, `skills/`, `tests/` → `src/`

- [ ] Record the clean pre-move branch and ignored configuration state.
- [ ] Create `src/` and move each complete subtree with its ignored local runtime files.
- [ ] Verify every tracked file maps to the corresponding `src/` path and no source subtree remains at root.
- [ ] Verify `src/backend/.env` remains ignored and absent from the Git index.

### Task 2: Repair executable path consumers

**Files:** root configuration, `.github/`, `src/scripts/`, `src/backend/`, `src/deploy/`, `src/packaging/`, `src/tests/`

- [ ] Update Python, shell, PowerShell, CI, release, packaging, deployment, and test configuration paths.
- [ ] Add or adjust layout verification so future executable files cannot drift back to the old root locations.
- [ ] Run compile, layout, migration, and focused test checks; fix path regressions.

### Task 3: Update current documentation and governance

**Files:** `AGENTS.md`, `CONTRIBUTING.md`, `README.md`, `README.zh.md`, `docs/README.md`, `docs/PROJECT_MEMORY.md`, `docs/SESSION_HANDOFF.md`, current runbooks

- [ ] Update current commands, links, tree diagrams, environment paths, and working agreements.
- [ ] Preserve dated historical records as evidence and identify their former layout where needed.
- [ ] Run link/path scans and `git diff --check`.

### Task 4: Prove build and runtime behavior

**Files:** no new product files expected; append evidence to `docs/DEVELOPMENT_LOG.md` and refresh `docs/SESSION_HANDOFF.md`

- [ ] Run backend lint and tests from `src/backend` against `src/tests/backend`.
- [ ] Run frontend unit tests, typecheck, i18n/config checks, and production build from `src/frontend-enterprise`.
- [ ] Start through `src/scripts/dev_up.ps1 --detach`, verify status and `/api/health`, then stop through `src/scripts/dev_down.ps1`.
- [ ] Record results, remaining platform limits, and exact current commands.

### Task 5: Commit and merge

**Files:** all migration changes

- [ ] Review staged files for secrets, generated output, and unintended historical rewrites.
- [ ] Commit the migration with a focused Conventional Commit message.
- [ ] Merge `codex/prd-tiktok-v1-8` into `main` and verify the merged tree and branch status.
