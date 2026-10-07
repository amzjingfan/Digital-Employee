# Repository Guidelines

## Project Structure & Module Organization

Joukir is the inherited product deployment built on StaffDeck. It combines a Python 3.11+ FastAPI service with a React/TypeScript console. All executable project areas live below the root `src/` directory. Backend application code lives in `src/backend/app/`; entry points such as `src/backend/single_port_app.py` support the desktop and single-port runtime. Frontend code is in `src/frontend-enterprise/src/`, with static assets in `src/frontend-enterprise/public/`. All executable repository tests live below `src/tests/`, grouped as `backend`, `frontend`, `integration`, and `packaging`; published skill evaluation data remains under `src/skills/*/evals/`. Put newly generated reports, designs, operations records, and development notes under the matching `docs/` category and index them in `docs/README.md`; reserve the repository root for governance, documentation, CI metadata, and repository-wide configuration. Use `src/scripts/` for development lifecycle tooling, `src/deploy/` for PostgreSQL/Casdoor platform assets, and `src/packaging/` for platform release assets. The supported conversation runtime is Harness v2.

## Build, Test, and Development Commands

- `uv sync --project src/backend --locked --extra dev` installs the locked backend and test dependencies.
- `npm --prefix src/frontend-enterprise ci` installs the locked frontend dependencies.
- `src/scripts/dev_up.sh --detach` builds the frontend and starts the single-port app; use `src/scripts/dev_status.sh` and `src/scripts/dev_down.sh` to inspect or stop it.
- `src/backend/.venv/bin/python -m pytest -c pytest.ini src/tests/backend` runs the backend suite on macOS/Linux/WSL; use `src\backend\.venv\Scripts\python.exe -m pytest -c pytest.ini src\tests\backend` on Windows.
- `src/backend/.venv/bin/python src/tests/check_test_layout.py` enforces the `src/tests` boundary; use the matching Windows virtual-environment path when needed.
- `src/backend/.venv/bin/ruff check src/backend` checks Python style.
- `npm --prefix src/frontend-enterprise test` runs Vitest; `npm --prefix src/frontend-enterprise run test:typecheck` type-checks the frontend suite; `npm --prefix src/frontend-enterprise run build` performs the production TypeScript/Vite build.
- Run `npm --prefix src/frontend-enterprise run i18n:check` and `npm --prefix src/frontend-enterprise run config:check` when changing UI text or Vite environment usage.

## Coding Style & Naming Conventions

Python uses four-space indentation, type hints, `snake_case` functions/modules, and `PascalCase` classes; Ruff targets Python 3.11 with a 100-character line limit. TypeScript is strict and follows the existing two-space, single-quote, semicolon style. Name React components in `PascalCase`, hooks with `use...`, and tests after the unit under test. Prefer the `@/` alias for frontend imports.

## Testing Guidelines

Name Python tests `test_*.py` and frontend tests `*.test.ts(x)`. Put every executable repository test in the matching `src/tests/` category; do not colocate tests with production source. Add focused regression tests for behavior changes, especially permissions, persistence, streaming, and channel routing. No numeric coverage threshold is configured; changed paths should still be exercised. For UI changes, also verify the affected route and user role in a browser.

## Commit & Pull Request Guidelines

Follow the history’s concise Conventional Commit pattern, such as `feat(channels): add binding status` or `fix: reject unsafe avatar URLs`. Keep commits focused. Pull requests should explain intent and risk, link relevant issues, list tests run, and identify routes and roles used for UI validation. Include screenshots for visible changes and preserve unrelated worktree changes.

After a short-lived branch's requested work is complete, its required validation has passed, and any required repository review is satisfied, merge it automatically into the target branch recorded when the work began (default `main`) without asking for separate confirmation. Keep `main` linear by using a squash or rebase merge, never a merge commit. If unrelated worktree changes, unresolved conflicts, failed required checks, missing authority, or worktree restrictions prevent a safe merge, stop and report the exact blocker. Treat pushing the result and deleting the source branch as separate actions that still require explicit user authorization.

## Security & Configuration

Create the ignored `src/backend/.env` only from approved deployment-specific configuration or a secure runtime handoff; this repository does not provide a tracked example file. Never commit secrets or channel credentials. Use strong `APP_SECRET` values and least-privilege external credentials. PostgreSQL is the authoritative current-development database; Casdoor OIDC, Casbin authorization, and forced PostgreSQL RLS form separate security boundaries. Apply schema changes through `src/backend/migrations/`, verify the production database gate, and never weaken tenant context or least-privilege database roles to make a test pass.

## Development Memory and Logging

- At the start of every development session, read `docs/PROJECT_MEMORY.md` and `docs/SESSION_HANDOFF.md` before changing code.
- Before each development step, append the date, objective, scope, and known blockers to `docs/DEVELOPMENT_LOG.md`.
- After each step, append the changed files, validation commands and results, remaining risks, and the next recommended step. Do not rewrite prior entries.
- Before ending unfinished work, refresh `docs/SESSION_HANDOFF.md` with the current branch, verified state, blockers, and exact next actions.
- Keep stable architecture and working agreements in `docs/PROJECT_MEMORY.md`. Record lasting architecture or workflow decisions as ADRs under `docs/adr/`.
- Code comments must be readable to human maintainers. Explain intent, business constraints, security boundaries, or non-obvious trade-offs; do not add comments that merely restate the code.
- Never put passwords, tokens, API secrets, cookies, private keys, full personal data, or raw external authorization payloads in source code, comments, memory, logs, test fixtures, or screenshots.
- A development log records implementation evidence; it does not turn a seed, mock, local approval, or sandbox result into production approval.

## Agent skills

### Issue tracker

Do not create or manage issues for this repository. See `docs/agents/issue-tracker.md`.

### Triage labels

Issue triage labels are not used. See `docs/agents/triage-labels.md`.

### Domain docs

Use the single-context documentation layout. See `docs/agents/domain.md`.
