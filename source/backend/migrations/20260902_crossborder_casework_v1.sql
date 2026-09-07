BEGIN;

CREATE TABLE IF NOT EXISTS public.after_sales_cases (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  case_key varchar NOT NULL,
  store_resource_id varchar NOT NULL REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  store_code varchar NOT NULL,
  platform varchar NOT NULL,
  marketplace_country varchar NOT NULL,
  language varchar NOT NULL DEFAULT 'en',
  order_reference_digest varchar NOT NULL,
  order_reference_masked varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'intake',
  category varchar,
  risk_level varchar NOT NULL DEFAULT 'medium',
  needs_human boolean NOT NULL DEFAULT false,
  human_reason varchar,
  task_id varchar NOT NULL REFERENCES public.work_tasks(id) ON DELETE RESTRICT,
  approval_request_id varchar REFERENCES public.high_risk_action_requests(id) ON DELETE RESTRICT,
  order_snapshot_json json NOT NULL DEFAULT '{}'::json,
  citations_json json NOT NULL DEFAULT '[]'::json,
  recommendation_json json NOT NULL DEFAULT '{}'::json,
  draft_reply varchar,
  root_cause varchar,
  follow_up_task_ids_json json NOT NULL DEFAULT '[]'::json,
  created_by_user_id varchar NOT NULL,
  closed_by_user_id varchar,
  version integer NOT NULL DEFAULT 0,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  closed_at timestamp without time zone,
  CONSTRAINT uq_after_sales_case_key UNIQUE (tenant_id, case_key),
  CONSTRAINT after_sales_cases_status_check CHECK (
    status IN ('intake', 'queried', 'classified', 'drafted', 'waiting_approval',
               'needs_human', 'closed', 'rejected')
  ),
  CONSTRAINT after_sales_cases_risk_check CHECK (
    risk_level IN ('low', 'medium', 'high', 'critical')
  ),
  CONSTRAINT after_sales_cases_version_check CHECK (version >= 0)
);

