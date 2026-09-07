BEGIN;

CREATE TABLE IF NOT EXISTS public.business_action_executions (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  request_id varchar NOT NULL,
  resource_id varchar NOT NULL,
  action_type varchar NOT NULL,
  connector_type varchar NOT NULL,
  environment varchar NOT NULL DEFAULT 'sandbox',
  workflow_version integer NOT NULL DEFAULT 1,
  status varchar NOT NULL DEFAULT 'queued',
  idempotency_key varchar NOT NULL,
  attempt_count integer NOT NULL DEFAULT 0,
  compensation_attempt_count integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 3,
  next_attempt_at timestamp without time zone,
  deadline_at timestamp without time zone,
  lease_owner varchar,
  lease_expires_at timestamp without time zone,
  execution_generation integer NOT NULL DEFAULT 0,
  external_operation_id varchar,
  receipt_json json NOT NULL DEFAULT '{}'::json,
  last_error_code varchar,
  last_error_message varchar,
  started_at timestamp without time zone,
  completed_at timestamp without time zone,
  compensated_at timestamp without time zone,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_business_action_execution_request UNIQUE (tenant_id, request_id),
  CONSTRAINT uq_business_action_execution_idempotency UNIQUE (tenant_id, idempotency_key),
  CONSTRAINT business_action_executions_environment_check
    CHECK (environment IN ('sandbox', 'live')),
  CONSTRAINT business_action_executions_status_check
    CHECK (status IN (
      'queued', 'running', 'retry_wait', 'succeeded', 'failed',
      'compensation_requested', 'compensating', 'compensated',
      'compensation_failed', 'manual_resolution_required'
    )),
  CONSTRAINT business_action_executions_attempts_check
    CHECK (attempt_count >= 0 AND compensation_attempt_count >= 0 AND max_attempts BETWEEN 1 AND 10),
  CONSTRAINT business_action_executions_request_fk
    FOREIGN KEY (request_id) REFERENCES public.high_risk_action_requests(id) ON DELETE RESTRICT,
  CONSTRAINT business_action_executions_resource_fk
    FOREIGN KEY (resource_id) REFERENCES public.business_resources(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS public.business_action_execution_events (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  execution_id varchar NOT NULL,
  request_id varchar NOT NULL,
  phase varchar NOT NULL,
  event_type varchar NOT NULL,
  attempt_no integer NOT NULL DEFAULT 0,
  actor_type varchar NOT NULL DEFAULT 'system',
  actor_id varchar,
  actor_business_role varchar,
  detail_json json NOT NULL DEFAULT '{}'::json,
  occurred_at timestamp without time zone NOT NULL,
  CONSTRAINT business_action_execution_events_phase_check
    CHECK (phase IN ('execution', 'compensation', 'reconciliation', 'operator')),
  CONSTRAINT business_action_execution_events_attempt_check CHECK (attempt_no >= 0),
  CONSTRAINT business_action_execution_events_execution_fk
    FOREIGN KEY (execution_id) REFERENCES public.business_action_executions(id) ON DELETE RESTRICT,
  CONSTRAINT business_action_execution_events_request_fk
    FOREIGN KEY (request_id) REFERENCES public.high_risk_action_requests(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_business_action_executions_tenant_id
  ON public.business_action_executions (tenant_id);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_request_id
  ON public.business_action_executions (request_id);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_resource_id
  ON public.business_action_executions (resource_id);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_action_type
  ON public.business_action_executions (action_type);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_connector_type
  ON public.business_action_executions (connector_type);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_environment
  ON public.business_action_executions (environment);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_status
  ON public.business_action_executions (status);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_idempotency_key
  ON public.business_action_executions (idempotency_key);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_next_attempt_at
  ON public.business_action_executions (next_attempt_at);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_deadline_at
  ON public.business_action_executions (deadline_at);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_lease_owner
  ON public.business_action_executions (lease_owner);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_lease_expires_at
  ON public.business_action_executions (lease_expires_at);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_external_operation_id
  ON public.business_action_executions (external_operation_id);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_last_error_code
  ON public.business_action_executions (last_error_code);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_completed_at
  ON public.business_action_executions (completed_at DESC);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_compensated_at
  ON public.business_action_executions (compensated_at DESC);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_created_at
  ON public.business_action_executions (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_business_action_executions_tenant_due
  ON public.business_action_executions (tenant_id, status, next_attempt_at);

CREATE INDEX IF NOT EXISTS ix_business_action_execution_events_tenant_id
  ON public.business_action_execution_events (tenant_id);
CREATE INDEX IF NOT EXISTS ix_business_action_execution_events_execution_id
  ON public.business_action_execution_events (execution_id);
CREATE INDEX IF NOT EXISTS ix_business_action_execution_events_request_id
  ON public.business_action_execution_events (request_id);
CREATE INDEX IF NOT EXISTS ix_business_action_execution_events_phase
  ON public.business_action_execution_events (phase);
CREATE INDEX IF NOT EXISTS ix_business_action_execution_events_event_type
  ON public.business_action_execution_events (event_type);
CREATE INDEX IF NOT EXISTS ix_business_action_execution_events_actor_type
  ON public.business_action_execution_events (actor_type);
CREATE INDEX IF NOT EXISTS ix_business_action_execution_events_actor_id
  ON public.business_action_execution_events (actor_id);
CREATE INDEX IF NOT EXISTS ix_business_action_execution_events_actor_business_role
  ON public.business_action_execution_events (actor_business_role);
CREATE INDEX IF NOT EXISTS ix_business_action_execution_events_occurred_at
  ON public.business_action_execution_events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_business_action_execution_events_execution_time
  ON public.business_action_execution_events (execution_id, occurred_at);

CREATE OR REPLACE FUNCTION app.reject_business_execution_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'business action execution events are append-only';
END;
$$;

DROP TRIGGER IF EXISTS business_action_execution_events_append_only
  ON public.business_action_execution_events;
CREATE TRIGGER business_action_execution_events_append_only
BEFORE UPDATE OR DELETE ON public.business_action_execution_events
FOR EACH ROW EXECUTE FUNCTION app.reject_business_execution_event_mutation();

DO $staffdeck_business_execution_rls$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'business_action_executions',
    'business_action_execution_events'
  ]
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
$staffdeck_business_execution_rls$;

GRANT SELECT, INSERT, UPDATE ON public.business_action_executions TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.business_action_execution_events TO staffdeck_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.business_action_executions TO staffdeck_worker;
GRANT SELECT, INSERT ON public.business_action_execution_events TO staffdeck_worker;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES (
  '20260901_business_action_execution_v1', now(), 'postgresql', 2, 0
)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
