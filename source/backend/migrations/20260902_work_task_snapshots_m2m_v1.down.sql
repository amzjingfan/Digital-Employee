BEGIN;

DROP TABLE IF EXISTS public.work_task_execution_snapshots;
ALTER TABLE public.work_task_runs
  DROP CONSTRAINT IF EXISTS work_task_runs_service_identity_fk,
  DROP COLUMN IF EXISTS service_identity_id,
  DROP COLUMN IF EXISTS execution_snapshot_id,
  DROP COLUMN IF EXISTS snapshot_digest;
DROP TABLE IF EXISTS public.agent_service_identities;
DROP FUNCTION IF EXISTS app.reject_work_task_snapshot_mutation();
DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260902_work_task_snapshots_m2m_v1';

COMMIT;
