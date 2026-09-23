BEGIN;

ALTER TABLE public.sessions
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITHOUT TIME ZONE;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'uq_sessions_tenant_id_id'
      AND conrelid = 'public.sessions'::regclass
  ) THEN
    ALTER TABLE public.sessions
      ADD CONSTRAINT uq_sessions_tenant_id_id UNIQUE (tenant_id, id);
  END IF;
END
$$;

ALTER TABLE public.work_task_runs
  DROP CONSTRAINT IF EXISTS work_task_runs_session_fk;

ALTER TABLE public.work_task_runs
  ADD CONSTRAINT work_task_runs_session_fk
  FOREIGN KEY (tenant_id, session_id)
  REFERENCES public.sessions (tenant_id, id) ON DELETE RESTRICT;

CREATE INDEX IF NOT EXISTS ix_sessions_deleted_at
  ON public.sessions (deleted_at);

COMMIT;
