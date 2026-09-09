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

`ok=true` proves only that the auditable TikTok code and Skill surface in the current commit contains no Live write. Signed external evidence is verified separately by the [signed UAT release evidence gate](#signed-uat-release-evidence-gate). Neither static result replaces real TikTok authorization, a full 14-calendar-day shadow run, or validation by the authoritative external systems.

## Signed UAT release evidence gate

This second, read-only gate connects environment checks and externally accountable evidence to the tenant production-readiness card. It does not issue approvals, hold a signing private key, perform OAuth, start a shadow run, or change an external system.

The application accepts only an Ed25519-signed evidence bundle bound to one tenant, one immutable Git target commit, one SHA-256 release-request digest, one configured signing-key identifier, and an expiry no more than 90 days after issue. Missing configuration, malformed or oversized bundles, stale timestamps, target mismatches, unknown fields, symlinks, and invalid signatures all fail closed.

### Runtime configuration

Supply these values through the protected deployment environment. Do not commit their values:

```text
TIKTOK_RELEASE_EVIDENCE_DIR
TIKTOK_RELEASE_EVIDENCE_PUBLIC_KEY_FILE
TIKTOK_RELEASE_EVIDENCE_KEY_ID
TIKTOK_RELEASE_TARGET_COMMIT
TIKTOK_RELEASE_REQUEST_SHA256
```

Both paths must be absolute. The evidence directory and public-key file must be read-only to the application identity. The private key belongs to the protected release controller and must never be installed on the application host.

For tenant `<tenant-id>`, the controller writes the bundle as:

```text
<TIKTOK_RELEASE_EVIDENCE_DIR>/<sha256(UTF-8 tenant-id)>.json
```

### Signed bundle contract

The top-level JSON object has no optional or unknown fields:

```json
{
  "schema_version": 1,
  "tenant_id": "tenant_demo",
  "target_commit": "<40-or-64-lowercase-hex-git-object-id>",
  "request_sha256": "<64-lowercase-hex-release-request-digest>",
  "key_id": "uat-release-2026-q3",
  "issued_at": "2026-09-09T03:00:00Z",
  "expires_at": "2026-10-09T03:00:00Z",
  "controls": {
    "identity_mfa": {"status": "passed", "authority": "<system>", "record_id": "<immutable-id>", "decided_at": "<UTC-time>", "expires_at": "<UTC-time-or-null>"},
    "transport_tls": {"status": "passed", "authority": "<system>", "record_id": "<immutable-id>", "decided_at": "<UTC-time>", "expires_at": "<UTC-time-or-null>"},
    "credential_rotation": {"status": "passed", "authority": "<system>", "record_id": "<immutable-id>", "decided_at": "<UTC-time>", "expires_at": "<UTC-time-or-null>"},
    "postgres_restore": {"status": "passed", "authority": "<system>", "record_id": "<immutable-id>", "decided_at": "<UTC-time>", "expires_at": "<UTC-time-or-null>"},
    "business_signoff": {"status": "approved", "authority": "<system>", "record_id": "<immutable-id>", "decided_at": "<UTC-time>", "expires_at": "<UTC-time-or-null>"},
    "security_signoff": {"status": "approved", "authority": "<system>", "record_id": "<immutable-id>", "decided_at": "<UTC-time>", "expires_at": "<UTC-time-or-null>"},
    "product_signoff": {"status": "approved", "authority": "<system>", "record_id": "<immutable-id>", "decided_at": "<UTC-time>", "expires_at": "<UTC-time-or-null>"}
  },
  "signature": "<base64url-ed25519-signature>"
}
```

The controller signs the UTF-8 bytes of the object after removing `signature` and serializing with sorted keys, no insignificant whitespace, and `ensure_ascii=false`. The verifier accepts only an Ed25519 SubjectPublicKeyInfo PEM public key.

### Run

From `backend`:

```powershell
$env:PYTHONPATH='.'
uv run python scripts/verify_tiktok_uat_release_evidence.py --tenant-id tenant_demo
```

Exit `0` means the production-like runtime configuration and all signed evidence controls passed. Exit `2` is release-blocking. Output contains gate codes and references only; it does not print credentials or bundle payloads.

### Trust boundary and shadow criteria

A valid bundle proves that the configured release controller signed the supplied references. The controller remains responsible for querying the authoritative approval, identity, TLS, secret-management, and backup systems before signing. The application must not treat an unsigned document, database row, chat message, or model-generated approval as equivalent evidence.

The 14-calendar-day shadow run and real TikTok authorization remain separate database/runtime gates. Official Live connector reads record successful and failed shadow observations. A shadow run passes only after its full duration, observations on at least 14 distinct UTC dates, a final heartbeat at or after the end time, a read-only baseline, and zero recorded connector errors. An elapsed but incomplete run becomes `expired`, never `completed`.

The overall production-readiness result passes only when those gates, the static no-live-write audit, agent releases, production configuration, and the signed evidence bundle all pass together.
