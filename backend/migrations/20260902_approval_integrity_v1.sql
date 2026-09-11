BEGIN;

ALTER TABLE public.business_resources
  ADD COLUMN IF NOT EXISTS revision integer NOT NULL DEFAULT 1;

ALTER TABLE public.high_risk_action_requests
  ADD COLUMN IF NOT EXISTS content_digest varchar NOT NULL DEFAULT 'legacy-unverified',
  ADD COLUMN IF NOT EXISTS resource_snapshot_digest varchar NOT NULL DEFAULT 'legacy-unverified',
  ADD COLUMN IF NOT EXISTS invalidated_at timestamp without time zone,
  ADD COLUMN IF NOT EXISTS invalidation_reason varchar;

ALTER TABLE public.business_action_executions
  ADD COLUMN IF NOT EXISTS approval_content_digest varchar NOT NULL DEFAULT 'legacy-unverified',
  ADD COLUMN IF NOT EXISTS resource_snapshot_digest varchar NOT NULL DEFAULT 'legacy-unverified';

ALTER TABLE public.high_risk_action_requests
  DROP CONSTRAINT IF EXISTS high_risk_action_requests_status_check;
ALTER TABLE public.high_risk_action_requests
  ADD CONSTRAINT high_risk_action_requests_status_check
  CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled', 'invalidated'));

ALTER TABLE public.high_risk_action_events
  DROP CONSTRAINT IF EXISTS high_risk_action_events_type_check;
ALTER TABLE public.high_risk_action_events
  ADD CONSTRAINT high_risk_action_events_type_check
  CHECK (event_type IN ('requested', 'approved', 'rejected', 'cancelled', 'invalidated'));

WITH invalidated AS (
  UPDATE public.high_risk_action_requests AS request
  SET status = 'invalidated',
      invalidated_at = now(),
      invalidation_reason = 'legacy_approval_has_no_integrity_snapshot',
      updated_at = now()
  WHERE request.status IN ('pending', 'approved')
    AND NOT EXISTS (
      SELECT 1
      FROM public.business_action_executions AS execution
      WHERE execution.tenant_id = request.tenant_id
        AND execution.request_id = request.id
        AND execution.status IN ('succeeded', 'compensated')
    )
  RETURNING request.id, request.tenant_id
)
INSERT INTO public.high_risk_action_events (
  id,
  tenant_id,
  request_id,
  event_type,
  actor_user_id,
  actor_business_role,
  detail_json,
  occurred_at
)
SELECT
  'approval_event_migration_' || substr(md5(id), 1, 16),
  tenant_id,
  id,
  'invalidated',
  'system',
  'system',
  json_build_object(
    'reason', 'legacy_approval_has_no_integrity_snapshot',
    'phase', 'schema_migration'
  ),
  now()
FROM invalidated;

UPDATE public.business_action_executions AS execution
SET status = CASE
      WHEN execution.status IN ('running', 'compensating', 'manual_resolution_required')
        THEN 'manual_resolution_required'
      ELSE 'failed'
    END,
    next_attempt_at = NULL,
    lease_owner = NULL,
    lease_expires_at = NULL,
    execution_generation = execution.execution_generation + 1,
    last_error_code = 'approval_invalidated',
    last_error_message = 'Legacy approval has no integrity snapshot; submit a new request',
    updated_at = now()
FROM public.high_risk_action_requests AS request
WHERE request.tenant_id = execution.tenant_id
  AND request.id = execution.request_id
  AND request.status = 'invalidated'
  AND execution.status NOT IN ('succeeded', 'compensated');

ALTER TABLE public.business_resources
  DROP CONSTRAINT IF EXISTS business_resources_revision_check;
ALTER TABLE public.business_resources
  ADD CONSTRAINT business_resources_revision_check CHECK (revision > 0);

CREATE INDEX IF NOT EXISTS ix_high_risk_action_requests_content_digest
  ON public.high_risk_action_requests (content_digest);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_requests_resource_snapshot_digest
  ON public.high_risk_action_requests (resource_snapshot_digest);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_requests_invalidated_at
  ON public.high_risk_action_requests (invalidated_at DESC);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_approval_content_digest
  ON public.business_action_executions (approval_content_digest);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_resource_snapshot_digest
  ON public.business_action_executions (resource_snapshot_digest);

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260902_approval_integrity_v1', now(), 'postgresql', 3, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
