# ADR 0001: Main repository layout and history preservation

- Date: 2026-09-11
- Status: Accepted

## Context

The inherited Joukir delivery stored product source below `source/` while deployment, CI, and handover material also existed at repository root. Development needed a new independent main directory without losing any functional module or the provenance of the 44-commit handover baseline. The user also required one clearly categorized test directory, Git-based development, and durable project memory. Runtime databases, restored identity data, local secrets, dependencies, and build output had to remain outside tracked source.

## Decision

The main development repository is an independent full clone at `E:\develop\数字员工\joukir` with no Git object alternates or configured placeholder remote. It preserves original commit IDs and uses annotated tag `handover-20260909` for baseline `e0cb8df042b3a5f856c60b45cf7e9c2bafbc23b5`.

Product directories are promoted to a flat repository root: backend, frontend, deployment, packaging, scripts, skills, documentation, and GitHub configuration are first-class root entries. The layout change is recorded through ordinary Git rename commits, so `git log --follow` can trace files across the old `source/` boundary.

All executable repository tests live under root `tests/` and are classified as backend, frontend, integration, or packaging. Skill `evals/cases.json` files remain co-located because they are published evaluation data. A tracked guard checks the boundary from `git ls-files`.

Restored PostgreSQL and Casdoor state, runtime configuration, credentials, logs, process state, dependency trees, build output, and backups stay outside version control. Local ignored configuration points the new checkout at the existing runtime without making that runtime part of the repository.

The repository uses local `main` plus short-lived GitHub Flow branches. It remains without a remote until a maintainer supplies the real GitHub URL.

## Alternatives considered

- Reinitialize Git in the new directory: rejected because it discards provenance, review context, and exact handover commit IDs.
- Rewrite history so every old commit uses the flat root: rejected because it changes all commit IDs and creates unnecessary risk of omitting source outside `source/`.
- Keep the inherited nested layout: rejected because it leaves source, deployment, and governance split across two roots and conflicts with the selected main-directory structure.
- Keep tests beside production modules: rejected because the user requires one independent, categorized test root.
- Commit restored runtime or local configuration for portability: rejected because it would mix secrets and mutable data with source and weaken rollback and review boundaries.

## Consequences

- Historical commits and dated handover documents legitimately retain `source/` paths; current commands use flat root paths.
- Git history remains auditable and the old checkout remains a rollback source until the user removes it after acceptance.
- Test tooling must explicitly resolve the external root test tree. New executable tests outside `tests/` fail the layout guard.
- A fresh checkout must rebuild dependencies and frontend output and receive approved ignored runtime configuration before it can start.
- GitHub remote binding and branch protection are a later maintainer action. No placeholder URL or required-check name is recorded.
- Rollback during migration is to keep the old Web process and old checkout in service. The final process cutover occurs only after the new checkout passes its Task 8 gates.

## Evidence

- [Approved migration design](../superpowers/specs/2026-09-11-joukir-main-repository-migration-design.md)
- [Implementation plan](../superpowers/plans/2026-09-11-joukir-main-repository-migration.md)
- [Pre-layout source index](../migration/source-index-before-layout.tsv)
- [Layout mapping report](../migration/layout-mapping-report.json)
- Root promotion commit `07b1cd19131357127963394f3469d7488cdc5fbe`
- Backend test move commit `d081397d29f85284849674a2b21b9d6185fb8fa6`
- Frontend test move commit `963d0730c05213ec6d05cce5ded5c515779ca1e6`
- Integration/packaging test move commit `db849b773f7bb9a68d7027e8bb3c05d6006d2062`
