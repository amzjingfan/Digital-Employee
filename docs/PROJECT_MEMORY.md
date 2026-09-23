# Joukir project memory

This file contains stable facts and working agreements. Read it with `SESSION_HANDOFF.md` at the start of every development session. Do not put branch-specific progress, live process IDs, credentials, connection strings, cookies, private keys, personal data, or raw external authorization payloads here.

## Product identity and license

- Joukir (九骥) is the inherited enterprise deployment and cross-border operations extension built on the StaffDeck digital-employee platform. The repository retains StaffDeck product and upstream attribution where applicable.
- The repository license is GNU Affero General Public License v3.0 as recorded in the root `LICENSE` file.
- Core product capabilities include digital employees, teams, conversations, Harness v2 execution, knowledge, skills and SOPs, tools, scheduled and work tasks, memory, feedback, traces, channels, and human handoff.
- Business extensions include brands and product lifecycle, advertising, social/creator operations, offsite channels, BI and operations reports, cross-border workflows, creative/DesignKit work, and the TikTok business unit.

## Code and runtime entry points

- `src/backend/app/main.py` creates the FastAPI API and registers the domain routers and workers. Interactive Swagger, ReDoc, and OpenAPI schema endpoints are deliberately disabled there.
- `src/backend/single_port_app.py` is the single-port desktop/Web entry point that serves the built frontend and API together.
- `src/frontend-enterprise/src/App.tsx`, `src/frontend-enterprise/src/enums/routes.ts`, and `src/frontend-enterprise/src/pages/` define the React workspace, routing, and screens.
- `src/backend/app/harness/`, `src/backend/app/agents/`, `src/backend/app/src/skills/`, `src/backend/app/knowledge/`, `src/backend/app/tools/`, and `src/backend/app/work_tasks/` contain the main digital-employee execution domains.
- `src/backend/app/bi/`, `advertising/`, `social/`, `offsite/`, `product_lifecycle/`, `business_execution/`, `operations_reports/`, `crossborder/`, and `tiktok/` contain business-domain behavior.
- `src/scripts/` manages local development lifecycle, `src/deploy/staffdeck-platform/` contains PostgreSQL/Casdoor platform assets, and `src/packaging/` builds desktop and Linux artifacts.

## Data, identity, and authorization boundaries

- PostgreSQL is the authoritative database for the current development environment. SQLModel/SQLAlchemy models live in `src/backend/app/db/`; reviewed schema changes are explicit SQL migrations under `src/backend/migrations/`.
- Casdoor supplies the current OIDC identity boundary. OIDC login and account mapping live in `src/backend/app/api/oidc.py`, `src/backend/app/accounts/`, and related security modules.
- Joukir intentionally retains two authentication entry paths: standard Casdoor OIDC for normal users and an explicitly initialized local administrator for emergency access. Browser single sign-out uses Casdoor front-channel logout without persisting Casdoor tokens. Production must pass the fail-closed HTTPS, Secure Cookie, strong application secret, and no-demo-seed startup gate before database initialization.
- Casbin policies and application permission checks form the service authorization boundary. PostgreSQL forced row-level security forms a separate tenant data boundary. Passing one boundary never substitutes for checking the others.
- Database runtime, migration, worker, and identity roles must stay least-privileged and must not receive superuser or `BYPASSRLS`. Code that reads or writes tenant data must establish and preserve the intended tenant context.
- Schema work must account for migration ownership, forward application, rollback where supported, data backfill, forced RLS, and the production database gate. Never disable RLS or broaden a role to make development or tests pass.
- Work-task runs are durable execution and audit evidence. User deletion physically removes ordinary conversations, but a same-tenant conversation referenced by `WorkTaskRun` is marked deleted and hidden from chat and user mutation paths while its session, messages, Harness state, workspace, and run records remain available to internal execution and enterprise audit paths. Keep the restrictive `(tenant_id, session_id)` run-to-session foreign key aligned with the application boundary; see ADR 0002.
- Public API support exists under `src/backend/app/public_api/` and is feature-gated. Use the published API skill references indexed in `docs/README.md`; do not assume an interactive `/docs` endpoint exists.

## Runtime and secret boundary

- Runtime state and secrets remain outside Git. The current restored environment is maintained below `E:\develop\数字员工\joukir-runtime` and in the independent Compose project named `joukir-restored-20260909`.
- Local `src/backend/.env` and `src/frontend-enterprise/.env.local` are ignored and access-restricted runtime inputs. Dependency trees, build output, logs, PID files, databases, recovered objects, and backup material are also outside version control.
- Do not put passwords, tokens, API keys, full database URLs, cookies, private keys, personal data, or raw authorization payloads in source, commits, documentation, tests, reports, terminal output, or screenshots. Evidence should record keys by name and results by status or count only.
- Restored PostgreSQL/Casdoor state and encrypted backups must not be rebuilt, deleted, or moved as a side effect of ordinary source work. Never use `docker compose down -v` on the restored project.

## Test organization and coverage limits

