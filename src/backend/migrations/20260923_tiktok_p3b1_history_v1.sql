BEGIN;

CREATE TABLE IF NOT EXISTS public.tiktok_history_batches (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  recorded_run_id varchar NOT NULL,
  scope_id varchar NOT NULL,
  source_kind varchar NOT NULL,
  source_label varchar NOT NULL,
  assigned_bd_user_id varchar NOT NULL,
  imported_by_user_id varchar NOT NULL,
  dataset_digest varchar NOT NULL,
  metric_version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_tiktok_history_batch_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_tiktok_history_batch_run UNIQUE (tenant_id, recorded_run_id),
  CONSTRAINT fk_tiktok_history_batch_run FOREIGN KEY (tenant_id, recorded_run_id)
    REFERENCES public.tiktok_data_validation_runs(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_history_batch_scope FOREIGN KEY (tenant_id, scope_id)
    REFERENCES public.tiktok_data_validation_scopes(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_history_batch_assignee FOREIGN KEY (tenant_id, assigned_bd_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_history_batch_importer FOREIGN KEY (tenant_id, imported_by_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT tiktok_history_batch_source_check
    CHECK (source_kind IN ('synthetic', 'approved_redacted_history')),
  CONSTRAINT tiktok_history_batch_metric_version_check CHECK (metric_version > 0)
);

CREATE TABLE IF NOT EXISTS public.tiktok_history_facts (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  scope_id varchar NOT NULL,
  batch_id varchar NOT NULL,
  source_label varchar NOT NULL,
  domain varchar NOT NULL,
  business_key varchar NOT NULL,
  observed_at timestamptz NOT NULL,
  values_json jsonb NOT NULL,
  fact_digest varchar NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_tiktok_history_fact_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_tiktok_history_fact_identity
    UNIQUE (tenant_id, scope_id, source_label, domain, business_key, observed_at),
  CONSTRAINT fk_tiktok_history_fact_batch FOREIGN KEY (tenant_id, batch_id)
    REFERENCES public.tiktok_history_batches(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_history_fact_scope FOREIGN KEY (tenant_id, scope_id)
    REFERENCES public.tiktok_data_validation_scopes(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT tiktok_history_fact_domain_check
    CHECK (domain IN ('sample', 'order', 'logistics', 'video', 'attribution', 'gmv'))
);
CREATE INDEX IF NOT EXISTS ix_tiktok_history_fact_tenant_domain_observed
  ON public.tiktok_history_facts (tenant_id, domain, observed_at DESC);

CREATE TABLE IF NOT EXISTS public.tiktok_history_metric_definitions (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  code varchar NOT NULL,
  version integer NOT NULL,
  label varchar NOT NULL,
  formula varchar NOT NULL,
  unit varchar NOT NULL,
  numerator varchar,
  denominator varchar,
  timezone varchar NOT NULL,
  "window" varchar NOT NULL,
  status varchar NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_tiktok_history_metric_version UNIQUE (tenant_id, code, version),
  CONSTRAINT tiktok_history_metric_version_check CHECK (version > 0)
);

CREATE TABLE IF NOT EXISTS public.tiktok_history_reconciliations (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  fact_id varchar NOT NULL,
  verdict varchar NOT NULL,
  reason varchar NOT NULL,
  comparison_ref varchar NOT NULL,
  reviewed_by_user_id varchar NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_tiktok_history_reconciliation_fact FOREIGN KEY (tenant_id, fact_id)
    REFERENCES public.tiktok_history_facts(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_history_reconciliation_reviewer
    FOREIGN KEY (tenant_id, reviewed_by_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT tiktok_history_reconciliation_verdict_check
    CHECK (verdict IN ('matched', 'difference', 'needs_review'))
);
CREATE INDEX IF NOT EXISTS ix_tiktok_history_reconciliation_tenant_fact
  ON public.tiktok_history_reconciliations (tenant_id, fact_id);

CREATE TABLE IF NOT EXISTS public.tiktok_history_signoffs (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  scope_id varchar NOT NULL,
  scope_revision integer NOT NULL,
  review_digest varchar NOT NULL,
  reviewed_count integer NOT NULL,
  approval_ref varchar NOT NULL,
  source_evidence_ref varchar NOT NULL,
  confirmed_by_user_id varchar NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_tiktok_history_signoff_scope FOREIGN KEY (tenant_id, scope_id)
    REFERENCES public.tiktok_data_validation_scopes(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_history_signoff_owner FOREIGN KEY (tenant_id, confirmed_by_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT tiktok_history_signoff_count_check CHECK (reviewed_count >= 30)
);

CREATE OR REPLACE FUNCTION public.reject_tiktok_history_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'tiktok history is append-only';
END;
$$;

CREATE TRIGGER tiktok_history_batches_append_only
BEFORE UPDATE OR DELETE ON public.tiktok_history_batches
FOR EACH ROW EXECUTE FUNCTION public.reject_tiktok_history_mutation();
CREATE TRIGGER tiktok_history_facts_append_only
BEFORE UPDATE OR DELETE ON public.tiktok_history_facts
FOR EACH ROW EXECUTE FUNCTION public.reject_tiktok_history_mutation();
CREATE TRIGGER tiktok_history_metric_definitions_append_only
BEFORE UPDATE OR DELETE ON public.tiktok_history_metric_definitions
FOR EACH ROW EXECUTE FUNCTION public.reject_tiktok_history_mutation();
CREATE TRIGGER tiktok_history_reconciliations_append_only
BEFORE UPDATE OR DELETE ON public.tiktok_history_reconciliations
FOR EACH ROW EXECUTE FUNCTION public.reject_tiktok_history_mutation();
CREATE TRIGGER tiktok_history_signoffs_append_only
BEFORE UPDATE OR DELETE ON public.tiktok_history_signoffs
FOR EACH ROW EXECUTE FUNCTION public.reject_tiktok_history_mutation();

ALTER TABLE public.tiktok_history_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_history_batches FORCE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_history_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_history_facts FORCE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_history_metric_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_history_metric_definitions FORCE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_history_reconciliations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_history_reconciliations FORCE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_history_signoffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_history_signoffs FORCE ROW LEVEL SECURITY;

DO $joukir_tiktok_history_rls$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'tiktok_history_batches', 'tiktok_history_facts',
    'tiktok_history_metric_definitions', 'tiktok_history_reconciliations',
    'tiktok_history_signoffs'
  ] LOOP
    EXECUTE format(
      'CREATE POLICY runtime_tenant_isolation ON public.%I FOR ALL TO staffdeck_runtime '
      'USING (tenant_id = app.current_staffdeck_tenant_id()) '
      'WITH CHECK (tenant_id = app.current_staffdeck_tenant_id())', table_name
    );
    EXECUTE format(
      'CREATE POLICY worker_tenant_isolation ON public.%I FOR ALL TO staffdeck_worker '
      'USING (tenant_id = app.current_staffdeck_tenant_id()) '
      'WITH CHECK (tenant_id = app.current_staffdeck_tenant_id())', table_name
    );
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC', table_name);
  END LOOP;
END
$joukir_tiktok_history_rls$;

GRANT SELECT, INSERT ON public.tiktok_history_batches TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.tiktok_history_facts TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.tiktok_history_metric_definitions TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.tiktok_history_reconciliations TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.tiktok_history_signoffs TO staffdeck_runtime;

GRANT SELECT, INSERT ON public.tiktok_history_batches TO staffdeck_worker;
GRANT SELECT, INSERT ON public.tiktok_history_facts TO staffdeck_worker;
GRANT SELECT, INSERT ON public.tiktok_history_metric_definitions TO staffdeck_worker;
GRANT SELECT, INSERT ON public.tiktok_history_reconciliations TO staffdeck_worker;
GRANT SELECT, INSERT ON public.tiktok_history_signoffs TO staffdeck_worker;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260923_tiktok_p3b1_history_v1', now(), 'postgresql', 5, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
