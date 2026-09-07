BEGIN;

CREATE TABLE IF NOT EXISTS public.work_tasks (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  idempotency_key varchar NOT NULL,
  source_type varchar NOT NULL DEFAULT 'manual',
  source_id varchar,
  source_report_id varchar,
  title varchar NOT NULL,
  description varchar,
  owner_business_role varchar NOT NULL,
  assignee_agent_id varchar,
  assigned_by_user_id varchar NOT NULL,
  priority varchar NOT NULL DEFAULT 'normal',
  risk_level varchar NOT NULL DEFAULT 'medium',
  status varchar NOT NULL DEFAULT 'pending',
  scope_json json NOT NULL DEFAULT '{}'::json,
  input_json json NOT NULL DEFAULT '{}'::json,
  due_at timestamp without time zone,
  started_at timestamp without time zone,
  completed_at timestamp without time zone,
  version integer NOT NULL DEFAULT 0,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_work_task_idempotency UNIQUE (tenant_id, idempotency_key),
  CONSTRAINT work_tasks_status_check CHECK (
    status IN ('pending', 'in_progress', 'waiting_input', 'review', 'completed',
               'failed', 'cancelled', 'archived')
  ),
  CONSTRAINT work_tasks_priority_check CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
  CONSTRAINT work_tasks_risk_check CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
  CONSTRAINT work_tasks_version_check CHECK (version >= 0),
  CONSTRAINT work_tasks_report_fk
    FOREIGN KEY (source_report_id) REFERENCES public.operations_reports(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS public.work_task_evidence (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  task_id varchar NOT NULL,
  source_type varchar NOT NULL,
  source_id varchar NOT NULL,
  severity varchar NOT NULL DEFAULT 'info',
  label varchar NOT NULL,
  summary varchar NOT NULL,
  source_route varchar NOT NULL,
  occurred_at timestamp without time zone NOT NULL,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_work_task_evidence UNIQUE (tenant_id, task_id, source_type, source_id),
  CONSTRAINT work_task_evidence_task_fk
    FOREIGN KEY (task_id) REFERENCES public.work_tasks(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS public.work_task_events (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  task_id varchar NOT NULL,
  event_type varchar NOT NULL,
  actor_type varchar NOT NULL DEFAULT 'human',
  actor_id varchar,
  actor_business_role varchar,
  from_status varchar,
  to_status varchar,
  detail_json json NOT NULL DEFAULT '{}'::json,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT work_task_events_task_fk
    FOREIGN KEY (task_id) REFERENCES public.work_tasks(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_work_tasks_tenant_id ON public.work_tasks (tenant_id);
CREATE INDEX IF NOT EXISTS ix_work_tasks_idempotency_key ON public.work_tasks (idempotency_key);
CREATE INDEX IF NOT EXISTS ix_work_tasks_source_type ON public.work_tasks (source_type);
CREATE INDEX IF NOT EXISTS ix_work_tasks_source_id ON public.work_tasks (source_id);
CREATE INDEX IF NOT EXISTS ix_work_tasks_source_report_id ON public.work_tasks (source_report_id);
CREATE INDEX IF NOT EXISTS ix_work_tasks_owner_business_role ON public.work_tasks (owner_business_role);
CREATE INDEX IF NOT EXISTS ix_work_tasks_assignee_agent_id ON public.work_tasks (assignee_agent_id);
CREATE INDEX IF NOT EXISTS ix_work_tasks_assigned_by_user_id ON public.work_tasks (assigned_by_user_id);
CREATE INDEX IF NOT EXISTS ix_work_tasks_priority ON public.work_tasks (priority);
CREATE INDEX IF NOT EXISTS ix_work_tasks_risk_level ON public.work_tasks (risk_level);
CREATE INDEX IF NOT EXISTS ix_work_tasks_status ON public.work_tasks (status);
CREATE INDEX IF NOT EXISTS ix_work_tasks_due_at ON public.work_tasks (due_at);
CREATE INDEX IF NOT EXISTS ix_work_tasks_created_at ON public.work_tasks (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_work_tasks_tenant_role_status
  ON public.work_tasks (tenant_id, owner_business_role, status);
CREATE INDEX IF NOT EXISTS ix_work_tasks_tenant_due ON public.work_tasks (tenant_id, due_at);
CREATE INDEX IF NOT EXISTS ix_work_task_evidence_tenant_id ON public.work_task_evidence (tenant_id);
CREATE INDEX IF NOT EXISTS ix_work_task_evidence_task_id ON public.work_task_evidence (task_id);
CREATE INDEX IF NOT EXISTS ix_work_task_evidence_source_type ON public.work_task_evidence (source_type);
CREATE INDEX IF NOT EXISTS ix_work_task_evidence_source_id ON public.work_task_evidence (source_id);
CREATE INDEX IF NOT EXISTS ix_work_task_evidence_severity ON public.work_task_evidence (severity);
CREATE INDEX IF NOT EXISTS ix_work_task_evidence_task_time
  ON public.work_task_evidence (task_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_work_task_events_tenant_id ON public.work_task_events (tenant_id);
CREATE INDEX IF NOT EXISTS ix_work_task_events_task_id ON public.work_task_events (task_id);
CREATE INDEX IF NOT EXISTS ix_work_task_events_event_type ON public.work_task_events (event_type);
CREATE INDEX IF NOT EXISTS ix_work_task_events_actor_id ON public.work_task_events (actor_id);
CREATE INDEX IF NOT EXISTS ix_work_task_events_task_time
  ON public.work_task_events (task_id, created_at);

CREATE OR REPLACE FUNCTION app.reject_work_task_append_only_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'work task evidence and events are append-only';
END;
$$;

DROP TRIGGER IF EXISTS work_task_evidence_append_only ON public.work_task_evidence;
CREATE TRIGGER work_task_evidence_append_only
BEFORE UPDATE OR DELETE ON public.work_task_evidence
FOR EACH ROW EXECUTE FUNCTION app.reject_work_task_append_only_mutation();

DROP TRIGGER IF EXISTS work_task_events_append_only ON public.work_task_events;
CREATE TRIGGER work_task_events_append_only
BEFORE UPDATE OR DELETE ON public.work_task_events
FOR EACH ROW EXECUTE FUNCTION app.reject_work_task_append_only_mutation();

DO $staffdeck_work_tasks_rls$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['work_tasks', 'work_task_evidence', 'work_task_events']
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS runtime_tenant_isolation ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY runtime_tenant_isolation ON public.%I FOR ALL TO staffdeck_runtime '
      'USING (tenant_id = app.current_staffdeck_tenant_id()) '
      'WITH CHECK (tenant_id = app.current_staffdeck_tenant_id())',
      table_name
    );
    EXECUTE format('DROP POLICY IF EXISTS worker_all_tenants ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY worker_all_tenants ON public.%I FOR ALL TO staffdeck_worker '
      'USING (true) WITH CHECK (true)',
      table_name
    );
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC', table_name);
  END LOOP;
END
$staffdeck_work_tasks_rls$;

GRANT SELECT, INSERT, UPDATE ON public.work_tasks TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.work_task_evidence TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.work_task_events TO staffdeck_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.work_tasks TO staffdeck_worker;
GRANT SELECT, INSERT ON public.work_task_evidence TO staffdeck_worker;
GRANT SELECT, INSERT ON public.work_task_events TO staffdeck_worker;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260901_work_tasks_v1', now(), 'postgresql', 3, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