- Every executable repository test lives under `src/tests/`: backend pytest modules in `src/tests/src/backend/`, frontend Vitest modules in `src/tests/frontend/`, cross-module runners in `src/tests/integration/`, and package/runtime smoke checks in `src/tests/src/packaging/`.
- `src/tests/check_test_layout.py` enforces the tracked-file boundary. `src/skills/*/evals/cases.json` stays with each published skill because it is runtime evaluation data, not an executable repository test.
- Root `pytest.ini` supplies backend discovery and import paths. Frontend tests use `src/tests/frontend/tsconfig.json` and the `@/` alias into `src/frontend-enterprise/src`.
- No numeric coverage threshold is configured. Pull request CI runs a focused backend regression set and the complete frontend suite/build; changes outside that backend set require proportional focused tests or the complete backend suite.
- Real model calls, human identity/role flows, third-party authorization and writes, recovered object availability, and platform-specific packages require explicit acceptance evidence in their intended environment. Seed data, mocks, replay success, database restoration, or a health endpoint cannot establish those claims by themselves.

## TikTok P3-B0 data-validation boundary

- The runnable TikTok data-validation workbench uses four tenant-scoped PostgreSQL tables: pilot scopes, field contracts, action/provider evidence, and append-only validation-run summaries. Schema changes use explicit migrations, same-tenant references, forced RLS, and an update/delete guard on run history.
- Catalog version `p3-b0.v1` defines 30 field contracts, 27 action-level capabilities, and 4 provider decisions. Evidence belongs to an exact action; evidence for one endpoint, login, package, or Mock run never upgrades another action.
- `workbench_ready` and `real_data_ready` are separate gates. A deterministic Mock run may satisfy the workbench run requirement, but real readiness also requires matching E3 `real_account` evidence plus a real or approved recorded-data validation. Mock, documentation, sandbox, or login evidence cannot satisfy that gate.
- Validation storage and UI contain contracts, evidence metadata, check codes, counts, issue metadata, and fixture digests only. Raw fixtures, external response bodies, OAuth payloads, credentials, cookies, and token fingerprints remain outside this boundary.
- Approved recorded validation accepts a browser-selected JSON request only within a 2 MiB actual-byte limit. It permits the six catalog collections, the current 30 business fields, and reserved `observed_at` validation metadata; rejects unknown/nested/sensitive-key and non-finite JSON input; and never persists the raw dataset, source filename, or value-level errors.
- A recorded run requires an active same-tenant approver distinct from the executing administrator, timezone-aware approval/data-period metadata, and a sanitization attestation. It evaluates freshness against `replay_as_of`, stores the scope revision and contract digest, and becomes stale after scope, contract, catalog, or approval changes. Mock and recorded latest runs are selected independently; recorded success never upgrades action evidence to E3.

## TikTok P3-B1 historical-fact boundary

- A passed P3-B0 recorded run stores no business values. P3-B1 imports a matching approved sanitized dataset into separate tenant-scoped, append-only historical batches and six-domain normalized facts; it does not infer facts from the run summary alone. See [ADR 0003](adr/0003-tiktok-recorded-validation-and-history-facts.md).
- Versioned metric definitions, latest business-key observations, BD-assigned append-only reconciliations and a scope-revision-bound Owner signoff form the first dashboard/review slice. Missing source data is unknown, not zero; mixed GMV currencies are not summed.
- Synthetic and Mock facts never count toward the 30-record business review gate. A passed recorded run or an Owner review snapshot does not establish E3 authorization, a successful live API read, or production readiness.

## Git history and repository workflow

- This repository is an independent clone with no Git object alternates. It preserves the complete 44-commit handover history and original commit IDs.
- Annotated tag `handover-20260909` resolves to immutable handover baseline `e0cb8df042b3a5f856c60b45cf7e9c2bafbc23b5`.
- Current executable source uses the root `src/` directory; historical commits and dated handover documents may still show the former `source/` or flat-root layout as evidence.
- `main` is the integration branch. Use short-lived GitHub Flow branches and the review, validation, and merge rules in `CONTRIBUTING.md`.
- No remote is configured until a maintainer supplies the real GitHub URL. Do not invent a remote, organization, visibility setting, branch-protection rule, or required-check name.

## Memory maintenance

- Keep durable architecture, boundaries, and working agreements in this file.
- Classify new narrative documentation under `docs/` (for example `reports/`, `design/`, `operations/`, or `development-branches/`) and link it from `docs/README.md`. Keep only entry-point documents at the repository root.
- Keep mutable branch/HEAD, live services, recent verification, blockers, and exact next actions in `SESSION_HANDOFF.md`.
- Append chronological implementation evidence to `DEVELOPMENT_LOG.md`; never rewrite prior entries to make later results look cleaner.
- Record lasting architecture or workflow decisions in `docs/adr/` using its documented format.
- Use `docs/README.md` as the document index. Keep dated migration and development-branch records as historical snapshots instead of silently rewriting them to current paths.
