# TikTok P3-A Live-Write-Disabled Release Gate

## Purpose

This read-only gate audits the frozen P3-A TikTok surface. It prevents an unreviewed API route, outbound HTTP mutation, or Skill write declaration from entering a release. It does not call TikTok, Casdoor, or any business system; read credentials; or change a database.

## Run

From the `backend` directory:

```powershell
$env:PYTHONPATH='.'
uv run python scripts/verify_tiktok_live_write_disabled.py
```

Success prints JSON with `ok=true` and exits `0`. A blocked gate prints `ok=false`, lists stable machine-readable reasons in `issues`, and exits `2`. The production-readiness API uses the same audit function for its `external_writes` gate.

## Audited surface

- The enterprise TikTok API must exactly match the reviewed route freeze. Adding, removing, or changing a method or path fails closed.
- HTTP clients in `backend/app/tiktok/` and the TikTok API may not use `POST`, `PUT`, `PATCH`, `DELETE`, `request`, or `send`. The current official adapter permits only reviewed GET-based authorization and reads.
- TikTok modules may not import the generic `business_execution` surface or an unreviewed network library.
- The Skill Pack registry and all 12 manifests must be present, repository-contained, and explicitly declare `external_write=false`.

## Failure handling

1. Do not delete the check or change only its expected result to make the gate green.
2. Review the route, file, and verb identified by `issues`. If it remains a P3-A read or internal rehearsal, obtain security review and update the freeze plus regression tests together.
3. If the change produces a TikTok external side effect, stop the P3-A release. Treat it as a separate Live-write project requiring approval, idempotency, expected resource revision, deadline, rollback/reconciliation, and a signed connector contract.

## Evidence boundary

`ok=true` proves only that the auditable TikTok code and Skill surface in the current commit contains no Live write. It does not prove real TikTok authorization, formal MFA/TLS/key rotation, a full 14-calendar-day shadow run, backup/restore rehearsal, or business/product/security sign-off.
