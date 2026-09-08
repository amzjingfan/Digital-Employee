BEGIN;

CREATE TABLE IF NOT EXISTS public.pdca_search_term_runs (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  idempotency_key varchar NOT NULL,
  ad_account_resource_id varchar NOT NULL REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  store_resource_id varchar REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  source_type varchar NOT NULL DEFAULT 'amazon_search_term_csv',
  source_label varchar NOT NULL DEFAULT 'local source file',
  source_sha256 varchar NOT NULL,
  input_digest varchar NOT NULL,
  attempt integer NOT NULL DEFAULT 1,
  mapping_version varchar NOT NULL,
  rule_version varchar NOT NULL,
  metric_definition_version varchar NOT NULL,
  mode varchar NOT NULL DEFAULT 'rules_only',
  state varchar NOT NULL DEFAULT 'succeeded',
  target_acos numeric(12, 8) NOT NULL,
  currency varchar NOT NULL DEFAULT 'USD',
  source_row_count integer NOT NULL DEFAULT 0,
  fact_count integer NOT NULL DEFAULT 0,
  action_count integer NOT NULL DEFAULT 0,
  quality_score integer NOT NULL DEFAULT 0,
  mapping_snapshot_json json NOT NULL DEFAULT '{}'::json,
  summary_json json NOT NULL DEFAULT '{}'::json,
  warnings_json json NOT NULL DEFAULT '[]'::json,
  external_execution_allowed boolean NOT NULL DEFAULT false,
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_pdca_search_term_run_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_pdca_search_term_run_idempotency UNIQUE (tenant_id, idempotency_key),
  CONSTRAINT uq_pdca_search_term_run_snapshot_attempt UNIQUE (tenant_id, input_digest, attempt),
  CONSTRAINT pdca_search_term_runs_mode_check CHECK (mode = 'rules_only'),
  CONSTRAINT pdca_search_term_runs_state_check CHECK (state = 'succeeded'),
  CONSTRAINT pdca_search_term_runs_no_execution_check CHECK (external_execution_allowed = false),
  CONSTRAINT pdca_search_term_runs_quality_check CHECK (quality_score BETWEEN 0 AND 100),
  CONSTRAINT pdca_search_term_runs_counts_check CHECK (
    source_row_count > 0 AND fact_count > 0 AND action_count >= 0
  ),
  CONSTRAINT pdca_search_term_runs_target_check CHECK (target_acos > 0 AND target_acos <= 1),
  CONSTRAINT pdca_search_term_runs_attempt_check CHECK (attempt > 0),
  CONSTRAINT pdca_search_term_runs_currency_check CHECK (currency ~ '^[A-Z]{3}$')
);
CREATE INDEX IF NOT EXISTS ix_pdca_search_term_runs_tenant_id
  ON public.pdca_search_term_runs (tenant_id);
