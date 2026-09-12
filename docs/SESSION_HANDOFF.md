# Current session handoff

Last refreshed: 2026-09-12 (Asia/Shanghai)

This file is mutable operational context. Re-check every process, port, branch, and test result before relying on it. It contains no credential values or connection strings.

## Repository state

- Working repository: `E:\develop\数字员工\joukir`.
- The reviewed functional audit was prepared on `docs/project-functional-audit-20260912` and integrated into local `main`. The follow-up document classification branch `docs/classify-project-docs` was also integrated into local `main`. The report now lives at `docs/reports/报告.md`; inspect `git rev-parse main` for the current SHA. The older `chore/main-repository-migration` branch remains at the migration cutover commit. No GitHub remote is configured yet.
- Annotated tag `handover-20260909` targets `e0cb8df042b3a5f856c60b45cf7e9c2bafbc23b5`. The clone has no object alternates and no configured remote.
- The old `E:\develop\数字员工\joukir-enterprise` source remains intact for rollback and will be removed manually by the user after acceptance.

## Installed local toolchain

- The new backend environment reports Python 3.12.13 and was rebuilt from `backend/uv.lock` with the development extra (79 installed packages in the migration install record).
- The current host reports Node.js 24.19.0 and npm 11.17.0. `npm ci` rebuilt 561 frontend packages from the lock file.
- `frontend-enterprise/dist/` was rebuilt in the new repository; it is ignored build output and is not staged.
- Ignored backend and frontend local configuration was copied through the approved secure handoff. Its access is restricted to the current Administrator and SYSTEM. Do not inspect or print its secret values during routine work.

## Verified source and test state

- The immutable pre-layout index has 1,154 entries and the pinned `fc1dd45` source map resolves all 1,154 uniquely, with zero missing, case-folded collisions, unexplained content edits or unexplained mode changes. Exactly 1,056 blobs remain identical, 98 edits map to reviewed commits, and the three Unix shell mode changes are reviewed. The tracked map and verifier are under `docs/migration/` and `scripts/migration/`.
- The migration's new-root and legacy backend baseline each collected 2,241 tests and ended 2,211 passed, 21 failed, 9 skipped, 0 errors, with identical normalized failure/error/skip nodes. The 2026-09-12 full audit collected 2,244 tests: 2,200 passed, 35 failed, 9 skipped. All 21 earlier stable failures reproduced; 13 of the 14 additional default-environment failures passed when isolated, and the remaining WeChat recovery test was intermittent. Ruff reported 1,844 existing issues. See `docs/reports/报告.md`; this is not a green backend gate.
- Frontend gates passed: configuration, 4,209-entry English i18n coverage, test type-check, 64 files/271 Vitest tests, and a 2,163-module production build.
- Integration: deterministic TikTok Mock replay passed 5/5 main SOPs and 30/30 exception checks with external writes disabled. PostgreSQL production gate returned `ok=true`; the adapted tenant A/B/no-context and cross-tenant write denial checks passed. Source map resolves 1,154/1,154 paths; root test-layout guard passes. A real minimal text request to the configured default model returned a nonempty answer. Twelve M2M identities verified after bypassing the Windows system proxy for loopback; default HTTPX otherwise received 502 from the proxy. Browser automation did not connect, so no complete human UI acceptance was claimed.
- Worktree security delta found zero new sensitive-text candidates or tracked runtime artifacts. The audit evidence XML/JSON is ignored under `.dev/functional-audit-20260912/`.

## Live local services

- Compose project `joukir-restored-20260909` currently reports PostgreSQL and Casdoor healthy, bound only to loopback on ports 55433 and 18000 respectively.
- After a temporary Docker Desktop shutdown during the audit, it was restarted and the existing volumes auto-restored. At the final check, PostgreSQL and Casdoor were healthy, the Web supervisor PID was 40792, app PID was 9656, `127.0.0.1:5173` was listening and `/api/health` returned ok. Re-check these transient PIDs and ports before relying on them.
- Health, gallery HTML/assets, OIDC configuration, Casdoor health and OIDC code/nonce/state/PKCE redirect checks passed without credentials. Browser automation failed to connect in this audit; human login, role/page interactions and full UI flows remain unverified.
- A 2026-09-12 16:34 Asia/Shanghai read-only database snapshot found 149 public tables, 74 nonempty, 75 empty, 4,863 rows. Ten active employees were published and 14 draft. One TikTok Shadow record was `running` with zero observations and no later heartbeat; local `TIKTOK_SHADOW_ENABLED=false`. These are changing operational counts, not 14-day acceptance.

## Next actions

1. Continue development from local `main` in `E:\develop\数字员工\joukir`, read `docs/reports/报告.md`, and use short-lived branches. Keep executable suites in the four categorized `tests/` subdirectories and run `tests/check_test_layout.py`.
2. Fix or explicitly baseline the 21 stable backend failures, isolate the WeChat race, and ensure the local Web/worker M2M client bypasses the Windows loopback proxy without changing authentication policy. Retest focused paths and the full applicable gates.
3. Have a human account owner complete Casdoor login, role/page, long conversation and SOP-task acceptance. For TikTok, real authorization, data, observation and write approval must each get separate evidence; the single zero-observation Shadow row is insufficient. Restore MinIO objects only when the missing backup scope and files are available.
4. Obtain the actual GitHub repository URL before adding `origin`, pushing or configuring required checks/protection. Do not invent a remote.

## Validations still unavailable or intentionally deferred

- A human Casdoor account has not completed final login and role/page acceptance.
- One minimal real external model text request succeeded; long conversation, streaming, attachments and reliability have not been accepted.
- TikTok, advertising, social, channel, and other third-party production authorizations and writes are not accepted; execution remains disabled where recorded in local configuration.
- MinIO object data was absent from the backup; Redis and Superset were not restored. Original asset availability is therefore unproven.
- macOS and Linux package smoke tests require their target platforms. Full release signing/notarization also requires maintainer-controlled external credentials.
- Remote binding, initial push, required GitHub checks, and `main` branch protection wait for a real GitHub URL and maintainer choices.
