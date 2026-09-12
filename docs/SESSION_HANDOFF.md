# Current session handoff

Last refreshed: 2026-09-12 (Asia/Shanghai)

This file is mutable operational context. Re-check every process, port, branch, and test result before relying on it. It contains no credential values or connection strings.

## Repository state

- Working repository: `E:\develop\数字员工\joukir`.
- The migration feature branch is `chore/main-repository-migration`; its final functional-source commit is `fc1dd456445a0eccbe053fa0d19987a4b37102d9`.
- Local `main` was fast-forwarded from `9cc0327b7ac84c0d277293cf347fea2ccd40a8cb` through the reviewed migration commit `df310e5ef15b15d40d03946ca93bd3b3e1e8d99d` on 2026-09-12. The retained feature branch and `main` are kept at the same latest commit; inspect `git rev-parse main` and `git rev-parse chore/main-repository-migration` for their current SHA. No GitHub remote is configured yet.
- Annotated tag `handover-20260909` targets `e0cb8df042b3a5f856c60b45cf7e9c2bafbc23b5`. The clone has no object alternates and no configured remote.
- The old `E:\develop\数字员工\joukir-enterprise` source remains intact for rollback and will be removed manually by the user after acceptance.

## Installed local toolchain

- The new backend environment reports Python 3.12.13 and was rebuilt from `backend/uv.lock` with the development extra (79 installed packages in the migration install record).
- The current host reports Node.js 24.19.0 and npm 11.17.0. `npm ci` rebuilt 561 frontend packages from the lock file.
- `frontend-enterprise/dist/` was rebuilt in the new repository; it is ignored build output and is not staged.
- Ignored backend and frontend local configuration was copied through the approved secure handoff. Its access is restricted to the current Administrator and SYSTEM. Do not inspect or print its secret values during routine work.

## Verified source and test state

- The immutable pre-layout index has 1,154 entries and the pinned `fc1dd45` source map resolves all 1,154 uniquely, with zero missing, case-folded collisions, unexplained content edits or unexplained mode changes. Exactly 1,056 blobs remain identical, 98 edits map to reviewed commits, and the three Unix shell mode changes are reviewed. The tracked map and verifier are under `docs/migration/` and `scripts/migration/`.
- The full new-root and legacy backend baseline runs each collected 2,241 tests and ended 2,211 passed, 21 failed, 9 skipped, 0 errors, with identical normalized failure/error/skip nodes. This is not a full green suite; details and environment differences are in `docs/migration/VERIFICATION_20260911.md`. The workflow-contract fix added three tests after that baseline; the current tree collects 2,244 and the focused 20-test run passed.
- Frontend gates passed: configuration, 4,209-entry English i18n coverage, test type-check, 64 files/271 Vitest tests, and a 2,163-module production build.
- Integration/packaging: both Python runner groups compile, PowerShell and Bash callers parse, the deterministic TikTok replay passed 5 checks with external writes disabled, and the tracked root test-layout guard passes.
- GitHub workflow YAML parses and the backend TikTok CI subset passed 61 tests. The PostgreSQL production gate returned `ok=true`, and the worktree security delta found zero new sensitive-text candidates or tracked runtime artifacts.

## Live local services

- Compose project `joukir-restored-20260909` currently reports PostgreSQL and Casdoor healthy, bound only to loopback on ports 55433 and 18000 respectively.
- The new repository's Web launcher PID 40608 and listener PID 37160 took over `127.0.0.1:5173` on 2026-09-12. Re-check process identity before relying on these transient PIDs. The launcher uses `joukir\backend\.venv`, ignored `backend/.env` and external `E:\develop\数字员工\joukir-runtime\data`; the PID is also in ignored `.dev/local-web.pid`, with logs under the external runtime `logs/` directory.
- Health, gallery HTML/assets, OIDC configuration, Casdoor health and OIDC code/nonce/state/PKCE redirect checks passed without credentials. The browser rendered the already-authenticated gallery and a direct Casdoor Password page. Existing Admin cookies prevented this session from showing the unauthenticated SSO button, so that UI click remains unverified.

## Next actions

1. Continue all product development in `E:\develop\数字员工\joukir`; use a short-lived feature branch and pull request from the local `main` once a real GitHub remote is supplied. `CONTRIBUTING.md`, `AGENTS.md`, `.github/` and `docs/PROJECT_MEMORY.md` define the current workflow and durable context.
2. Triage the 21 shared backend failures as separate baseline/cross-platform work. When changing tests, keep executable suites in the four categorized `tests/` subdirectories and run `tests/check_test_layout.py`.
3. Ask the maintainer to provide the actual GitHub repository URL before adding `origin`, pushing or configuring required checks/protection. Do not invent a remote.
4. Have a human account owner complete Casdoor login, role/page and model-conversation acceptance; restore MinIO/Redis/Superset only if corresponding data and scope become available.

## Validations still unavailable or intentionally deferred

- A human Casdoor account has not completed final login and role/page acceptance.
- The restored model configuration has not made a real external model request.
- TikTok, advertising, social, channel, and other third-party production authorizations and writes are not accepted; execution remains disabled where recorded in local configuration.
- MinIO object data was absent from the backup; Redis and Superset were not restored. Original asset availability is therefore unproven.
- macOS and Linux package smoke tests require their target platforms. Full release signing/notarization also requires maintainer-controlled external credentials.
- Remote binding, initial push, required GitHub checks, and `main` branch protection wait for a real GitHub URL and maintainer choices.
