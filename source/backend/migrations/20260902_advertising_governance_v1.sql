BEGIN;

CREATE TABLE IF NOT EXISTS public.advertising_recommendations (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  recommendation_key varchar NOT NULL,
  ad_account_resource_id varchar NOT NULL REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  store_resource_id varchar REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  campaign_id varchar NOT NULL,
  product_key varchar NOT NULL,
  metric_snapshot_json json NOT NULL DEFAULT '{}'::json,
  constraint_snapshot_json json NOT NULL DEFAULT '{}'::json,
  findings_json json NOT NULL DEFAULT '[]'::json,
  recommendation_json json NOT NULL DEFAULT '{}'::json,
  proposed_action_type varchar,
  proposed_action_payload_json json NOT NULL DEFAULT '{}'::json,
  risk_level varchar NOT NULL DEFAULT 'medium',
  status varchar NOT NULL DEFAULT 'ready',
  input_digest varchar NOT NULL,
  task_id varchar NOT NULL REFERENCES public.work_tasks(id) ON DELETE RESTRICT,
  linked_task_ids_json json NOT NULL DEFAULT '[]'::json,
  approval_request_id varchar REFERENCES public.high_risk_action_requests(id) ON DELETE RESTRICT,
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  version integer NOT NULL DEFAULT 0,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_advertising_recommendation_key UNIQUE (tenant_id, recommendation_key),
  CONSTRAINT advertising_recommendations_status_check CHECK (
    status IN ('ready', 'blocked', 'action_pending', 'action_approved', 'action_rejected')
  ),
  CONSTRAINT advertising_recommendations_risk_check CHECK (
    risk_level IN ('low', 'medium', 'high', 'critical')
  ),
  CONSTRAINT advertising_recommendations_version_check CHECK (version >= 0)
);
CREATE INDEX IF NOT EXISTS ix_advertising_recommendations_tenant_id
  ON public.advertising_recommendations (tenant_id);
CREATE INDEX IF NOT EXISTS ix_advertising_recommendations_ad_account_resource_id
  ON public.advertising_recommendations (ad_account_resource_id);
