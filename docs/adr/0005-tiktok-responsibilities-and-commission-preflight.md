# ADR 0005: Separate creator responsibilities before commission approval

Date: 2026-09-24

Status: Accepted for the P3-B2 internal pilot

## Context

The PRD distinguishes claim ownership, fulfillment and maintenance. PRD D6 still lacks approved percentages, overlap priority and a finance approver. Pool claims already use revision checks and append-only events.

## Decision

The TikTok creator pool's claim Owner, fulfillment owner and maintenance owner are independent tenant-scoped user references. An operations supervisor or tenant administrator changes the two execution roles through the pool revision and an append-only event, consistent with existing pool management permissions. Releasing the claim clears execution roles; transferring the claim does not silently replace them.

PRD D6 has no approved role percentages, overlap priority or finance approver. The commission endpoint therefore checks only the structure of a proposed internal input: three role shares add to 10,000 basis points, opaque order references do not overlap within the request, and the supplied expiry is future-dated. It always reports `rule_unapproved` and cannot submit or freeze a financial allocation. The supplied version and expiry are never treated as an approved rule. This prevents mock or manually entered metadata from becoming payment evidence.

## Alternatives considered

Keeping all responsibilities in the claim Owner would lose the PRD's distinct accountability. Treating user-entered version metadata as approved would allow an unreviewed allocation into finance. Both were rejected.

## Consequences and rollback

Future durable drafts need an approved rule registry, authorized order facts, cross-draft scope exclusion and named finance approval before a frozen snapshot can be introduced. That decision requires a separate migration and acceptance review.

The schema migration is reversible while no new responsibility event must be retained; rollback after real assignments requires an explicit data disposition. No runtime data is silently deleted by the forward migration.

## Evidence

- [E03 design](../superpowers/specs/2026-09-24-tiktok-e03-role-and-commission-preflight.md)
- [E03 implementation plan](../superpowers/plans/2026-09-24-tiktok-e03-role-and-commission-preflight.md)