CREATE INDEX IF NOT EXISTS ix_pdca_search_term_runs_account_time
  ON public.pdca_search_term_runs (tenant_id, ad_account_resource_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_pdca_search_term_runs_source_sha256
  ON public.pdca_search_term_runs (tenant_id, source_sha256);

CREATE TABLE IF NOT EXISTS public.pdca_fact_search_terms (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  run_id varchar NOT NULL,
  grain_key varchar NOT NULL,
  date_start date NOT NULL,
  date_end date NOT NULL,
  campaign_id varchar NOT NULL,
  campaign_name varchar NOT NULL,
  ad_group_id varchar NOT NULL,
  ad_group_name varchar NOT NULL,
  targeting varchar NOT NULL,
  match_type varchar NOT NULL,
  search_term varchar NOT NULL,
  search_term_norm varchar NOT NULL,
  impressions bigint NOT NULL DEFAULT 0,
  clicks bigint NOT NULL DEFAULT 0,
  spend numeric(20, 6) NOT NULL DEFAULT 0,
  sales numeric(20, 6) NOT NULL DEFAULT 0,
  orders bigint NOT NULL DEFAULT 0,
  metric_snapshot_json json NOT NULL DEFAULT '{}'::json,
  evidence_json json NOT NULL DEFAULT '{}'::json,
  source_row_refs_json json NOT NULL DEFAULT '[]'::json,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_pdca_fact_search_term_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_pdca_fact_search_term_grain UNIQUE (tenant_id, run_id, grain_key),
  CONSTRAINT fk_pdca_fact_search_term_run_tenant FOREIGN KEY (tenant_id, run_id)
    REFERENCES public.pdca_search_term_runs(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT pdca_fact_search_terms_metric_check CHECK (
    impressions >= 0 AND clicks >= 0 AND orders >= 0 AND spend >= 0 AND sales >= 0
  )
);
CREATE INDEX IF NOT EXISTS ix_pdca_fact_search_terms_tenant_id
  ON public.pdca_fact_search_terms (tenant_id);
CREATE INDEX IF NOT EXISTS ix_pdca_fact_search_terms_run
  ON public.pdca_fact_search_terms (tenant_id, run_id, campaign_id);
CREATE INDEX IF NOT EXISTS ix_pdca_fact_search_terms_search_term
  ON public.pdca_fact_search_terms (tenant_id, search_term_norm);

CREATE TABLE IF NOT EXISTS public.pdca_actions (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  run_id varchar NOT NULL,
  fact_id varchar NOT NULL,
  action_type varchar NOT NULL,
  priority varchar NOT NULL,
  must_do_score integer NOT NULL DEFAULT 0,
  rationale varchar NOT NULL,
  evidence_json json NOT NULL DEFAULT '{}'::json,
  thresholds_json json NOT NULL DEFAULT '{}'::json,
  current_values_json json NOT NULL DEFAULT '{}'::json,
  expected_effect varchar NOT NULL,
  risk_note varchar NOT NULL,
  verification_window_days integer NOT NULL DEFAULT 7,
  execution_hint varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'suggested',
  external_execution_allowed boolean NOT NULL DEFAULT false,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_pdca_action_rule_output UNIQUE (tenant_id, run_id, fact_id, action_type),
  CONSTRAINT fk_pdca_action_run_tenant FOREIGN KEY (tenant_id, run_id)
    REFERENCES public.pdca_search_term_runs(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_pdca_action_fact_tenant FOREIGN KEY (tenant_id, fact_id)
    REFERENCES public.pdca_fact_search_terms(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT pdca_actions_type_check CHECK (
    action_type IN ('manual_review', 'lower_bid', 'convert_exact', 'protect_scale', 'observe')
  ),
  CONSTRAINT pdca_actions_priority_check CHECK (
    priority IN ('critical', 'high', 'medium', 'low')
  ),
  CONSTRAINT pdca_actions_status_check CHECK (status = 'suggested'),
  CONSTRAINT pdca_actions_no_execution_check CHECK (external_execution_allowed = false),
  CONSTRAINT pdca_actions_score_check CHECK (must_do_score BETWEEN 0 AND 100),
  CONSTRAINT pdca_actions_window_check CHECK (verification_window_days > 0)
);
CREATE INDEX IF NOT EXISTS ix_pdca_actions_tenant_id
  ON public.pdca_actions (tenant_id);
CREATE INDEX IF NOT EXISTS ix_pdca_actions_run_priority
  ON public.pdca_actions (tenant_id, run_id, must_do_score DESC);

CREATE OR REPLACE FUNCTION app.reject_pdca_evidence_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'pdca_search_term_runs',
    'pdca_fact_search_terms',
    'pdca_actions'
  ] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS pdca_append_only ON public.%I', table_name);
    EXECUTE format(
      'CREATE TRIGGER pdca_append_only BEFORE UPDATE OR DELETE ON public.%I '
      'FOR EACH ROW EXECUTE FUNCTION app.reject_pdca_evidence_mutation()',
      table_name
    );
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
    EXECUTE format(
      'GRANT SELECT, INSERT ON public.%I TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator',
      table_name
    );
  END LOOP;
END;
$$;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260908_pdca_search_term_rules_v1', now(), 'postgresql', 3, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
