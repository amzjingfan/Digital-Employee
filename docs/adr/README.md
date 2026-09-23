# Architecture decision records

Architecture decision records (ADRs) explain choices that have lasting effects on system structure, security boundaries, data ownership, deployment, or repository workflow. They complement project memory: `PROJECT_MEMORY.md` states the current durable rule, while an ADR explains why the rule exists and what alternatives were rejected.

## When to add or update an ADR

Create an ADR before merging a lasting decision that changes a public contract, service or data boundary, tenant/security model, database strategy, deployment topology, repository layout, required workflow, or major dependency. Small implementation details and temporary session state do not need an ADR.

Do not rewrite an accepted ADR to hide history. Add a new ADR that supersedes it and link both records. Never include credentials, connection strings, cookies, private keys, personal data, or raw external authorization payloads.

## Format

Use the next four-digit number and a short lowercase filename. Include:

1. title, date, and status (`Proposed`, `Accepted`, `Superseded`, or `Rejected`);
2. context and constraints;
3. decision;
4. alternatives considered;
5. consequences, including risks and rollback;
6. evidence and related documents.

## Index

- [0001 — Main repository layout and history preservation](0001-main-repository-layout.md) — Accepted, 2026-09-11.
- [0002 — Preserve task execution evidence when users delete conversations](0002-task-session-deletion-retention.md) — Accepted, 2026-09-22.
- [0003 — TikTok recorded validation and historical facts](0003-tiktok-recorded-validation-and-history-facts.md) — Accepted, 2026-09-23.
- [0004 — TikTok creator pool ownership](0004-tiktok-creator-pool-ownership.md) — Accepted, 2026-09-23.
