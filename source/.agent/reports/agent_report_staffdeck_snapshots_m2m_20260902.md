# Agent Audit Report: StaffDeck execution snapshots and role M2M identities

Date: 2026-09-02 (Asia/Shanghai)

## Outcome

The requested feature is implemented and deployed to the local StaffDeck sandbox. Every new work-task Run must bind one active role digital employee, one active tenant/role-matched Casdoor service identity, and one append-only execution snapshot. Seven distinct Casdoor Client Credentials applications and seven one-to-one StaffDeck identity mappings are active.

Production/live release verdict: **INCONCLUSIVE / BLOCKED**. This source directory is not a Git repository, so no immutable commit/tree/diff target can be produced. No independent read-only verifier is available in this task. A high-risk IAM release therefore still requires a Git-backed immutable target, independent verification and accountable human approval.

## Risk classification

Tier: **high**.

Rationale: this change handles authentication secrets, workload identity, tenant RLS, execution authorization, durable task inputs and a PostgreSQL schema migration. A defect could leak a Client Secret, misattribute work to another role, bypass a revoked capability or weaken tenant isolation.

## Approved scope

- Freeze employee, SOP, knowledge-base and tool inputs at Run claim time.
- Add separate Casdoor M2M service identity for operations supervisor, after-sales, Listing compliance, logistics exception, advertising inspection, designer and procurement.
- Preserve StaffDeck/Casbin/RLS as the final business authorization layer.
- Keep external business execution in sandbox.

Requirements SHA-256: `e402609d11969a2fd5dbeb9bf9d3165f151a3a493cccbeeb5ff70f5ba4332026`

Current 23-file core source-scope manifest SHA-256: `21a71995d3b46a6401d92a3827c7a6d9a419688c8f6081bb38c221d8a60df5d0`

The hash is evidence for this local audit only; it is not a substitute for a Git commit/tree and must be recomputed after any edit.

## Design and controls

1. Claim-time snapshot
   - `work_task_execution_snapshots` is unique per Run and records safe employee data, exact expanded SOP content/version, knowledge-base version IDs, safe tool descriptors/digests, capability maps and service-identity fingerprints.
   - The canonical SHA-256 is stored on both Run and snapshot and recomputed before execution.
   - Raw tool auth/config values, Client Secrets and complete tokens are excluded.

2. Frozen execution
   - Frozen SOP content can replace only a SOP that remains visible to the employee; it cannot resurrect revoked access.
   - Knowledge capabilities are narrowed to captured version IDs.
   - Tool invocation remains authorized only if the current invocation digest equals the launch digest. Drift fails closed rather than replaying obsolete credentials.
   - Employee persona and action budget come from the snapshot.

3. Workload authentication and authorization
   - Each role has a distinct Casdoor application/client ID and one StaffDeck identity mapping.
   - Casdoor JWT signature, issuer, audience, issued-at and expiry are validated.
   - Issuer, token endpoint and JWKS URI are pinned to trusted deployment configuration before the Client Secret is loaded, preventing database-field tampering from redirecting a secret to an attacker endpoint.
   - The Secret Store record's client ID must match the mapped identity client ID.
   - Casdoor authentication does not grant business access. Tenant, employee, role, task generation, capability binding, tool digest, Casbin policy and RLS checks remain authoritative.

4. Secret governance
   - Long-lived secrets are stored outside the repository at `D:\saas\runtime\staffdeck-secrets\agent-m2m.json`.
   - Windows ACL verification showed only the current runtime account and `SYSTEM`, both Full Control; inherited ACLs are removed.
   - StaffDeck schema inspection found no `client_secret`, `access_token`, `refresh_token` or `id_token` columns.
   - Runtime and Worker database roles can update only service-identity verification receipt columns. Protected identity configuration columns reject updates.

