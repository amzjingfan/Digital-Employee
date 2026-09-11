# Current session handoff

Last refreshed: 2026-09-11 (Asia/Shanghai)

This file is mutable operational context. Re-check every process, port, branch, and test result before relying on it. It contains no credential values or connection strings.

## Repository state

- Working repository: `E:\develop\数字员工\joukir`.
- Active migration branch: `chore/main-repository-migration`.
- Last completed migration task before the governance/memory commit: `c2ccf97600ed3ef27b21d3d9d987db0baabc02d3` (`test: fix test layout guard matching`).
- Local `main` still points to the approved design baseline while the migration branch is under review. Task 8 will fast-forward it only after final functional verification.
- Annotated tag `handover-20260909` targets `e0cb8df042b3a5f856c60b45cf7e9c2bafbc23b5`. The clone has no object alternates and no configured remote.
- The old `E:\develop\数字员工\joukir-enterprise` source remains intact for rollback and will be removed manually by the user after acceptance.

## Installed local toolchain

- The new backend environment reports Python 3.12.13 and was rebuilt from `backend/uv.lock` with the development extra (79 installed packages in the migration install record).
- The current host reports Node.js 24.19.0 and npm 11.17.0. `npm ci` rebuilt 561 frontend packages from the lock file.
- `frontend-enterprise/dist/` was rebuilt in the new repository; it is ignored build output and is not staged.
- Ignored backend and frontend local configuration was copied through the approved secure handoff. Its access is restricted to the current Administrator and SYSTEM. Do not inspect or print its secret values during routine work.

## Verified source and test state

- All 1,154 indexed handover paths resolved after the flat-root move; 1,153 retained identical blobs and the expected `.gitignore` edit was the only content difference at that stage.
- Backend tests: 190 tracked modules under `tests/backend/`; old and new collection both found 2,241 tests. A path-sensitive 26-test run passed after setting UTF-8 subprocess I/O and bypassing proxies for localhost. The complete new backend suite is still pending Task 8 comparison.
- Frontend tests: 64 files and 271 tests passed in both the old and new layouts. Frontend test type-check and production build passed after the move.
- Integration/packaging: both Python runner groups compile, PowerShell and Bash callers parse, the deterministic TikTok replay passed 5 checks with external writes disabled, and the tracked root test-layout guard passes.
- Task 6 CI-parity checks: backend layout/compile/Ruff passed and the 12 focused TikTok modules passed 61 tests; frontend configuration, 4,209-entry English i18n coverage, test type-check, 64-file/271-test Vitest suite, and 2,163-module production build passed. All workflow YAML parses, and the CodeQL, release, and Dependabot files remain byte-identical to their pre-task versions.
- Historical full backend handover evidence reports 2,207 passed, 22 failed, and 12 skipped. It is comparison evidence, not a successful current full-suite result.

## Live local services

- Compose project `joukir-restored-20260909` currently reports PostgreSQL and Casdoor healthy, bound only to loopback on ports 55433 and 18000 respectively.
- The old repository's Web process tree is still serving `127.0.0.1:5173`; the parent process uses the old `joukir-enterprise\source\backend\.venv` and the listening child currently reports application health `status=ok`, app `九骥 Joukir`.
- The new repository has not taken ownership of port 5173 and has no new `.dev/local-web.pid`. Do not stop the old process until every pre-cutover Task 8 gate passes.

## Next actions

Task 8 must:

1. Re-run Git integrity, mapping, test-layout, stale-path, staged-artifact, and redacted secret-pattern checks.
2. Run the full backend suite from the new root and compare every failure with the handover environment; fix only migration regressions.
3. Run all frontend gates and record final file/test counts and build result.
4. Run the PostgreSQL production gate without exposing its database URL.
5. If every pre-cutover gate passes, stop only the verified old Web process tree, start the new single-port app with the external runtime data directory, and store the new ignored PID/log state.
6. Verify health, main pages, OIDC configuration, Casdoor health, and the browser SSO redirect to the Casdoor password page with PKCE. Do not enter or expose human credentials.
7. Write final migration evidence, refresh this handoff, append the development log, commit the evidence, and fast-forward local `main`.

## Validations still unavailable or intentionally deferred

- A human Casdoor account has not completed final login and role/page acceptance.
- The restored model configuration has not made a real external model request.
- TikTok, advertising, social, channel, and other third-party production authorizations and writes are not accepted; execution remains disabled where recorded in local configuration.
- MinIO object data was absent from the backup; Redis and Superset were not restored. Original asset availability is therefore unproven.
- macOS and Linux package smoke tests require their target platforms. Full release signing/notarization also requires maintainer-controlled external credentials.
- Remote binding, initial push, required GitHub checks, and `main` branch protection wait for a real GitHub URL and maintainer choices.
