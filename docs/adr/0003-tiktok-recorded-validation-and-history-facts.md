# ADR 0003: Separate TikTok recorded validation from historical facts

Date: 2026-09-23. Status: Accepted.

## Context

P3-B0 recorded runs retain an immutable validation summary and dataset digest, not business values. P3-B1 needs durable, comparable historical facts while keeping raw files and external provider responses outside the audit store.

## Decision

P3-B1 promotes the same approved, sanitized six-domain dataset through a separate import that rechecks the current pilot scope, field contracts and digest, then stores normalized facts with provenance, versioned metric definitions and append-only human reviews. This keeps a passed replay from silently becoming business evidence and lets each fact be traced and reconciled without retaining the uploaded file or an external provider response.

Mock and synthetic facts remain visible for workbench testing but never count toward the 30-record business review gate. Owner confirmation records a digest of the reviewed facts and the pilot scope revision; later review or scope changes make that confirmation stale. An approved sanitized source is an attested candidate for business review, not proof of live E3 authorization or production readiness.

## Alternatives considered

Storing raw datasets inside validation runs was rejected because it would expand the P3-B0 audit surface and retain more sensitive material. Computing a dashboard directly from each upload was rejected because the values and human conclusions would have no durable, reviewable identity.

## Consequences and rollback

The dashboard must query the separate fact store and report missing evidence as unknown. Import and review records are append-only; rollback of the schema before production use can drop the new tables, while an in-use installation requires an explicit data retention and migration decision rather than deleting reviewed business history. The P3-B0 validator remains usable independently.

## Evidence

- [Approved P3-B1 design](../superpowers/specs/2026-09-23-tiktok-p3b1-dashboard-fulfillment-design.md)
- [P3-B1 implementation plan](../superpowers/plans/2026-09-23-tiktok-p3b1-dashboard-fulfillment.md)
