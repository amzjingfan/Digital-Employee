# TikTok P3-B2 first slice: internal creator claims

Date: 2026-09-23. Base: `main@d88d231`. This is the first E03 slice, not the P3-B2 exit gate.

## Outcome and boundary

An operations supervisor can place an existing tenant-owned SocialCreator with an active, verified TikTok platform identity and current evidence into a US pilot pool. An active TikTok BD can claim a public entry exactly once, record an evidence-linked effective follow-up, and see the next due time. A supervisor can mark an overdue claim as a reflow candidate and approve its return to the public pool. The interface and API show current state and revision; concurrent actions fail with a refreshable conflict. Only internal records change. There is no creator message, platform operation, commission calculation, or payment.

## Model and authority

Use the existing SocialCreator and SocialPlatformIdentity as canonical person and platform identity records. Intake checks the selected identity's latest SocialCreatorEvidence is current, matching the Social catalog's effective status, and stores that existing evidence ID as its source. Add one tenant-scoped pool entry per creator, with the verified TikTok identity, source reference, explicit SLA rule version and follow-up window, state, owner, due time, and integer revision. An append-only event table stores each transition with actor, prior/new owner, evidence reference or reason, and server time. Follow-up references use a strict opaque ID syntax; do not retain contacts or private message text.

The supervisor sets a non-default, versioned follow-up window at intake; no global seven-day assumption is embedded. BD claims use a database compare-and-swap on `(tenant_id, id, revision, state)` so two BDs cannot both win. Effective follow-up requires a human-supplied opaque evidence reference and renews the due time from the server clock; viewing a profile does not count. Reflow is proposed only after the due time and requires supervisor approval before the owner is cleared. A valid owner follow-up after proposal cancels the candidate if it wins the revision race.

The service checks active user, tenant, role and exact ownership. The intake panel lists eligible creators from the existing Social catalog so operators do not have to type IDs. BD reads only public and personally owned entries; a supervisor/admin may read the whole tenant pool. A claim race returns a conflict with current owner and revision but no private contact data. PostgreSQL stores composite tenant foreign keys, forced RLS, minimal role grants and an append-only event guard. The API and UI do not add any external send route.

## Acceptance

Focused tests cover verified identity intake, duplicate and cross-tenant denial, two competing claims, stale revision, owner-only follow-up, no view-as-action, overdue proposal, supervisor approval, and the follow-up/approval race. Static migration tests check tenant constraints, forced RLS, grants and event immutability. Frontend tests check role-gated controls and conflict refresh. UI browser and live PostgreSQL checks remain separate environment gates; synthetic test entries do not constitute real creator or business acceptance.
