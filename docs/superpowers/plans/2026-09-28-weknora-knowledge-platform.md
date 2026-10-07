# WeKnora Knowledge Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Joukir knowledge retrieval with an independently deployed WeKnora-based knowledge platform that also serves other systems through authorized document, search, cited-answer, and file-import APIs.

**Architecture:** WeKnora owns content parsing, indexing, retrieval, and native knowledge chat. An independent Knowledge API owns cross-system identity, KB catalog, grants, stable contracts, import jobs, and cross-workspace routing. Joukir becomes one consumer with a migration adapter and a staged cutover.

**Tech Stack:** WeKnora pinned release/commit and its supported deployment stack; standalone Python 3.11+ FastAPI Knowledge API with PostgreSQL; Joukir FastAPI/Harness v2; pytest and HTTP contract tests.

**Spec:** [WeKnora 独立知识平台设计](../specs/2026-09-28-weknora-knowledge-platform-design.md)

## Global Constraints

- First release accepts file imports only; URL, Markdown, FAQ, and connector ingestion remain versioned contract reservations.
- Company shared and tenant private workspaces are separate ownership and access boundaries. Client requests always use logical KB keys; the server resolves WeKnora IDs.
- Read, search, QA, download, and ingest grants are distinct. Unauthorised KB IDs fail closed. Do not distribute platform-level WeKnora keys to consumers.
- QA is based only on selected KBs, with references, and never uses Joukir digital-employee persona, SOPs, tools, or web search.
- Preserve existing Joukir version/snapshot audit semantics before switching work-task traffic.
- Keep all new executable tests under `src/tests/`; no credentials or raw file contents in logs or tracked fixtures.

## Review Focus

- A request mixing allowed and forbidden KB keys must return 403 without querying either KB (Task 3).
- A tenant A client must not retrieve tenant B content by guessing WeKnora document/chunk IDs (Task 3).
- Retrying a file upload after timeout must return the original job, and a failed replacement must leave the old document active (Task 4).
- A cited answer with no evidence must return an explicit insufficient-evidence outcome (Task 5).
- A Joukir task started before a KB update must retain its recorded citations and source digest afterward (Task 6).

---

### Task 1: Freeze target and prove WeKnora behavior

**Files:** create `docs/runbooks/weknora-poc.md`; create `src/tests/integration/weknora_contract/` for opt-in contract probes; add a link in `docs/README.md`.

**Interfaces:** Produce a checked table of the target version's file upload, parse status, document preview/download, chunks, knowledge-search, knowledge-chat/SSE, shared KB access, and API-key limitations. Record image/commit digest, enabled components, model IDs by role (without secrets), and POC result.

- [ ] Deploy isolated WeKnora using a pinned image/commit, separate storage and database, and selected parsing/embedding/rerank/answer models.
- [ ] Create company shared, tenant A, and tenant B workspaces; upload small representative PDF, DOCX, and Markdown files. Include a scanned file only if it is in the actual corpus.
- [ ] Run positive and negative calls with scoped machine keys: A own KB, A shared KB, A denied B KB, shared KB discovery, preview, raw download, chunk locators, and cited QA.
- [ ] Test one query covering shared + private KB; if native QA cannot do it with scoped keys, record the separate-retrieval + answer-layer path as the implementation choice.
- [ ] Verify parse completion, duplicate 409, malformed file, queued/failed status, SSE complete/error, and restart recovery. Save status codes and redacted evidence only.
- [ ] **Gate:** No platform or Joukir implementation starts until the POC table says which calls work in the pinned version and how shared/private combined QA is achieved.

### Task 2: Standalone service and authorization catalog

**Files:** create `src/knowledge-platform/` as an independently deployed FastAPI service; create its package/deployment files; create PostgreSQL migrations under that service; test in `src/tests/backend/test_knowledge_platform_catalog.py` and isolated PostgreSQL integration tests.

**Interfaces:** `resolve_allowed_bases(client_id, operation, logical_keys) -> list[ResolvedBase]` returns owner workspace, WeKnora KB ID, active revision, and source scope; `resolve_document(client_id, operation, document_id) -> ResolvedDocument` validates ownership. Records: client, grant, logical KB, import job, source document mapping.

- [ ] Write failing tests for default-deny, distinct download/ingest grants, disabled key, revoked grant, same logical key in different owner scopes, and guessed document ID.
- [ ] Add schema/migrations with unique logical key per owner scope, explicit foreign keys, forced PostgreSQL RLS for tenant data, and secret references only.
- [ ] Implement identity validation for machine callers and authorization resolution before WeKnora calls. Service-to-WeKnora credentials are held in runtime secret storage, one workspace scope per credential.
- [ ] Verify migration forward/back in a disposable PostgreSQL instance, auth tests, and no cross-tenant reads.

### Task 3: Stable read API and retrieval

**Files:** create service modules for catalog/document/read/search routes and a WeKnora HTTP adapter under `src/knowledge-platform/`; test in `src/tests/backend/test_knowledge_platform_read.py` and contract probes.

**Interfaces:** Implement the spec's `GET /v1/knowledge-bases`, document list/detail/content/chunks/file, and `POST /v1/search`. Search body: `{query, knowledge_base_keys, limit}`; hit: `{kb_key, document_id, chunk_id, content, score, source_locators, content_digest}`. Require nonempty KB keys; cap limit and query length in the contract.

