# Joukir documentation index

Start a development session with the durable memory and current handoff below. Put new reports, designs, operations records, and branch notes in the matching `docs/` category, then add them to this index. Dated handover and development-branch records are evidence snapshots: they may use the former `source/` layout or describe service state that has since changed. Use current commands from the root README, `CONTRIBUTING.md`, and `src/tests/README.md`.

## Current reports

- [Current project functional audit and handover report, 2026-09-12](reports/报告.md)

## Development context and governance

- [Stable project memory](PROJECT_MEMORY.md)
- [Current session handoff](SESSION_HANDOFF.md)
- [Append-only development log](DEVELOPMENT_LOG.md)
- [Architecture decision records](adr/README.md)
- [ADR 0001: main repository layout and history preservation](adr/0001-main-repository-layout.md)
- [ADR 0002: preserve task execution evidence when users delete conversations](adr/0002-task-session-deletion-retention.md)
- [ADR 0003: TikTok recorded validation and historical facts](adr/0003-tiktok-recorded-validation-and-history-facts.md)
- [Repository agent rules](../AGENTS.md)
- [Contribution and GitHub Flow guide](../CONTRIBUTING.md)
- [Repository test guide](../src/tests/README.md)
- [Agent documentation domain policy](agents/domain.md)
- [Agent issue tracker policy](agents/issue-tracker.md)
- [Agent triage label policy](agents/triage-labels.md)

## Product requirements

- [Cross-border digital workforce PRD V1.8 (2026)](prd/crossborder-digital-workforce-prd-2026.md)
- [TikTok business unit module PRD V1.8 (2026)](prd/tiktok-business-unit-module-prd-v1.8.md)
- [Cross-border digital workforce integrated plan (2026)](prd/crossborder-digital-workforce-integrated-plan-2026.md)

The cross-border PRD and integrated plan refer to `prd/lan-multiuser-codex-memory-2026.md`. That LAN multiuser/Codex memory research document was absent from the inherited repository, so this migration records the gap instead of fabricating its contents.

## Operations and restoration

- [TikTok live-write release gate runbook](runbooks/tiktok-live-write-release-gate.md)
- [StaffDeck platform deployment guide](../src/deploy/staffdeck-platform/README.md)
- [StaffDeck platform source manifest](../src/deploy/staffdeck-platform/SOURCE_MANIFEST.md)
- [PostgreSQL and Casdoor restoration record, 2026-09-09](DATABASE_RESTORE_20260909.md) — dated handover evidence; verify live state before using it.
- [Joukir analysis and local startup record, 2026-09-09](LOCAL_STARTUP_20260909.md) — dated source-layout/startup snapshot; current service state is in the session handoff and final verification.
- [Portable development handover, 2026-09-09](PORTABLE_DEVELOPMENT_20260909.md) — dated handover snapshot.
- [Backup scope](operations/BACKUP_SCOPE.md) — inherited scope record; backup data itself remains outside Git.

## Repository migration

- [`src/` repository layout migration design](superpowers/specs/2026-09-17-src-layout-migration-design.md)
- [`src/` repository layout migration implementation plan](superpowers/plans/2026-09-17-src-layout-migration.md)
- [Approved main-repository migration design](superpowers/specs/2026-09-11-joukir-main-repository-migration-design.md)
- [Main-repository migration implementation plan](superpowers/plans/2026-09-11-joukir-main-repository-migration.md)
- [Pre-layout tracked source index](migration/source-index-before-layout.tsv) — immutable handover path/blob evidence.
- [Flat-layout mapping report](migration/layout-mapping-report.json)
- [Final source path/blob mapping](migration/final-source-map.tsv)
- [Final migration and functional verification, 2026-09-11](migration/VERIFICATION_20260911.md)
- [Reproducible migration evidence tools](../src/scripts/migration/README.md)

## Current designs and implementation plans