CREATE INDEX IF NOT EXISTS ix_advertising_recommendations_campaign_time
  ON public.advertising_recommendations (tenant_id, campaign_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_advertising_recommendations_approval_request_id
  ON public.advertising_recommendations (approval_request_id);

CREATE TABLE IF NOT EXISTS public.advertising_effect_follow_ups (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  execution_id varchar NOT NULL REFERENCES public.business_action_executions(id) ON DELETE RESTRICT,
  request_id varchar NOT NULL REFERENCES public.high_risk_action_requests(id) ON DELETE RESTRICT,
  recommendation_id varchar REFERENCES public.advertising_recommendations(id) ON DELETE RESTRICT,
  horizon_days integer NOT NULL,
  baseline_json json NOT NULL DEFAULT '{}'::json,
  task_id varchar NOT NULL REFERENCES public.work_tasks(id) ON DELETE RESTRICT,
  status varchar NOT NULL DEFAULT 'pending',
  due_at timestamp without time zone NOT NULL,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_advertising_effect_follow_up UNIQUE (
    tenant_id, execution_id, horizon_days
  ),
  CONSTRAINT advertising_effect_follow_ups_horizon_check CHECK (
    horizon_days IN (7, 14, 30)
  ),
  CONSTRAINT advertising_effect_follow_ups_status_check CHECK (
    status IN ('pending', 'completed', 'cancelled')
  )
);
CREATE INDEX IF NOT EXISTS ix_advertising_effect_follow_ups_tenant_id
  ON public.advertising_effect_follow_ups (tenant_id);
CREATE INDEX IF NOT EXISTS ix_advertising_effect_follow_ups_execution_id
  ON public.advertising_effect_follow_ups (execution_id);
CREATE INDEX IF NOT EXISTS ix_advertising_effect_follow_ups_due
  ON public.advertising_effect_follow_ups (tenant_id, status, due_at);

CREATE TABLE IF NOT EXISTS public.execution_automation_policies (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  resource_id varchar NOT NULL REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  action_type varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'paused',
  rollout_percent integer NOT NULL DEFAULT 0,
  max_single_value double precision NOT NULL DEFAULT 0,
  max_daily_value double precision NOT NULL DEFAULT 0,
  max_risk_level varchar NOT NULL DEFAULT 'low',
  approval_required boolean NOT NULL DEFAULT true,
  kill_switch_engaged boolean NOT NULL DEFAULT true,
  revision integer NOT NULL DEFAULT 1,
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  updated_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_execution_automation_policy UNIQUE (tenant_id, resource_id, action_type),
  CONSTRAINT execution_automation_policies_status_check CHECK (
    status IN ('active', 'paused')
  ),
  CONSTRAINT execution_automation_policies_rollout_check CHECK (
    rollout_percent BETWEEN 0 AND 100
  ),
  CONSTRAINT execution_automation_policies_values_check CHECK (
    max_single_value >= 0 AND max_daily_value >= 0 AND revision > 0
  ),
  CONSTRAINT execution_automation_policies_risk_check CHECK (
    max_risk_level IN ('low', 'medium')
  ),
  CONSTRAINT execution_automation_policies_approval_check CHECK (
    approval_required = true
  )
);
CREATE INDEX IF NOT EXISTS ix_execution_automation_policies_tenant_id
  ON public.execution_automation_policies (tenant_id);
CREATE INDEX IF NOT EXISTS ix_execution_automation_policies_lookup
  ON public.execution_automation_policies (tenant_id, resource_id, action_type, status);

CREATE TABLE IF NOT EXISTS public.automation_usage_ledger (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  policy_id varchar NOT NULL REFERENCES public.execution_automation_policies(id) ON DELETE RESTRICT,
  policy_revision integer NOT NULL,
  request_id varchar NOT NULL REFERENCES public.high_risk_action_requests(id) ON DELETE RESTRICT,
  action_type varchar NOT NULL,
  cohort_bucket integer NOT NULL,
  quantitative_value double precision NOT NULL,
  usage_date varchar NOT NULL,
  decision varchar NOT NULL,
  reason varchar NOT NULL,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_automation_usage_request UNIQUE (tenant_id, request_id),
  CONSTRAINT automation_usage_ledger_decision_check CHECK (
    decision IN ('allowed', 'blocked')
  ),
  CONSTRAINT automation_usage_ledger_values_check CHECK (
    cohort_bucket BETWEEN 0 AND 99 AND quantitative_value >= 0
  )
);
CREATE INDEX IF NOT EXISTS ix_automation_usage_ledger_tenant_id
  ON public.automation_usage_ledger (tenant_id);
CREATE INDEX IF NOT EXISTS ix_automation_usage_ledger_policy_day
  ON public.automation_usage_ledger (tenant_id, policy_id, usage_date, decision);

CREATE OR REPLACE FUNCTION app.protect_advertising_recommendation_evidence()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'advertising recommendation evidence cannot be deleted';
  END IF;
  IF (
    OLD.metric_snapshot_json::text IS DISTINCT FROM NEW.metric_snapshot_json::text OR
    OLD.constraint_snapshot_json::text IS DISTINCT FROM NEW.constraint_snapshot_json::text OR
    OLD.findings_json::text IS DISTINCT FROM NEW.findings_json::text OR
    OLD.recommendation_json::text IS DISTINCT FROM NEW.recommendation_json::text OR
    OLD.proposed_action_type IS DISTINCT FROM NEW.proposed_action_type OR
    OLD.proposed_action_payload_json::text IS DISTINCT FROM NEW.proposed_action_payload_json::text OR
    OLD.input_digest IS DISTINCT FROM NEW.input_digest
  ) THEN
    RAISE EXCEPTION 'advertising recommendation evidence is immutable';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS advertising_recommendations_evidence_immutable
  ON public.advertising_recommendations;
CREATE TRIGGER advertising_recommendations_evidence_immutable
BEFORE UPDATE OR DELETE ON public.advertising_recommendations
FOR EACH ROW EXECUTE FUNCTION app.protect_advertising_recommendation_evidence();

CREATE OR REPLACE FUNCTION app.reject_advertising_ledger_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;

DROP TRIGGER IF EXISTS automation_usage_ledger_append_only
  ON public.automation_usage_ledger;
CREATE TRIGGER automation_usage_ledger_append_only
BEFORE UPDATE OR DELETE ON public.automation_usage_ledger
FOR EACH ROW EXECUTE FUNCTION app.reject_advertising_ledger_mutation();

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'advertising_recommendations',
    'advertising_effect_follow_ups',
    'execution_automation_policies',
    'automation_usage_ledger'
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

GRANT SELECT, INSERT, UPDATE ON public.advertising_recommendations
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT, UPDATE ON public.advertising_effect_follow_ups
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT, UPDATE ON public.execution_automation_policies
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT ON public.automation_usage_ledger
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260902_advertising_governance_v1', now(), 'postgresql', 4, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