CREATE INDEX IF NOT EXISTS ix_after_sales_cases_tenant_id ON public.after_sales_cases (tenant_id);
CREATE INDEX IF NOT EXISTS ix_after_sales_cases_case_key ON public.after_sales_cases (case_key);
CREATE INDEX IF NOT EXISTS ix_after_sales_cases_store_resource_id ON public.after_sales_cases (store_resource_id);
CREATE INDEX IF NOT EXISTS ix_after_sales_cases_order_reference_digest ON public.after_sales_cases (order_reference_digest);
CREATE INDEX IF NOT EXISTS ix_after_sales_cases_task_id ON public.after_sales_cases (task_id);
CREATE INDEX IF NOT EXISTS ix_after_sales_cases_approval_request_id ON public.after_sales_cases (approval_request_id);
CREATE INDEX IF NOT EXISTS ix_after_sales_cases_tenant_status_updated
  ON public.after_sales_cases (tenant_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS public.after_sales_case_events (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  case_id varchar NOT NULL REFERENCES public.after_sales_cases(id) ON DELETE RESTRICT,
  event_type varchar NOT NULL,
  actor_type varchar NOT NULL DEFAULT 'human',
  actor_id varchar,
  actor_business_role varchar,
  from_status varchar,
  to_status varchar,
  detail_json json NOT NULL DEFAULT '{}'::json,
  occurred_at timestamp without time zone NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_after_sales_case_events_tenant_id ON public.after_sales_case_events (tenant_id);
CREATE INDEX IF NOT EXISTS ix_after_sales_case_events_case_id ON public.after_sales_case_events (case_id);
CREATE INDEX IF NOT EXISTS ix_after_sales_case_events_event_type ON public.after_sales_case_events (event_type);
CREATE INDEX IF NOT EXISTS ix_after_sales_case_events_case_time
  ON public.after_sales_case_events (case_id, occurred_at);

CREATE TABLE IF NOT EXISTS public.logistics_anomalies (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  fingerprint varchar NOT NULL,
  carrier_resource_id varchar NOT NULL REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  carrier_code varchar NOT NULL,
  store_resource_id varchar REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  platform varchar NOT NULL,
  order_reference_digest varchar NOT NULL,
  order_reference_masked varchar NOT NULL,
  status_event_id varchar NOT NULL,
  shipment_status varchar NOT NULL,
  anomaly_type varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'detected',
  severity varchar NOT NULL DEFAULT 'medium',
  customer_impact varchar NOT NULL DEFAULT 'medium',
  cluster_key varchar NOT NULL,
  dimensions_json json NOT NULL DEFAULT '{}'::json,
  evidence_json json NOT NULL DEFAULT '{}'::json,
  escalation_targets_json json NOT NULL DEFAULT '[]'::json,
  follow_up_task_ids_json json NOT NULL DEFAULT '[]'::json,
  task_id varchar NOT NULL REFERENCES public.work_tasks(id) ON DELETE RESTRICT,
  occurrence_count integer NOT NULL DEFAULT 1,
  deadline_at timestamp without time zone,
  first_observed_at timestamp without time zone NOT NULL,
  last_observed_at timestamp without time zone NOT NULL,
  resolved_by_user_id varchar,
  resolution varchar,
  version integer NOT NULL DEFAULT 0,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  resolved_at timestamp without time zone,
  CONSTRAINT uq_logistics_anomaly_fingerprint UNIQUE (tenant_id, fingerprint),
  CONSTRAINT logistics_anomalies_status_check CHECK (
    status IN ('detected', 'clustered', 'escalated', 'resolved')
  ),
  CONSTRAINT logistics_anomalies_severity_check CHECK (
    severity IN ('low', 'medium', 'high', 'critical')
  ),
  CONSTRAINT logistics_anomalies_customer_impact_check CHECK (
    customer_impact IN ('low', 'medium', 'high', 'critical')
  ),
  CONSTRAINT logistics_anomalies_occurrence_check CHECK (occurrence_count > 0),
  CONSTRAINT logistics_anomalies_version_check CHECK (version >= 0)
);

CREATE INDEX IF NOT EXISTS ix_logistics_anomalies_tenant_id ON public.logistics_anomalies (tenant_id);
CREATE INDEX IF NOT EXISTS ix_logistics_anomalies_fingerprint ON public.logistics_anomalies (fingerprint);
CREATE INDEX IF NOT EXISTS ix_logistics_anomalies_carrier_resource_id ON public.logistics_anomalies (carrier_resource_id);
CREATE INDEX IF NOT EXISTS ix_logistics_anomalies_store_resource_id ON public.logistics_anomalies (store_resource_id);
CREATE INDEX IF NOT EXISTS ix_logistics_anomalies_order_reference_digest ON public.logistics_anomalies (order_reference_digest);
CREATE INDEX IF NOT EXISTS ix_logistics_anomalies_task_id ON public.logistics_anomalies (task_id);
CREATE INDEX IF NOT EXISTS ix_logistics_anomalies_tenant_status_updated
  ON public.logistics_anomalies (tenant_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_logistics_anomalies_tenant_cluster
  ON public.logistics_anomalies (tenant_id, cluster_key);

CREATE TABLE IF NOT EXISTS public.logistics_anomaly_events (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  anomaly_id varchar NOT NULL REFERENCES public.logistics_anomalies(id) ON DELETE RESTRICT,
  event_type varchar NOT NULL,
  actor_type varchar NOT NULL DEFAULT 'system',
  actor_id varchar,
  actor_business_role varchar,
  from_status varchar,
  to_status varchar,
  detail_json json NOT NULL DEFAULT '{}'::json,
  occurred_at timestamp without time zone NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_logistics_anomaly_events_tenant_id ON public.logistics_anomaly_events (tenant_id);
CREATE INDEX IF NOT EXISTS ix_logistics_anomaly_events_anomaly_id ON public.logistics_anomaly_events (anomaly_id);
CREATE INDEX IF NOT EXISTS ix_logistics_anomaly_events_event_type ON public.logistics_anomaly_events (event_type);
CREATE INDEX IF NOT EXISTS ix_logistics_anomaly_events_anomaly_time
  ON public.logistics_anomaly_events (anomaly_id, occurred_at);

CREATE TABLE IF NOT EXISTS public.integration_health_states (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  dependency_key varchar NOT NULL,
  display_name varchar NOT NULL,
  domain varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'healthy',
  reason_code varchar,
  message varchar NOT NULL DEFAULT '',
  recovery_hint varchar NOT NULL DEFAULT '',
  source varchar NOT NULL DEFAULT 'operator',
  last_success_at timestamp without time zone,
  observed_at timestamp without time zone NOT NULL,
  stale_after_seconds integer NOT NULL DEFAULT 900,
  version integer NOT NULL DEFAULT 0,
  updated_by_user_id varchar,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_integration_health_dependency UNIQUE (tenant_id, dependency_key),
  CONSTRAINT integration_health_states_status_check CHECK (
    status IN ('healthy', 'degraded', 'unavailable')
  ),
  CONSTRAINT integration_health_states_stale_after_check CHECK (
    stale_after_seconds BETWEEN 30 AND 86400
  ),
  CONSTRAINT integration_health_states_version_check CHECK (version >= 0)
);

CREATE INDEX IF NOT EXISTS ix_integration_health_states_tenant_id ON public.integration_health_states (tenant_id);
CREATE INDEX IF NOT EXISTS ix_integration_health_states_dependency_key ON public.integration_health_states (dependency_key);
CREATE INDEX IF NOT EXISTS ix_integration_health_states_domain ON public.integration_health_states (domain);
CREATE INDEX IF NOT EXISTS ix_integration_health_states_reason_code ON public.integration_health_states (reason_code);
CREATE INDEX IF NOT EXISTS ix_integration_health_tenant_status
  ON public.integration_health_states (tenant_id, status);

CREATE TABLE IF NOT EXISTS public.integration_health_events (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  state_id varchar NOT NULL REFERENCES public.integration_health_states(id) ON DELETE RESTRICT,
  event_type varchar NOT NULL,
  actor_type varchar NOT NULL DEFAULT 'system',
  actor_id varchar,
  from_status varchar,
  to_status varchar NOT NULL,
  detail_json json NOT NULL DEFAULT '{}'::json,
  occurred_at timestamp without time zone NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_integration_health_events_tenant_id ON public.integration_health_events (tenant_id);
CREATE INDEX IF NOT EXISTS ix_integration_health_events_state_id ON public.integration_health_events (state_id);
CREATE INDEX IF NOT EXISTS ix_integration_health_events_event_type ON public.integration_health_events (event_type);
CREATE INDEX IF NOT EXISTS ix_integration_health_events_state_time
  ON public.integration_health_events (state_id, occurred_at);

CREATE OR REPLACE FUNCTION app.reject_crossborder_trace_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;

DROP TRIGGER IF EXISTS after_sales_case_events_append_only ON public.after_sales_case_events;
CREATE TRIGGER after_sales_case_events_append_only
BEFORE UPDATE OR DELETE ON public.after_sales_case_events
FOR EACH ROW EXECUTE FUNCTION app.reject_crossborder_trace_mutation();

DROP TRIGGER IF EXISTS logistics_anomaly_events_append_only ON public.logistics_anomaly_events;
CREATE TRIGGER logistics_anomaly_events_append_only
BEFORE UPDATE OR DELETE ON public.logistics_anomaly_events
FOR EACH ROW EXECUTE FUNCTION app.reject_crossborder_trace_mutation();

DROP TRIGGER IF EXISTS integration_health_events_append_only ON public.integration_health_events;
CREATE TRIGGER integration_health_events_append_only
BEFORE UPDATE OR DELETE ON public.integration_health_events
FOR EACH ROW EXECUTE FUNCTION app.reject_crossborder_trace_mutation();

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'after_sales_cases',
    'after_sales_case_events',
    'logistics_anomalies',
    'logistics_anomaly_events',
    'integration_health_states',
    'integration_health_events'
  ] LOOP
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
END;
$$;

GRANT SELECT, INSERT, UPDATE ON public.after_sales_cases TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT ON public.after_sales_case_events TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT, UPDATE ON public.logistics_anomalies TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT ON public.logistics_anomaly_events TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT, UPDATE ON public.integration_health_states TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT ON public.integration_health_events TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260902_crossborder_casework_v1', now(), 'postgresql', 6, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
