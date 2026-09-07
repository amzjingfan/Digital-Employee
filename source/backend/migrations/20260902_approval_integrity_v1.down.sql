BEGIN;

ALTER TABLE public.high_risk_action_requests
  DROP CONSTRAINT IF EXISTS high_risk_action_requests_status_check;
ALTER TABLE public.high_risk_action_events
  DROP CONSTRAINT IF EXISTS high_risk_action_events_type_check;

DELETE FROM public.high_risk_action_events
WHERE event_type = 'invalidated';
UPDATE public.high_risk_action_requests
SET status = 'cancelled'
WHERE status = 'invalidated';

ALTER TABLE public.high_risk_action_requests
  ADD CONSTRAINT high_risk_action_requests_status_check
  CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled'));
ALTER TABLE public.high_risk_action_events
  ADD CONSTRAINT high_risk_action_events_type_check
  CHECK (event_type IN ('requested', 'approved', 'rejected', 'cancelled'));

ALTER TABLE public.business_action_executions
  DROP COLUMN IF EXISTS approval_content_digest,
  DROP COLUMN IF EXISTS resource_snapshot_digest;
ALTER TABLE public.high_risk_action_requests
  DROP COLUMN IF EXISTS content_digest,
  DROP COLUMN IF EXISTS resource_snapshot_digest,
  DROP COLUMN IF EXISTS invalidated_at,
  DROP COLUMN IF EXISTS invalidation_reason;
ALTER TABLE public.business_resources
  DROP CONSTRAINT IF EXISTS business_resources_revision_check,
  DROP COLUMN IF EXISTS revision;

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260902_approval_integrity_v1';

COMMIT;