- [ ] Write failing tests for allowed list, pagination, forbidden KB mixed with allowed KB, guessed ID, unavailable original file, and scoped-key file-access limitation.
- [ ] Implement read-through mapping to WeKnora list, preview, chunk and download APIs. Stream source files; never put source bytes in response logs.
- [ ] Implement single-workspace search through WeKnora `knowledge-search`. For a cross-workspace selection, query each authorized workspace separately and combine with deterministic ranking; if score scales differ, rerank the merged text rather than comparing raw scores.
- [ ] Verify API contract tests against the pinned WeKnora instance and error translation for 401/403/404/409/429/503.

### Task 4: File import jobs

**Files:** create service import route/worker/ledger modules; test in `src/tests/backend/test_knowledge_platform_import.py` and one live WeKnora import probe.

**Interfaces:** `POST /v1/imports/files` accepts multipart file, target logical KB key, `source_system`, `source_record_id`, `source_version`, and `Idempotency-Key`; returns `{job_id,status}` with 202. `GET /v1/imports/{job_id}` returns `{status,document_id,error_code}`. Define job states `queued/uploading/parsing/completed/failed`.

- [ ] Write failing tests for idempotent retry, same name with new content, forbidden target, unsupported/oversized file, upload timeout, parsing failure, and failed replacement retaining active old mapping.
- [ ] Stream file to bounded staging storage, calculate SHA-256, create ledger entry transactionally, and enqueue upload. Do not base64-encode entire files into a database job payload.
- [ ] Upload using WeKnora's file endpoint, persist knowledge ID, poll its parse status with bounded backoff, and mark completion only after indexed/ready verification.
- [ ] Expose per-file batch results and safe retry. Add job age, queue depth, failure count and processing duration metrics.
- [ ] Verify restart resumes incomplete jobs and duplicate requests return the prior job without duplicate WeKnora content.

### Task 5: Cited knowledge-only answer API

**Files:** create service answer route/SSE mapper and, only if POC requires it, a small evidence-bound answer component; test in `src/tests/backend/test_knowledge_platform_answers.py` and a live SSE probe.

**Interfaces:** `POST /v1/answers:stream` body `{question, knowledge_base_keys, conversation_id?}`. Emit `answer`, `references`, `complete`, or `error` events. Every reference contains KB key, document/chunk IDs, cited text, locator, and digest.

- [ ] Write failing tests for missing KBs, unauthorized mixed scope, no evidence, broken upstream SSE, stale citation, and answer text without references.
- [ ] For POC-proven native combined query, create/reuse WeKnora session and call `knowledge-chat` with explicit authorized KB IDs and agent mode off.
- [ ] Otherwise retrieve per workspace, rerank and de-duplicate evidence, then answer only from the selected snippets with citation IDs checked against the evidence set. Return insufficient evidence when none survives.
- [ ] Persist request ID, selected KB revision, evidence IDs/digests and result status for audit; do not persist secrets or raw authorization headers.
- [ ] Verify the client receives a terminal event, references resolve to authorized documents, and no tool/web/agent call is made.

### Task 6: Joukir migration adapter and staged cutover

**Files:** modify `src/backend/app/capabilities/` knowledge provider/registry, `src/backend/app/core/harness_capability_invoker.py`, knowledge binding and public API compatibility paths; add focused tests under `src/tests/backend/` and any required PostgreSQL migration in `src/backend/migrations/`.

**Interfaces:** Map `(joukir_tenant_id, agent_id, local_kb_id)` to a logical KB key and provider. Both Harness tool invocation and `KnowledgeRuntime.search` must use the same provider selector. Persist per-task selected KB revision and per-query evidence snapshot.

- [ ] Inventory local KBs, versions, documents, file availability and owners; generate a migration manifest with `migratable/source-needed/unrecoverable` states.
- [ ] Write failing tests for tenant/agent binding, shared KB visibility, task snapshot after external KB update, citation persistence, provider outage, and public agent-scoped API compatibility.
- [ ] Implement external provider and route all Joukir knowledge call sites through it under a per-tenant/agent feature flag. Keep current local provider for unswitched traffic.
- [ ] Re-import only recoverable approved source files through the Knowledge API; verify per-file checksum, parse status and representative retrieval results. Do not infer original bytes from legacy chunks.
- [ ] Compare old/new retrieval on a fixed question set and citations; pilot one tenant and one company shared KB, then expand by tenant. Rollback changes provider binding; preserve already imported WeKnora content.
- [ ] Verify focused backend/Harness tests, PostgreSQL security tests, public API contract tests, target WeKnora integration, and role-based browser checks for the Joukir knowledge route.

### Task 7: Release and operating controls

**Files:** create `docs/runbooks/weknora-operations.md`; update service deploy/monitoring and docs index.

- [ ] Set backup/restore for WeKnora metadata, object storage, index data and Knowledge API catalog/ledger; execute one restore drill in isolation.
- [ ] Configure quotas, upload limits, MIME checks, malware screening hook, rate limits, SSE proxy timeouts, audit retention, and key rotation.
- [ ] Run load tests for target corpus size/concurrent searches/imports and observe queue depth, p95 latency, failure rate, citation resolution and cross-tenant denials.
- [ ] Complete real machine-client acceptance for two distinct systems and tenant A/B; verify raw download is denied unless separately granted.
- [ ] Record go/no-go evidence and exact rollback mapping; only then retire old Joukir knowledge ingestion/retrieval paths after the retention period.

## Delivery order

Task 1 is the mandatory technical gate. Tasks 2–5 produce a usable platform for systems other than Joukir. Task 6 migrates Joukir independently. Task 7 completes production readiness. URL/FAQ/connector adapters start only after the file path is stable and a real source system exists.
