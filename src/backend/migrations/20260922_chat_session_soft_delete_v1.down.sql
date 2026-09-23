BEGIN;

ALTER TABLE public.work_task_runs
  DROP CONSTRAINT IF EXISTS work_task_runs_session_fk;

ALTER TABLE public.work_task_runs
  ADD CONSTRAINT work_task_runs_session_fk
  FOREIGN KEY (session_id) REFERENCES public.sessions (id) ON DELETE RESTRICT;

ALTER TABLE public.sessions
  DROP CONSTRAINT IF EXISTS uq_sessions_tenant_id_id;

DROP INDEX IF EXISTS public.ix_sessions_deleted_at;

ALTER TABLE public.sessions
  DROP COLUMN IF EXISTS deleted_at;

COMMIT;
