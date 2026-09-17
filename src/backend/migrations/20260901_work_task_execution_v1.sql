BEGIN;

ALTER TABLE public.work_tasks
  ADD COLUMN IF NOT EXISTS control_mode varchar NOT NULL DEFAULT 'agent',
  ADD COLUMN IF NOT EXISTS cancel_requested boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS lease_owner varchar,
  ADD COLUMN IF NOT EXISTS lease_expires_at timestamp without time zone,
  ADD COLUMN IF NOT EXISTS execution_generation integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS attempt_count integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_attempts integer NOT NULL DEFAULT 3,
  ADD COLUMN IF NOT EXISTS next_attempt_at timestamp without time zone,
  ADD COLUMN IF NOT EXISTS latest_session_id varchar,
  ADD COLUMN IF NOT EXISTS taken_over_by_user_id varchar,
  ADD COLUMN IF NOT EXISTS taken_over_at timestamp without time zone,
  ADD COLUMN IF NOT EXISTS last_error_code varchar,
  ADD COLUMN IF NOT EXISTS last_error_message varchar,
  ADD COLUMN IF NOT EXISTS result_summary varchar;

DO $work_task_constraints$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'work_tasks_control_mode_check'
  ) THEN
    ALTER TABLE public.work_tasks
      ADD CONSTRAINT work_tasks_control_mode_check CHECK (control_mode IN ('agent', 'human'));
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'work_tasks_execution_counts_check'
  ) THEN
    ALTER TABLE public.work_tasks
      ADD CONSTRAINT work_tasks_execution_counts_check
      CHECK (execution_generation >= 0 AND attempt_count >= 0 AND max_attempts BETWEEN 1 AND 10);
  END IF;
END
$work_task_constraints$;

CREATE TABLE IF NOT EXISTS public.work_task_runs (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  task_id varchar NOT NULL,
  attempt_no integer NOT NULL,
  generation integer NOT NULL,
  agent_id varchar NOT NULL,
  session_id varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'running',
  execution_mode varchar NOT NULL DEFAULT 'sandbox',
  result_summary varchar,
  error_code varchar,
  error_message varchar,
  trace_json json NOT NULL DEFAULT '{}'::json,
  started_at timestamp without time zone NOT NULL,
  finished_at timestamp without time zone,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_work_task_run_attempt UNIQUE (tenant_id, task_id, attempt_no),
  CONSTRAINT work_task_runs_status_check CHECK (
    status IN ('running', 'succeeded', 'retrying', 'failed', 'cancelled', 'stale')
  ),
  CONSTRAINT work_task_runs_execution_mode_check CHECK (execution_mode IN ('sandbox', 'live')),
  CONSTRAINT work_task_runs_attempt_check CHECK (attempt_no > 0 AND generation > 0),
  CONSTRAINT work_task_runs_task_fk
    FOREIGN KEY (task_id) REFERENCES public.work_tasks(id) ON DELETE RESTRICT,
  CONSTRAINT work_task_runs_session_fk
    FOREIGN KEY (session_id) REFERENCES public.sessions(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_work_tasks_control_mode ON public.work_tasks (control_mode);
CREATE INDEX IF NOT EXISTS ix_work_tasks_cancel_requested ON public.work_tasks (cancel_requested);
CREATE INDEX IF NOT EXISTS ix_work_tasks_lease_owner ON public.work_tasks (lease_owner);
CREATE INDEX IF NOT EXISTS ix_work_tasks_lease_expires_at ON public.work_tasks (lease_expires_at);
CREATE INDEX IF NOT EXISTS ix_work_tasks_next_attempt_at ON public.work_tasks (next_attempt_at);
CREATE INDEX IF NOT EXISTS ix_work_tasks_latest_session_id ON public.work_tasks (latest_session_id);
CREATE INDEX IF NOT EXISTS ix_work_tasks_taken_over_by_user_id ON public.work_tasks (taken_over_by_user_id);
CREATE INDEX IF NOT EXISTS ix_work_tasks_last_error_code ON public.work_tasks (last_error_code);
CREATE INDEX IF NOT EXISTS ix_work_tasks_execution_queue
  ON public.work_tasks (tenant_id, control_mode, status, next_attempt_at);

CREATE INDEX IF NOT EXISTS ix_work_task_runs_tenant_id ON public.work_task_runs (tenant_id);
CREATE INDEX IF NOT EXISTS ix_work_task_runs_task_id ON public.work_task_runs (task_id);
CREATE INDEX IF NOT EXISTS ix_work_task_runs_attempt_no ON public.work_task_runs (attempt_no);
CREATE INDEX IF NOT EXISTS ix_work_task_runs_generation ON public.work_task_runs (generation);
CREATE INDEX IF NOT EXISTS ix_work_task_runs_agent_id ON public.work_task_runs (agent_id);
CREATE INDEX IF NOT EXISTS ix_work_task_runs_session_id ON public.work_task_runs (session_id);
CREATE INDEX IF NOT EXISTS ix_work_task_runs_status ON public.work_task_runs (status);
CREATE INDEX IF NOT EXISTS ix_work_task_runs_execution_mode ON public.work_task_runs (execution_mode);
CREATE INDEX IF NOT EXISTS ix_work_task_runs_error_code ON public.work_task_runs (error_code);
CREATE INDEX IF NOT EXISTS ix_work_task_runs_started_at ON public.work_task_runs (started_at);
CREATE INDEX IF NOT EXISTS ix_work_task_runs_finished_at ON public.work_task_runs (finished_at);
CREATE INDEX IF NOT EXISTS ix_work_task_runs_created_at ON public.work_task_runs (created_at);
CREATE INDEX IF NOT EXISTS ix_work_task_runs_task_time
  ON public.work_task_runs (task_id, created_at DESC);

ALTER TABLE public.work_task_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.work_task_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.work_task_runs;
CREATE POLICY runtime_tenant_isolation ON public.work_task_runs
FOR ALL TO staffdeck_runtime
USING (tenant_id = app.current_staffdeck_tenant_id())
WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
DROP POLICY IF EXISTS worker_all_tenants ON public.work_task_runs;
CREATE POLICY worker_all_tenants ON public.work_task_runs
FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

REVOKE ALL ON public.work_task_runs FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON public.work_task_runs TO staffdeck_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.work_task_runs TO staffdeck_worker;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260901_work_task_execution_v1', now(), 'postgresql', 1, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
