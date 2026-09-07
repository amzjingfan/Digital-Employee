BEGIN;

DROP TABLE IF EXISTS public.work_task_runs;
ALTER TABLE public.work_tasks
  DROP CONSTRAINT IF EXISTS work_tasks_control_mode_check,
  DROP CONSTRAINT IF EXISTS work_tasks_execution_counts_check,
  DROP COLUMN IF EXISTS control_mode,
  DROP COLUMN IF EXISTS cancel_requested,
  DROP COLUMN IF EXISTS lease_owner,
  DROP COLUMN IF EXISTS lease_expires_at,
  DROP COLUMN IF EXISTS execution_generation,
  DROP COLUMN IF EXISTS attempt_count,
  DROP COLUMN IF EXISTS max_attempts,
  DROP COLUMN IF EXISTS next_attempt_at,
  DROP COLUMN IF EXISTS latest_session_id,
  DROP COLUMN IF EXISTS taken_over_by_user_id,
  DROP COLUMN IF EXISTS taken_over_at,
  DROP COLUMN IF EXISTS last_error_code,
  DROP COLUMN IF EXISTS last_error_message,
  DROP COLUMN IF EXISTS result_summary;
DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260901_work_task_execution_v1';

COMMIT;