5. Database isolation and immutability
   - New tables have FORCE RLS.
   - No-tenant and wrong-tenant identity reads returned no rows.
   - Runtime protected-column mutation was denied; receipt-column update succeeded.
   - Snapshot update was rejected by the append-only database trigger.
   - Runtime may SELECT/INSERT snapshots but cannot UPDATE/DELETE them.

## Deterministic evidence

| Gate | Result | Notes |
|---|---|---|
| Focused backend tests | PASS | 10 passed: task worker/fencing, snapshot versions/no-secret, endpoint pinning and credential binding |
| Existing work-task tests | PASS | Included in focused suite |
| Work-task Ruff checks | PASS | New/changed work-task modules, scripts and tests |
| Frontend production build | PASS | TypeScript project build and Vite bundle completed |
| PostgreSQL migration rerun | PASS | Idempotent rerun succeeded; RLS, trigger and column grants active |
| Seven live Client Credentials exchanges | PASS | 7 verified JWTs, 7 agents, 7 distinct clients; no secret/token output |
| Sandbox end-to-end task | PASS | Fresh task `worktask_5dd423a021d54341` reached review with Run/snapshot/M2M receipt and no persisted secret-shaped fields |
| Snapshot immutability | PASS | No-op UPDATE rejected by PostgreSQL trigger |
| Tenant RLS and protected columns | PASS | No-context and cross-tenant reads denied; protected config UPDATE denied |
| Application health | PASS | `http://127.0.0.1:5173/api/health` returned `status=ok` |
| Broad Harness regression suite | PARTIAL | 99 passed, 1 failed in a pre-existing published-deliverable read test with corrupted fixture text; failure is outside the changed execution-snapshot path but prevents a completely green broad gate |
| Formal independent verifier | NOT AVAILABLE | No immutable Git target and no separate read-only verifier in this task |

## Review finding fixed during this task

High: the first M2M broker draft trusted `token_endpoint` from the business database. A compromised configuration row could have redirected a Client Secret. The final implementation rejects any issuer/token/JWKS mismatch against deployment configuration before secret access and adds a negative test proving no HTTP request is made to an untrusted endpoint.

Medium: the first PostgreSQL end-to-end run exposed ORM flush ordering because migration-only foreign keys were not visible to SQLAlchemy. The transaction rolled back without partial data. The final worker explicitly flushes session/task, then Run, then append-only snapshot; unit and PostgreSQL end-to-end checks pass.

## Current limitations and release blockers

- The seven role employees currently have zero reviewed SOP, knowledge-base or tool bindings. Snapshots correctly display empty capability sets. Binding production capabilities is the next product phase and must be reviewed role by role.
- Worker execution still runs in local sandbox. External marketplace, carrier, advertising and supplier writes remain disabled.
- A separate non-public Worker process and workload-specific Casbin decision at every tool invocation should be completed before live mode.
- Client-secret rotation, overlap/revocation runbook and a production Vault/KMS integration are not implemented.
- The broad Harness suite has one unrelated failing test, so a fully green repository-wide test gate has not been demonstrated.
- No formal independent verification or accountable human production approval exists.

## Rollback and containment

- Immediate containment: keep `WORK_TASK_EXECUTION_MODE=sandbox` or disable `WORK_TASK_EXECUTION_ENABLED`; no external business side effects have been enabled.
- Identity containment: set affected `agent_service_identities.status=disabled` and disable the corresponding Casdoor application. Running live execution checks identity state at the next stream checkpoint.
- Application rollback: restore the timestamped local configuration/SQLite snapshot at `D:\saas\backups\staffdeck-sqlite-20260902-094958` using the existing rollback workflow if the entire PostgreSQL cutover must be reversed.
- Schema down migration is destructive because it drops snapshot/identity history. Do not run it after material production history exists without an approved export/retention plan.

## Handoff

Recommended next phase: define and approve a least-privilege capability matrix, then bind role-specific read-only SOPs, knowledge bases and tools to the seven employees. Create one sandbox task per role and assert non-empty version receipts, binding revocation, tool-digest drift, employee disable and service-identity disable behavior before considering live mode.
