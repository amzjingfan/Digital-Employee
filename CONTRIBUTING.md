# Contributing to Joukir

Joukir uses GitHub Flow. The local repository is ready for that workflow, but it intentionally has no remote. Configure a remote and protect `main` only after a maintainer supplies the real GitHub repository URL; do not create a placeholder remote or infer an organization, visibility, or repository name.

## Start a change

1. Read `docs/PROJECT_MEMORY.md` and `docs/SESSION_HANDOFF.md`.
2. Append the objective, scope, and known blockers to `docs/DEVELOPMENT_LOG.md`.
3. Update local `main`, then create a short-lived branch named `feature/<topic>`, `fix/<topic>`, `docs/<topic>`, or `chore/<topic>`.
4. Keep each commit focused and use Conventional Commits, for example `feat(channels): add binding status`, `fix: reject unsafe avatar URLs`, or `docs: clarify database recovery`.
5. Put all executable tests below `src/tests/` in the matching `backend`, `frontend`, `integration`, or `packaging` category. Keep `src/skills/*/evals/cases.json` with its published skill because it is evaluation data rather than a repository test executable.

## Local validation from the repository root

Install the locked dependencies:

```powershell
uv sync --project src/backend --locked --extra dev
npm --prefix src/frontend-enterprise ci
```

Run the backend checks represented in pull request CI. `uv --directory src/backend` gives Ruff and pytest the same working directory on Windows, macOS, Linux, and WSL:

```powershell
uv run --directory src/backend --locked python ../tests/check_test_layout.py
uv run --directory src/backend --locked python -m compileall -q app
uv run --directory src/backend --locked ruff check app/api/tiktok.py app/tiktok/connector.py app/tiktok/official.py app/tiktok/release_evidence.py app/tiktok/release_gate.py app/tiktok/schema.py app/tiktok/service.py app/tiktok/shadow.py ../tests/backend/test_tiktok_connector_authorization.py ../tests/backend/test_tiktok_live_write_release_gate.py ../tests/backend/test_tiktok_release_evidence.py ../tests/backend/test_tiktok_shadow.py
uv run --directory src/backend --locked pytest -c ../../pytest.ini -q ../tests/backend/test_tiktok_connector_authorization.py ../tests/backend/test_tiktok_live_write_release_gate.py ../tests/backend/test_tiktok_release_evidence.py ../tests/backend/test_tiktok_shadow.py ../tests/backend/test_tiktok_release_gate.py ../tests/backend/test_tiktok_official_oauth.py ../tests/backend/test_tiktok_mock_replay_tasks.py ../tests/backend/test_tiktok_mock_replay_execution.py ../tests/backend/test_tiktok_mock_replay.py ../tests/backend/test_tiktok_mock_exception_matrix.py ../tests/backend/test_tiktok_m2m_verification.py ../tests/backend/test_tiktok_business_unit.py
```

Run the complete backend suite when the affected behavior extends beyond the focused CI set:

```powershell
uv run --project src/backend --locked pytest -c pytest.ini src/tests/backend
```

Run every frontend gate:

```powershell
npm --prefix src/frontend-enterprise run config:check
npm --prefix src/frontend-enterprise run i18n:check
npm --prefix src/frontend-enterprise run test:typecheck
npm --prefix src/frontend-enterprise test
npm --prefix src/frontend-enterprise run build
```

Use the commands in `src/tests/README.md` for integration and packaging checks. Run platform-specific packaging checks on their target operating system. After editing files, run `git diff --check` and confirm ignored configuration, dependency trees, build output, databases, logs, and PID files are not staged.

## Pull requests and review

Open a pull request into `main` and complete `.github/pull_request_template.md`. A review must be able to connect the triggering problem to the resulting behavior and assess:

- affected routes, UI entry points, roles, tenant scopes, and browser checks;
- test evidence and any known coverage gap;
- schema migrations, ownership, Casbin rules, PostgreSQL RLS, data backfill, and rollback;
- external side effects, authorization flows, retries, release gates, audit evidence, and recovery;
- operational risk, deployment steps, and rollback;
- documentation, project memory, session handoff, and any lasting decision recorded as an ADR.

Pull requests must pass the repository CI and CodeQL checks and receive maintainer review. Keep `main` linear by using a squash merge or rebase merge. Do not create merge commits on `main`, force-push `main`, or bypass required checks. Once a real GitHub repository exists, maintainers should protect `main` with pull request, review, CI, CodeQL, and no-force-push rules.

## Releases

Create release tags from a verified `main`. The release workflow accepts tags beginning with `v` or a digit and builds the Windows, macOS, and Linux artifacts. Use the version format agreed by maintainers, verify the tag target, and document platform checks before pushing a release tag.

## Security and sensitive data

Use ignored, access-restricted runtime files for deployment configuration. Never paste credentials, full connection strings, API keys, cookies, private keys, personal data, or raw external authorization payloads into source, commits, pull requests, issue text, test fixtures, logs, screenshots, project memory, or ADRs. Redact evidence while preserving command, exit-code, count, and boundary information needed for review.

The current development environment uses PostgreSQL, Casdoor OIDC, Casbin, and forced PostgreSQL RLS as separate security boundaries. A green application test does not replace migration, role, tenant-isolation, and production-gate verification.
