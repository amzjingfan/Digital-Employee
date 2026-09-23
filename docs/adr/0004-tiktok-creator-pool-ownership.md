# ADR 0004: Keep TikTok creator ownership separate from creator identity

Date: 2026-09-23. Status: Accepted.

## Context

P3-B2 needs one current BD owner for a creator and a reviewable record of claims, follow-ups and returns to the pool. The existing SocialCreator and SocialPlatformIdentity records identify a creator and a verified TikTok account; changing either record to represent a temporary BD assignment would mix identity with workflow state. A profile view is not evidence of an effective follow-up, and a missed deadline alone must not silently transfer ownership.

## Decision

Store one tenant-scoped pool entry per canonical SocialCreator, linked to an active verified TikTok identity with current latest evidence at intake. The pool entry holds the current assignment, explicit supervisor-set SLA rule version/window, due time and revision. Intake stores the selected existing SocialCreatorEvidence ID as its source, not free text. Store each transition in an append-only event table with actor, prior/new owner, server time and an opaque evidence reference or reason. Follow-up references must match `evidence:` plus 32 lowercase hexadecimal digits. Do not retain contact details, messages or raw platform payloads.

Claims and subsequent transitions compare the expected revision and state in the database update. Only an active TikTok BD may claim or record an effective follow-up for their own entry; only an operations supervisor or admin may intake and approve reflow. An overdue claim becomes a candidate first. A supervisor approval clears ownership; an owner follow-up that wins the revision race renews the deadline and cancels the candidate. PostgreSQL enforces tenant composite references on the pool and all event user IDs, forced RLS and narrow runtime grants in addition to service authorization.

For personnel changes, a supervisor or admin may transfer a claimed or reflow-candidate entry to another active BD in the same tenant, or release it to the public pool. The same revision comparison applies. Transfer resets the follow-up deadline and cancels pending reflow; release clears the deadline. Both write an append-only event with prior/new owner, actor, server time and a fixed reason code, without storing free-text personnel details. The event-type constraint is extended by a separate migration so an already-applied pool migration remains unchanged.

## Alternatives considered

Putting owner and due time on SocialCreator was rejected because those fields are TikTok workflow state, while SocialCreator is a reusable canonical identity. An automatic deadline-triggered return was rejected because a delayed or disputed follow-up needs human review. Last-write-wins updates were rejected because simultaneous BD claims could silently overwrite ownership.

## Consequences and rollback

The pool cannot be populated until a verified TikTok identity with current evidence exists, and intake requires an explicit SLA rule version. Current state can be queried directly while event history remains auditable. The first interface lists up to 100 currently eligible creators from the Social catalog; pagination or search is a separate usability improvement. Tenants with a previously published Casbin policy must publish a reviewed successor containing the new creator-pool grants before BD POST actions work, because the published policy takes precedence over the repository CSV. The down migration drops both tables and their evidence, so it is suitable only before production data is retained; an in-use deployment requires a migration and retention decision.

The owner-transfer migration can be rolled back only while no `transferred` or `released` event has been retained; PostgreSQL rejects the old event constraint otherwise. A deployed tenant with those events needs a deliberate retention and forward-repair decision rather than deleting audit rows for rollback.

## Evidence

- [P3-B2 creator claim design](../superpowers/specs/2026-09-23-tiktok-p3b2-creator-claim-design.md)
- [P3-B2 implementation plan](../superpowers/plans/2026-09-23-tiktok-p3b2-creator-claim.md)
