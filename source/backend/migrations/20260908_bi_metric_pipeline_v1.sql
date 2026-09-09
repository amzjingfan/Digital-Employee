BEGIN;

CREATE TABLE IF NOT EXISTS public.bi_ingestion_batches (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  source_key varchar NOT NULL,
  window_start timestamptz NOT NULL,
  window_end timestamptz NOT NULL,
  business_timezone varchar NOT NULL,
  snapshot_mode varchar NOT NULL DEFAULT 'full_window',
  input_digest varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'pending',
  quality_status varchar NOT NULL DEFAULT 'pending',
  row_count integer NOT NULL DEFAULT 0,
  accepted_count integer NOT NULL DEFAULT 0,
  rejected_count integer NOT NULL DEFAULT 0,
  expected_row_count integer,
  expected_gross_sales numeric(24, 6),
  expected_ad_spend numeric(24, 6),
  actual_gross_sales numeric(24, 6) NOT NULL DEFAULT 0,
  actual_ad_spend numeric(24, 6) NOT NULL DEFAULT 0,
  reconciliation_tolerance numeric(24, 6) NOT NULL DEFAULT 0.01,
  metric_definition_version varchar NOT NULL DEFAULT '1.0.0',
  latest_source_observed_at timestamptz,
  created_by_user_id varchar NOT NULL,
  created_at timestamptz NOT NULL,
  completed_at timestamptz,
  CONSTRAINT uq_bi_ingestion_batch_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_bi_ingestion_batch_source_identity UNIQUE (tenant_id, id, source_key),
  CONSTRAINT uq_bi_ingestion_batch_payload UNIQUE (
    tenant_id, source_key, window_start, window_end, input_digest
  ),
  CONSTRAINT bi_ingestion_batches_status_check CHECK (
    status IN ('pending', 'succeeded', 'rejected', 'superseded')
  ),
  CONSTRAINT bi_ingestion_batches_quality_status_check CHECK (
    quality_status IN ('pending', 'passed', 'failed')
  ),
  CONSTRAINT bi_ingestion_batches_snapshot_mode_check CHECK (
    snapshot_mode IN ('full_window', 'incremental')
  ),
  CONSTRAINT bi_ingestion_batches_window_check CHECK (window_end > window_start),
  CONSTRAINT bi_ingestion_batches_count_check CHECK (
    row_count >= 0 AND accepted_count >= 0 AND rejected_count >= 0
  )
);

CREATE INDEX IF NOT EXISTS ix_bi_ingestion_batches_tenant_source_window
  ON public.bi_ingestion_batches (tenant_id, source_key, window_start, window_end);
