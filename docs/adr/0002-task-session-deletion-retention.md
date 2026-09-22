# ADR 0002: Preserve task execution evidence when users delete conversations

- Date: 2026-09-22
- Status: Accepted

## Context

`WorkTaskRun` is durable execution and audit evidence linked to the `ChatSession` used by a digital employee. PostgreSQL deliberately enforces `work_task_runs_session_fk` with `ON DELETE RESTRICT`. The original chat deletion path tried to physically delete every session, so deleting a task-generated conversation failed with HTTP 500. User-facing deletion still needs to remove the conversation from chat without weakening tenant isolation or destroying execution evidence.

## Decision

Ordinary user conversations continue to be physically deleted with their dependent chat and Harness records. When a same-tenant `WorkTaskRun` references a conversation, user deletion instead sets `ChatSession.deleted_at`. Soft-deleted sessions are excluded from user chat lists and treated as not found by centralized chat read, update, delete, and turn guards. Messages, Harness records, workspaces, task runs, and the session row remain available to internal execution and enterprise audit paths.

The `work_task_runs_session_fk ON DELETE RESTRICT` constraint remains unchanged. Tenant ID and session ID together determine whether task evidence protects a session.

## Alternatives considered

- Cascade-delete `WorkTaskRun` rows with the conversation: rejected because it destroys durable execution and audit evidence.
- Drop the foreign key or use `ON DELETE SET NULL`: rejected because it weakens traceability between a run and the exact execution conversation.
- Return a conflict response and refuse deletion: rejected because it preserves the data but does not satisfy the user's delete action or remove the conversation from chat.
- Soft-delete every conversation: rejected because ordinary chats can retain the existing physical deletion and storage-removal semantics.

## Consequences

- Existing databases require the reversible `sessions.deleted_at` migration before deploying the updated service.
- User chat endpoints must consistently apply the deleted-session guard; enterprise audit and worker code intentionally retain internal access.
- Rolling back the schema removes deletion markers and can make retained task conversations visible again, so application rollback and migration rollback must be coordinated.
- Any future physical retention job for task conversations must define an explicit audit-retention period and remove or archive task evidence before attempting to delete the session.

## Evidence

- [Migration](../../src/backend/migrations/20260922_chat_session_soft_delete_v1.sql)
- [Session cleanup implementation](../../src/backend/app/session/cleanup.py)
- [Regression tests](../../src/tests/backend/test_harness_session_cleanup.py)
- [Original audit finding](../reports/报告.md)