- [TikTok P3-B1 historical facts, dashboard and reconciliation design, 2026-09-23](superpowers/specs/2026-09-23-tiktok-p3b1-dashboard-fulfillment-design.md)
- [TikTok P3-B1 historical facts, dashboard and reconciliation implementation plan, 2026-09-23](superpowers/plans/2026-09-23-tiktok-p3b1-dashboard-fulfillment.md)
- [TikTok P3-B0 runnable data validation workbench design, 2026-09-22](superpowers/specs/2026-09-22-tiktok-p3b0-data-validation-workbench-design.md)
- [TikTok P3-B0 approved recorded-data validation design, 2026-09-22](superpowers/specs/2026-09-22-tiktok-p3b0-recorded-validation-design.md)
- [TikTok P3-B0 approved recorded-data validation implementation plan, 2026-09-22](superpowers/plans/2026-09-22-tiktok-p3b0-recorded-validation.md)
- [TikTok P3-B0 runnable data validation workbench implementation plan, 2026-09-22](superpowers/plans/2026-09-22-tiktok-p3b0-data-validation-workbench.md)
- TikTok P3-B0 browser acceptance: [administrator Mock result](screenshots/tiktok-p3b0/admin-mock-run.jpg) and [member read-only view](screenshots/tiktok-p3b0/member-read-only.jpg)
- Recorded-validation browser screenshots are intentionally absent: the browser-control inventory was unavailable during final acceptance, so automated backend/frontend evidence is recorded without claiming visual acceptance.
- [Casdoor production authentication hardening design, 2026-09-18](superpowers/specs/2026-09-18-casdoor-production-auth-hardening-design.md)
- [Casdoor production authentication hardening implementation plan, 2026-09-18](superpowers/plans/2026-09-18-casdoor-production-auth-hardening.md)

## Historical architecture and implementation records

These files preserve design or branch evidence from the inherited development period. They are not current runbooks.

- [Model API protocol design](design/design-model-api-protocols.md)
- [Multi-agent team decisions](design/design-multi-agent-team-decisions.md)
- [Design QA record](design/design-qa.md)
- [Feishu channel development record](development-branches/development-feishu-channel.md)
- [Cross-border capabilities agent report, 2026-09-02](reports/agent_report_crossborder_capabilities_20260902.md)
- [Cross-border gallery agent report, 2026-09-02](reports/agent_report_crossborder_gallery_20260902.md)
- [StaffDeck snapshots/M2M agent report, 2026-09-02](reports/agent_report_staffdeck_snapshots_m2m_20260902.md)
- [Amazon Ads PDCA branch](development-branches/amazon-ads-pdca.md)
- [BI analytics branch](development-branches/bi-analytics.md)
- [Portable integration branch](development-branches/integration-portable-20260909.md)
- [Offsite channels branch](development-branches/offsite-channels.md)
- [Platform foundation branch](development-branches/platform-foundation.md)
- [Social operations branch](development-branches/social-operations.md)
- [Workforce connectors/assets branch](development-branches/workforce-connectors-assets.md)
- [Workforce platform governance branch](development-branches/workforce-platform-governance.md)
- [Seven-role workforce workflows branch](development-branches/workforce-seven-role-workflows.md)
- [TikTok department branch](development-branches/workforce-tiktok-department.md)
- [Workforce UAT/release branch](development-branches/workforce-uat-release.md)

## API skill references

The application intentionally disables FastAPI's interactive Swagger, ReDoc, and OpenAPI schema routes. The tracked StaffDeck API skills provide maintained authentication and endpoint guidance:

- [API authentication skill](../src/skills/staffdeck-api-auth/SKILL.md) and [authentication endpoint reference](../src/skills/staffdeck-api-auth/references/endpoints.md)
- [Agent execution skill](../src/skills/staffdeck-api-run-agent/SKILL.md) and [run API reference](../src/skills/staffdeck-api-run-agent/references/run-api.md)
- [Resource management skill](../src/skills/staffdeck-api-manage-resources/SKILL.md) and [resource API reference](../src/skills/staffdeck-api-manage-resources/references/resources-api.md)
- [SOP management skill](../src/skills/staffdeck-api-manage-sops/SKILL.md) and [SOP API reference](../src/skills/staffdeck-api-manage-sops/references/sop-api.md)

Public API routes are feature-gated and may be disabled in a deployment. Validate configuration, authentication scope, tenant context, and the actual route before relying on an example.