CREATE INDEX IF NOT EXISTS ix_bi_ingestion_batches_tenant_quality_completed
  ON public.bi_ingestion_batches (tenant_id, quality_status, completed_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_bi_ingestion_batches_succeeded_window
  ON public.bi_ingestion_batches (tenant_id, source_key, window_start, window_end)
  WHERE status = 'succeeded';

CREATE TABLE IF NOT EXISTS public.bi_data_quality_checks (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  batch_id varchar NOT NULL,
  check_code varchar NOT NULL,
  status varchar NOT NULL,
  severity varchar NOT NULL DEFAULT 'error',
  observed_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  expected_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  detail varchar NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_bi_quality_check_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_bi_quality_check_batch_code UNIQUE (tenant_id, batch_id, check_code),
  CONSTRAINT bi_quality_checks_batch_fk FOREIGN KEY (tenant_id, batch_id)
    REFERENCES public.bi_ingestion_batches(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT bi_data_quality_checks_status_check CHECK (
    status IN ('passed', 'failed', 'skipped')
  ),
  CONSTRAINT bi_data_quality_checks_severity_check CHECK (
    severity IN ('info', 'warning', 'error')
  )
);

CREATE INDEX IF NOT EXISTS ix_bi_quality_checks_batch_status
  ON public.bi_data_quality_checks (batch_id, status);

CREATE TABLE IF NOT EXISTS public.bi_daily_commerce_facts (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  batch_id varchar NOT NULL,
  source_key varchar NOT NULL,
  external_id varchar NOT NULL,
  source_version varchar NOT NULL,
  content_digest varchar NOT NULL,
  replaces_fact_id varchar,
  is_current boolean NOT NULL DEFAULT true,
  business_date date NOT NULL,
  brand_id varchar NOT NULL,
  store_id varchar NOT NULL,
  platform varchar NOT NULL,
  entity_type varchar NOT NULL,
  entity_id varchar NOT NULL,
  currency char(3) NOT NULL,
  gross_sales numeric(24, 6) NOT NULL,
  refund_amount numeric(24, 6) NOT NULL,
  ad_spend numeric(24, 6) NOT NULL,
  attributed_ad_sales numeric(24, 6) NOT NULL,
  impressions bigint NOT NULL DEFAULT 0,
  clicks bigint NOT NULL DEFAULT 0,
  orders bigint NOT NULL DEFAULT 0,
  available_inventory bigint NOT NULL DEFAULT 0,
  rolling_units_sold bigint NOT NULL DEFAULT 0,
  rolling_window_days integer NOT NULL DEFAULT 30,
  source_observed_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_bi_daily_fact_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_bi_daily_fact_source_version UNIQUE (
    tenant_id, source_key, external_id, source_version
  ),
  CONSTRAINT bi_daily_facts_batch_fk FOREIGN KEY (tenant_id, batch_id, source_key)
    REFERENCES public.bi_ingestion_batches(tenant_id, id, source_key) ON DELETE RESTRICT,
  CONSTRAINT bi_daily_facts_replaces_fk FOREIGN KEY (tenant_id, replaces_fact_id)
    REFERENCES public.bi_daily_commerce_facts(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT bi_daily_facts_entity_type_check CHECK (
    entity_type IN ('store', 'asin', 'sku')
  ),
  CONSTRAINT bi_daily_facts_currency_check CHECK (currency ~ '^[A-Z]{3}$'),
  CONSTRAINT bi_daily_facts_amount_check CHECK (
    gross_sales >= 0 AND refund_amount >= 0 AND ad_spend >= 0
    AND attributed_ad_sales >= 0
  ),
  CONSTRAINT bi_daily_facts_count_check CHECK (
    impressions >= 0 AND clicks >= 0 AND orders >= 0
    AND available_inventory >= 0 AND rolling_units_sold >= 0
    AND rolling_window_days > 0
  )
);

CREATE INDEX IF NOT EXISTS ix_bi_daily_facts_current_grain
  ON public.bi_daily_commerce_facts (
    tenant_id, source_key, business_date, brand_id, store_id, is_current
  );
CREATE UNIQUE INDEX IF NOT EXISTS uq_bi_daily_facts_current_external
  ON public.bi_daily_commerce_facts (tenant_id, source_key, external_id)
  WHERE is_current;

CREATE TABLE IF NOT EXISTS public.bi_metric_definitions (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  code varchar NOT NULL,
  version varchar NOT NULL,
  name varchar NOT NULL,
  formula varchar NOT NULL,
  grain varchar NOT NULL,
  business_timezone varchar NOT NULL,
  currency_policy varchar NOT NULL,
  attribution_window_days integer NOT NULL DEFAULT 7,
  status varchar NOT NULL DEFAULT 'active',
  effective_from timestamptz NOT NULL,
  created_by_user_id varchar NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_bi_metric_definition_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_bi_metric_definition_identity UNIQUE (tenant_id, id, code, version),
  CONSTRAINT uq_bi_metric_definition_version UNIQUE (tenant_id, code, version),
  CONSTRAINT bi_metric_definitions_status_check CHECK (status IN ('active', 'retired')),
  CONSTRAINT bi_metric_definitions_attribution_check CHECK (attribution_window_days > 0)
);

CREATE INDEX IF NOT EXISTS ix_bi_metric_definitions_tenant_code_status
  ON public.bi_metric_definitions (tenant_id, code, status);

CREATE TABLE IF NOT EXISTS public.bi_daily_metrics (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  batch_id varchar NOT NULL,
  metric_definition_id varchar NOT NULL,
  metric_code varchar NOT NULL,
  metric_definition_version varchar NOT NULL,
  business_date date NOT NULL,
  source_key varchar NOT NULL,
  brand_id varchar NOT NULL DEFAULT '',
  store_id varchar NOT NULL DEFAULT '',
  platform varchar NOT NULL DEFAULT '',
  entity_type varchar NOT NULL,
  entity_id varchar NOT NULL,
  currency varchar NOT NULL DEFAULT '',
  value numeric(24, 6),
  null_reason varchar,
  freshness_status varchar NOT NULL DEFAULT 'unknown',
  latest_source_observed_at timestamptz,
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_current boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_bi_daily_metric_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_bi_daily_metric_batch_grain UNIQUE (
    tenant_id, batch_id, metric_definition_id, business_date,
    entity_type, entity_id, currency
  ),
  CONSTRAINT bi_daily_metrics_batch_fk FOREIGN KEY (tenant_id, batch_id, source_key)
    REFERENCES public.bi_ingestion_batches(tenant_id, id, source_key) ON DELETE RESTRICT,
  CONSTRAINT bi_daily_metrics_definition_fk FOREIGN KEY (
    tenant_id, metric_definition_id, metric_code, metric_definition_version
  ) REFERENCES public.bi_metric_definitions(tenant_id, id, code, version) ON DELETE RESTRICT,
  CONSTRAINT bi_daily_metrics_freshness_check CHECK (
    freshness_status IN ('fresh', 'stale', 'unknown')
  ),
  CONSTRAINT bi_daily_metrics_entity_type_check CHECK (entity_type IN ('tenant', 'store')),
  CONSTRAINT bi_daily_metrics_value_reason_check CHECK (
    (value IS NOT NULL AND null_reason IS NULL)
    OR (value IS NULL AND null_reason IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS ix_bi_daily_metrics_current_query
  ON public.bi_daily_metrics (
    tenant_id, business_date, metric_code, entity_type, is_current
  );
CREATE UNIQUE INDEX IF NOT EXISTS uq_bi_daily_metrics_current_grain
  ON public.bi_daily_metrics (
    tenant_id, source_key, metric_definition_id, business_date,
    entity_type, entity_id, currency
  ) WHERE is_current;

CREATE OR REPLACE FUNCTION app.reject_bi_append_only_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'BI quality and metric-definition evidence is append-only';
END;
$$;

CREATE OR REPLACE FUNCTION app.protect_bi_versioned_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'BI versioned evidence cannot be deleted';
  END IF;
  IF (to_jsonb(NEW) - 'is_current') IS DISTINCT FROM (to_jsonb(OLD) - 'is_current')
     OR OLD.is_current = false OR NEW.is_current = true THEN
    RAISE EXCEPTION 'BI versioned evidence only permits current-to-superseded transition';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS bi_quality_checks_append_only ON public.bi_data_quality_checks;
CREATE TRIGGER bi_quality_checks_append_only
BEFORE UPDATE OR DELETE ON public.bi_data_quality_checks
FOR EACH ROW EXECUTE FUNCTION app.reject_bi_append_only_mutation();

DROP TRIGGER IF EXISTS bi_metric_definitions_append_only ON public.bi_metric_definitions;
CREATE TRIGGER bi_metric_definitions_append_only
BEFORE UPDATE OR DELETE ON public.bi_metric_definitions
FOR EACH ROW EXECUTE FUNCTION app.reject_bi_append_only_mutation();

DROP TRIGGER IF EXISTS bi_daily_facts_version_guard ON public.bi_daily_commerce_facts;
CREATE TRIGGER bi_daily_facts_version_guard
BEFORE UPDATE OR DELETE ON public.bi_daily_commerce_facts
FOR EACH ROW EXECUTE FUNCTION app.protect_bi_versioned_row();

DROP TRIGGER IF EXISTS bi_daily_metrics_version_guard ON public.bi_daily_metrics;
CREATE TRIGGER bi_daily_metrics_version_guard
BEFORE UPDATE OR DELETE ON public.bi_daily_metrics
FOR EACH ROW EXECUTE FUNCTION app.protect_bi_versioned_row();

DO $joukir_bi_rls$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'bi_ingestion_batches',
    'bi_data_quality_checks',
    'bi_daily_commerce_facts',
    'bi_metric_definitions',
    'bi_daily_metrics'
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
    EXECUTE format('DROP POLICY IF EXISTS worker_tenant_isolation ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY worker_tenant_isolation ON public.%I FOR ALL TO staffdeck_worker '
      'USING (tenant_id = app.current_staffdeck_tenant_id()) '
      'WITH CHECK (tenant_id = app.current_staffdeck_tenant_id())',
      table_name
    );
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC', table_name);
  END LOOP;
END
$joukir_bi_rls$;

GRANT SELECT, INSERT, UPDATE ON public.bi_ingestion_batches TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.bi_data_quality_checks TO staffdeck_runtime;
GRANT SELECT, INSERT, UPDATE ON public.bi_daily_commerce_facts TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.bi_metric_definitions TO staffdeck_runtime;
GRANT SELECT, INSERT, UPDATE ON public.bi_daily_metrics TO staffdeck_runtime;

GRANT SELECT, INSERT, UPDATE ON public.bi_ingestion_batches TO staffdeck_worker;
GRANT SELECT, INSERT ON public.bi_data_quality_checks TO staffdeck_worker;
GRANT SELECT, INSERT, UPDATE ON public.bi_daily_commerce_facts TO staffdeck_worker;
GRANT SELECT, INSERT ON public.bi_metric_definitions TO staffdeck_worker;
GRANT SELECT, INSERT, UPDATE ON public.bi_daily_metrics TO staffdeck_worker;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260908_bi_metric_pipeline_v1', now(), 'postgresql', 5, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
