# Joukir Main Repository Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `E:\develop\数字员工\joukir` as the independent, history-preserving main repository with a flat product layout, one categorized root test tree, GitHub Flow, durable project memory, and verified access to the restored local services.

**Architecture:** Clone the complete handover Git object database, retain the immutable handover commit through a tag, and express all layout changes as ordinary rename commits. Keep source, tests, deployment assets, and governance in Git while local credentials, databases, dependencies, processes, logs, and build output remain ignored runtime state.

**Tech Stack:** Git, PowerShell, Python 3.11, uv, FastAPI, pytest, Ruff, Node.js 24, npm, React 18, TypeScript, Vite/Vitest, Docker Compose, PostgreSQL 16, Casdoor 3.161.1, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-11-joukir-main-repository-migration-design.md`

## Global Constraints

- Preserve the 44 handover commits and their commit IDs; do not rewrite history.
- Do not delete or modify `E:\develop\数字员工\joukir-enterprise`, its restored databases, its encrypted backup, or its Docker volume during migration.
- Do not print or commit passwords, tokens, API keys, cookies, private keys, full database URLs, or raw authorization payloads.
- Keep all executable repository test sources under root `tests/`, classified as backend, frontend, integration, or packaging.
- Keep `skills/*/evals/cases.json` co-located with each published skill because those files are runtime evaluation assets.
- Rebuild `.venv`, `node_modules`, and `dist`; do not copy generated dependencies, caches, logs, PIDs, locks, or SQLite files.
- Use `main` as the final branch and preserve the old directory until the user removes it manually.
- Leave GitHub remote configuration empty until a real repository URL is supplied.

---

### Task 1: Create an independent history-preserving repository

**Files:**
- Create: `E:\develop\数字员工\joukir\.git\`
- Create: `E:\develop\数字员工\joukir\docs\migration\source-index-before-layout.tsv`

**Interfaces:**
- Consumes: the committed implementation plan on top of design commit `9cc0327` and immutable handover commit `e0cb8df042b3a5f856c60b45cf7e9c2bafbc23b5`.
- Produces: an independent working repository on `chore/main-repository-migration`, with `main` and tag `handover-20260909`.

- [ ] **Step 1: Verify the target is absent and record the source state**

Run read-only checks for the resolved source and target paths, current branch, HEAD, commit count, refs, worktree status, and the two known untracked restoration reports. Abort if `E:\develop\数字员工\joukir` already exists.

- [ ] **Step 2: Clone all Git objects without local alternates**

```powershell
git clone --no-local 'E:\develop\数字员工\joukir-enterprise' 'E:\develop\数字员工\joukir'
```

Verify `.git\objects\info\alternates` is absent and `git fsck --full` exits 0.

- [ ] **Step 3: Establish branches and handover tag**

```powershell
git branch -m main
git tag -a handover-20260909 e0cb8df042b3a5f856c60b45cf7e9c2bafbc23b5 -m "Joukir handover baseline 2026-09-09"
git switch -c chore/main-repository-migration
git remote remove origin
```

Verify `main` points to `9cc0327`, the tag points to `e0cb8df`, and no remote remains.

- [ ] **Step 4: Capture the migration input mapping**

Generate `docs/migration/source-index-before-layout.tsv` from `git ls-files -s`, recording original path and blob ID. Record the exact handover paths of the two untracked root restoration reports and the ignored append-only development log for direct inclusion in Task 2. Do not copy environment files in this step.

### Task 2: Promote the complete product source to repository root

**Files:**
- Move: `source/backend/` → `backend/`
- Move: `source/frontend-enterprise/` → `frontend-enterprise/`
- Move: `source/packaging/` → `packaging/`
- Move: `source/scripts/` → `scripts/`
- Move: `source/skills/` → `skills/`
- Move: `source/.agent/` → `.agent/`
- Merge: `source/.github/` → `.github/`
- Merge: `source/docs/` → `docs/`
- Move: remaining tracked `source/*` root files → repository root
- Modify: `.gitignore`
- Create: `docs/migration/layout-mapping-report.json`

**Interfaces:**
- Consumes: Task 1 source-index mapping.
- Produces: the flat root layout with every original tracked blob mapped and no `source/` directory.

- [ ] **Step 1: Check every destination for collisions**

Build the expected mapping by stripping the leading `source/` component from source paths and keeping already-rooted paths unchanged. Compare destinations case-insensitively because Windows is case-insensitive. Abort and report every collision before moving any file.

- [ ] **Step 2: Move non-conflicting source directories with Git**

Use `git mv` for `backend`, `frontend-enterprise`, `packaging`, `scripts`, `skills`, `.agent`, `AGENTS.md`, `LICENSE`, both READMEs, the design documents, `development-feishu-channel.md`, `skills.zip`, and the source-level package lock.

- [ ] **Step 3: Merge GitHub and documentation trees**

Move the three `source/.github` files into the existing root `.github` tree. Move all tracked `source/docs` files into root `docs`, then copy the preserved `DEVELOPMENT_LOG.md`, `DATABASE_RESTORE_20260909.md`, and `LOCAL_STARTUP_20260909.md` into root `docs`. Remove the now-empty `source/` directory.

- [ ] **Step 4: Fix ignore rules without weakening secret protection**

Delete only the `/docs/` ignore entry. Keep `.env`, `.env.*` with `!.env.example`, private-key extensions, virtual environments, dependencies, build output, `.dev`, databases, logs, and cache exclusions.

- [ ] **Step 5: Verify blob preservation**

For every Task 1 tracked path, resolve its new path and compare `git hash-object` to the original blob ID. Record totals, missing paths, expected changed paths, and unexpected mismatches in `docs/migration/layout-mapping-report.json`. Expected content changes are limited to `.gitignore`, CI, AGENTS, test configuration, documentation, and test import rewrites performed in later tasks.

- [ ] **Step 6: Commit the root layout**

```powershell
git add -A
git commit -m "refactor: promote product source to repository root"
```

The commit must contain renames and documentation carry-over only; no `.env`, dependencies, database, logs, or build output.

### Task 3: Centralize the backend test suite

**Files:**
- Move: `backend/tests/*.py` → `tests/backend/*.py`
- Create: `pytest.ini`
- Modify: `backend/pyproject.toml`
- Create: `tests/README.md`

**Interfaces:**
- Consumes: editable backend package from `backend/`.
- Produces: root command `backend/.venv/Scripts/python.exe -m pytest -c pytest.ini tests/backend` and 190 tracked backend test modules under `tests/backend`.

- [ ] **Step 1: Capture backend test count and path-sensitive references**

Record all 190 `backend/tests/test_*.py` paths. Search their contents for `__file__`, `parents[...]`, literal `backend/tests`, fixture paths, and repository-root assumptions. List each required path update before moving.

- [ ] **Step 2: Move all backend tests using Git**

```powershell
New-Item -ItemType Directory -Path tests -Force
git mv backend\tests tests\backend
```

Move any tracked fixtures or subdirectories with the same Git rename semantics.

- [ ] **Step 3: Configure root pytest discovery**

Create `pytest.ini` with `testpaths = tests/backend`, and remove the obsolete `backend/tests` test path from `backend/pyproject.toml`. Update only path-sensitive test code identified in Step 1.

- [ ] **Step 4: Verify collection before running the suite**

```powershell
backend\.venv\Scripts\python.exe -m pytest -c pytest.ini tests\backend --collect-only -q
```

Compare collected test count to the same command run in the handover directory. Resolve only migration-caused collection differences.

### Task 4: Centralize the frontend test suite

**Files:**
- Move: `frontend-enterprise/src/**/*.test.ts` → `tests/frontend/**/*.test.ts`
- Move: `frontend-enterprise/src/**/*.test.tsx` → `tests/frontend/**/*.test.tsx`
- Modify: `frontend-enterprise/vite.config.ts`
- Modify: `frontend-enterprise/tsconfig.json`
- Modify: `frontend-enterprise/package.json`
- Modify: frontend test imports under `tests/frontend/`
- Create: `tests/frontend/tsconfig.json`

**Interfaces:**
- Consumes: production modules through the existing `@/` alias mapped to `frontend-enterprise/src`.
- Produces: 64 tracked frontend test files in `tests/frontend`, executable by `npm --prefix frontend-enterprise test`.

- [ ] **Step 1: Build an exact frontend test/import map**

For each of the 64 tests, map its path relative to `frontend-enterprise/src` to the same relative path below `tests/frontend`. Parse relative module specifiers in static imports, dynamic imports, `vi.mock`, and re-exports. Resolve each specifier against the original source tree and distinguish production modules from other moved test helpers.

- [ ] **Step 2: Move the frontend tests with Git**

Create the mirrored destination directories and run `git mv` for every test. Preserve basename and domain grouping such as `components`, `lib`, `pages`, `pages/chat`, and `pages/dashboard`.

- [ ] **Step 3: Rewrite imports mechanically and deterministically**

Convert relative references to production modules into `@/` specifiers followed by the resolved path relative to `frontend-enterprise/src`. Keep relative references between files that both moved into `tests/frontend`. Fail the rewrite if a relative specifier cannot resolve uniquely; do not guess.

- [ ] **Step 4: Configure Vitest for the external test root**

Set Vitest include paths to `../tests/frontend/**/*.test.ts` and `../tests/frontend/**/*.test.tsx`, retain `frontend-enterprise/src/test/setup.ts`, preserve jsdom URL, and allow the repository test directory through Vite file-system access. Create a test-specific TypeScript configuration extending the production settings and add `test:typecheck` to `frontend-enterprise/package.json`, so moved tests are type-checked against the existing source alias without changing production build output.

- [ ] **Step 5: Verify frontend discovery and type resolution**

```powershell
npm --prefix frontend-enterprise test -- --reporter=verbose
npm --prefix frontend-enterprise run test:typecheck
npm --prefix frontend-enterprise run build
```

The test file count must remain 64 and every failure must be compared with the handover source run before code is changed.

### Task 5: Centralize integration and packaging tests

**Files:**
- Move: `backend/scripts/run_designkit_e2e.py` → `tests/integration/run_designkit_e2e.py`
- Move: `backend/scripts/run_tiktok_mock_sop_replay.py` → `tests/integration/run_tiktok_mock_sop_replay.py`
- Move: `packaging/_docker_test_linux.sh` → `tests/packaging/docker_test_linux.sh`
- Move: `packaging/smoke_macos_app.sh` → `tests/packaging/smoke_macos_app.sh`
- Move: `packaging/smoke_sandbox_bundle.py` → `tests/packaging/smoke_sandbox_bundle.py`
- Move: `packaging/smoke_sandbox_runtime.py` → `tests/packaging/smoke_sandbox_runtime.py`
- Modify: `packaging/build_linux.sh`
- Modify: `packaging/build_macos.sh`
- Modify: `packaging/build_windows.ps1`
- Modify: documentation that invokes moved runners

**Interfaces:**
- Consumes: backend modules, packaging output paths, and explicit command-line arguments.
- Produces: categorized integration and platform smoke commands rooted under `tests/`.

- [ ] **Step 1: Move the six identified runners**

Use `git mv`, keeping the two integration runner basenames and removing the leading underscore from the Docker test filename.

- [ ] **Step 2: Update every tracked caller and usage string**

Use `git grep` for every old path before and after edits. Update build scripts, runbooks, PRD command examples, module usage strings, and test references. The final old-path grep must return zero matches except historical migration documents that explicitly describe the old location.

- [ ] **Step 3: Run cross-platform-safe checks**

Compile both Python runner groups, execute the TikTok mock replay with external writes disabled, and parse the PowerShell build script. Validate Bash test and build scripts with the available shell if present; otherwise record the exact Linux/macOS checks delegated to GitHub Actions.

- [ ] **Step 4: Enforce the root test boundary**

Add a repository check script under `tests/` that reads `git ls-files` and exits nonzero if executable test naming patterns exist outside `tests/`. It must explicitly allow `skills/*/evals/cases.json` and must ignore generated/untracked directories by using the Git index as its source.

- [ ] **Step 5: Commit the categorized test tree**

```powershell
git add -A
git commit -m "test: centralize repository test suites"
```

### Task 6: Establish GitHub Flow and durable project memory

**Files:**
- Modify: `.github/workflows/ci.yml`
- Preserve: `.github/workflows/codeql.yml`
- Preserve and path-check: `.github/workflows/release.yml`
- Preserve: `.github/dependabot.yml`
- Create: `.github/pull_request_template.md`
- Modify: `AGENTS.md`
- Create: `CONTRIBUTING.md`
- Create: `docs/README.md`
- Create: `docs/PROJECT_MEMORY.md`
- Create: `docs/SESSION_HANDOFF.md`
- Create: `docs/adr/README.md`
- Create: `docs/adr/0001-main-repository-layout.md`
- Create: `docs/agents/issue-tracker.md`
- Create: `docs/agents/triage-labels.md`
- Create: `docs/agents/domain.md`
- Modify: `README.md`
- Modify: `README.zh.md`

**Interfaces:**
- Consumes: final root and test paths from Tasks 2–5.
- Produces: self-documenting GitHub Flow and the memory files every future agent/session must read and update.

- [ ] **Step 1: Update GitHub paths and test commands**

Change CI working directories and dependency caches from `source/backend` and `source/frontend-enterprise` to `backend` and `frontend-enterprise`. Add frontend `config:check`, `i18n:check`, and the root test-layout check. Point backend regression paths to `tests/backend`. Search all `.github` files for obsolete `source/` and moved test paths.

- [ ] **Step 2: Add the PR contract**

Create a PR template with required sections for problem/behavior, implementation, risks, validation, affected routes/roles, schema or migration impact, and docs/ADR. State that credentials and external authorization payloads must never be pasted into a PR.

- [ ] **Step 3: Document GitHub Flow**

`CONTRIBUTING.md` defines `main`, short-lived branch prefixes, Conventional Commits, PR review, CI requirements, squash or linear merge, release tags, and the exact local verification commands. It states that remote creation and branch protection occur only after a real GitHub URL is provided.

- [ ] **Step 4: Create durable memory layers**

Write the stable architecture and runtime boundary to `PROJECT_MEMORY.md`; current verified state and next actions to `SESSION_HANDOFF.md`; decision format and rules to `docs/adr/README.md`; the history-preserving flat-root/test-root decision to ADR 0001. Build `docs/README.md` as an index of PRDs, runbooks, handover/restoration reports, specs/plans, memory, log, and ADRs. Create the three concise agent-domain documents already referenced by `AGENTS.md`, preserving the existing decisions that this repository does not use agent-managed issues or triage labels.

- [ ] **Step 5: Make memory mandatory in AGENTS**

Update `AGENTS.md` so each development session reads `PROJECT_MEMORY.md` and `SESSION_HANDOFF.md` first, appends `DEVELOPMENT_LOG.md` before and after work, updates the handoff before ending unfinished work, and writes an ADR for lasting architecture decisions. Retain all existing coding, testing, security, and issue-tracker rules, correcting only paths made stale by the migration.

- [ ] **Step 6: Update public READMEs for the new root**

Correct only repository structure, test commands, PostgreSQL/Casdoor local-development pointers, and the new contribution/memory links. Preserve product descriptions and functional documentation.

- [ ] **Step 7: Commit governance and memory**

```powershell
git add -A
git commit -m "chore: establish GitHub workflow and project memory"
```

### Task 7: Rebuild dependencies and inject local ignored configuration

**Files:**
- Create ignored: `backend/.venv/`
- Create ignored: `backend/.env`
- Create ignored: `frontend-enterprise/node_modules/`
- Create ignored: `frontend-enterprise/.env.local`
- Create ignored: `frontend-enterprise/dist/`

**Interfaces:**
- Consumes: lock files and local configuration from the verified handover environment.
- Produces: a runnable new checkout connected to `joukir-restored-20260909` without tracked secrets.

- [ ] **Step 1: Install locked backend and frontend dependencies**

```powershell
uv sync --project backend --locked --extra dev
npm --prefix frontend-enterprise ci
```

If network access is unavailable, use existing package caches; do not copy the old virtual environment or node_modules.

- [ ] **Step 2: Copy ignored local configuration securely**

Copy `joukir-enterprise\source\backend\.env` and `joukir-enterprise\source\frontend-enterprise\.env.local` without displaying their contents. Replace only old repository Python/venv absolute paths with `E:\develop\数字员工\joukir\backend\.venv`; keep database, OIDC, and disabled-execution settings intact.

- [ ] **Step 3: Restrict and verify ACLs**

Disable inheritance on the copied configuration and allow only current Administrator and SYSTEM. Enumerate ACL principals without printing file content. Verify both files remain ignored and absent from `git status`.

### Task 8: Run migration and functional verification

**Files:**
- Create: `docs/migration/VERIFICATION_20260911.md`
- Update: `docs/DEVELOPMENT_LOG.md`
- Update: `docs/SESSION_HANDOFF.md`

**Interfaces:**
- Consumes: fully migrated source, tests, dependencies, and ignored local configuration.
- Produces: fresh evidence for source completeness, tests, builds, database safety, and application startup.

- [ ] **Step 1: Verify Git and source completeness**

Run `git fsck --full`, verify no alternates/remotes, inspect branch/tag/commit counts, run the test-layout guard, and finalize the blob/path mapping report. Search tracked files for old absolute source paths, private-key headers, and common credential assignments without printing matched secret values.

- [ ] **Step 2: Run backend gates**

```powershell
backend\.venv\Scripts\python.exe -m compileall -q backend\app
backend\.venv\Scripts\python.exe -m ruff check backend\app\api\tiktok.py backend\app\tiktok\connector.py backend\app\tiktok\official.py backend\app\tiktok\release_evidence.py backend\app\tiktok\release_gate.py backend\app\tiktok\schema.py backend\app\tiktok\service.py backend\app\tiktok\shadow.py tests\backend\test_tiktok_connector_authorization.py tests\backend\test_tiktok_live_write_release_gate.py tests\backend\test_tiktok_release_evidence.py tests\backend\test_tiktok_shadow.py
backend\.venv\Scripts\python.exe -m pytest -c pytest.ini tests\backend
```

Save total passed, failed, skipped, duration, and failed test node IDs. If failures occur, run the equivalent handover command and compare; fix only migration-caused failures in this migration.

- [ ] **Step 3: Run frontend gates**

```powershell
npm --prefix frontend-enterprise run config:check
npm --prefix frontend-enterprise run i18n:check
npm --prefix frontend-enterprise run test:typecheck
npm --prefix frontend-enterprise test
npm --prefix frontend-enterprise run build
```

Require 64 discovered files, 271 baseline tests or a documented updated count caused only by test discovery configuration, and build exit 0.

- [ ] **Step 4: Run database production gate**

Load the ignored database URL internally and call `backend/scripts/verify_postgres_production_gate.py` without printing the URL. Require `ok=true`, no missing tables/RLS/roles, and no BYPASSRLS role.

- [ ] **Step 5: Cut over the Web process**

Identify the old Web process by executable path and exact `uvicorn single_port_app:app --port 5173` command. Stop only that process tree, leave Docker and all unrelated processes untouched, then start the same command from `joukir\backend` with `ULTRARAG_DATA_DIR=E:\develop\数字员工\joukir-runtime\data`. Store the new PID in ignored `.dev/local-web.pid` and logs under `joukir-runtime/logs`.

- [ ] **Step 6: Verify live behavior**

Require HTTP 200 and expected fields from `/api/health`, `/workspace/gallery`, `/api/auth/oidc/config`, and Casdoor `/api/health`. Use a browser to confirm the application loads and “企业 SSO 登录” reaches the restored Casdoor password page using PKCE. Do not enter or expose user credentials.

- [ ] **Step 7: Write verification evidence**

Document exact commands, exit codes, counts, migration baseline comparisons, current process/container status, known external-service limits, and Git status in `VERIFICATION_20260911.md`. Append the development log and refresh session handoff without credentials.

- [ ] **Step 8: Commit evidence and fast-forward main**

```powershell
git add docs
git commit -m "docs: record main repository migration verification"
git switch main
git merge --ff-only chore/main-repository-migration
```

Run the final verification commands again after the branch switch. Leave the feature branch available until a GitHub remote is configured.
