# ADR 0006: Persist unapproved commission proposals without reserving orders

Date: 2026-09-24

Status: Accepted for the P3-B2 internal pilot

## Context

ADR 0005 left commission preflight stateless because PRD D6 had no approved percentages, conflict priority or finance approver. Supervisors still need durable internal evidence of what was proposed and which proposals refer to the same order. The opaque order references have not been reconciled to an authorized order source.

## Decision

Save one structurally valid proposed order scope as an immutable, tenant-scoped, always-unapproved snapshot. Capture the pool revision and role IDs, reject stale pool input, and make retry idempotent. Detect overlap against all saved proposals in the tenant on read; overlap is a warning and blocks no write because an unapproved save must not confer order priority. Neither a save nor the absence of overlap proves order ownership, data rights, financial authorization or payment liability. BD users cannot see the proposal detail.

The authoritative financial allocation remains a separate future type and workflow. It requires a published rule with D6 priority, independently authorized order facts, exclusive conflict resolution, a named finance reviewer and an immutable approved/frozen snapshot. No route in this ADR submits or freezes a proposal.

## Alternatives and consequences

An order-wide unique index on proposals was rejected: the first unapproved draft would win an undefined business priority. Mutable proposals were rejected because changes would erase the original decision evidence. Retaining every draft means older overlapping proposals continue to appear as conflicts; a future reviewed selection workflow must decide their disposition.

The PostgreSQL migration applies forced RLS, same-tenant foreign keys, an append-only trigger and only SELECT/INSERT runtime grants. Its down migration drops the table, so operators may run it only after confirming no proposal data must be retained. The migration role cannot certify table emptiness with a normal SELECT under forced RLS; a prior implementation of that check falsely saw an occupied table as empty and was removed.

ADR 0007 replaces the pilot-scale tenant-wide JSON overlap scan with a derived, tenant-scoped order-reference index. The proposal snapshot and unapproved boundary remain unchanged.

## Evidence

- [Design](../superpowers/specs/2026-09-24-tiktok-e03-unapproved-drafts.md)
- [Implementation plan](../superpowers/plans/2026-09-24-tiktok-e03-unapproved-drafts.md)
