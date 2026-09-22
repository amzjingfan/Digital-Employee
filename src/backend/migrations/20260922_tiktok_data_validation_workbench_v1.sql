BEGIN;

CREATE TABLE IF NOT EXISTS public.tiktok_data_validation_scopes (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  market varchar NOT NULL DEFAULT 'US',
  store_resource_id varchar,
  creator_scope_summary varchar NOT NULL DEFAULT '',
  business_owner_user_id varchar,
  data_owner_user_id varchar,
  status varchar NOT NULL DEFAULT 'draft',
  revision integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_tiktok_dv_scope_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_tiktok_dv_scope_tenant_market UNIQUE (tenant_id, market),
  CONSTRAINT fk_tiktok_dv_scope_tenant_store
    FOREIGN KEY (tenant_id, store_resource_id)
    REFERENCES public.business_resources(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_dv_scope_tenant_business_owner
    FOREIGN KEY (tenant_id, business_owner_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_dv_scope_tenant_data_owner
    FOREIGN KEY (tenant_id, data_owner_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT tiktok_dv_scope_market_check CHECK (market = 'US'),
  CONSTRAINT tiktok_dv_scope_status_check CHECK (status IN ('draft', 'active', 'closed')),
  CONSTRAINT tiktok_dv_scope_revision_check CHECK (revision > 0)
);

CREATE INDEX IF NOT EXISTS ix_tiktok_dv_scope_tenant_status
  ON public.tiktok_data_validation_scopes (tenant_id, status);

CREATE TABLE IF NOT EXISTS public.tiktok_field_contracts (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  field_code varchar NOT NULL,
  domain varchar NOT NULL,
  label varchar NOT NULL,
  data_type varchar NOT NULL,
  required boolean NOT NULL DEFAULT true,
  owner_user_id varchar,
  business_key varchar NOT NULL DEFAULT '',
  freshness_sla_seconds integer,
  missing_behavior varchar NOT NULL DEFAULT 'unknown',
  sources_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  status varchar NOT NULL DEFAULT 'draft',
  revision integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_tiktok_field_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_tiktok_field_tenant_code UNIQUE (tenant_id, field_code),
  CONSTRAINT fk_tiktok_field_tenant_owner
    FOREIGN KEY (tenant_id, owner_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT tiktok_field_domain_check CHECK (
    domain IN ('sample', 'order', 'logistics', 'video', 'attribution', 'gmv')
  ),
  CONSTRAINT tiktok_field_data_type_check CHECK (
    data_type IN ('string', 'datetime', 'decimal', 'integer', 'boolean', 'enum')
  ),
  CONSTRAINT tiktok_field_missing_behavior_check CHECK (
    missing_behavior IN ('unknown', 'manual_review', 'block_stage', 'not_applicable')
  ),
  CONSTRAINT tiktok_field_status_check CHECK (
    status IN ('draft', 'confirmed', 'blocked', 'not_applicable')
  ),
  CONSTRAINT tiktok_field_freshness_sla_check CHECK (
    freshness_sla_seconds IS NULL OR freshness_sla_seconds > 0
  ),
  CONSTRAINT tiktok_field_revision_check CHECK (revision > 0)
);

CREATE INDEX IF NOT EXISTS ix_tiktok_field_tenant_domain_status
  ON public.tiktok_field_contracts (tenant_id, domain, status);

CREATE TABLE IF NOT EXISTS public.tiktok_capability_evidence (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  entry_code varchar NOT NULL,
  entry_kind varchar NOT NULL,
  platform_domain varchar NOT NULL,
  action varchar NOT NULL,
  direction varchar NOT NULL,
  subject_key varchar NOT NULL DEFAULT 'global',
  resource_id varchar,
  required_scope varchar NOT NULL DEFAULT '',
  endpoint_or_artifact varchar NOT NULL DEFAULT '',
  api_version varchar NOT NULL DEFAULT '',
  evidence_level varchar NOT NULL DEFAULT 'E0',
  evidence_type varchar NOT NULL DEFAULT 'unverified',
  status varchar NOT NULL DEFAULT 'unverified',
  decision varchar,
  summary varchar NOT NULL DEFAULT '',
  evidence_ref varchar NOT NULL DEFAULT '',
  checked_by_user_id varchar,
  checked_at timestamptz,
  valid_until timestamptz,
  revision integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_tiktok_capability_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_tiktok_capability_tenant_entry_subject
    UNIQUE (tenant_id, entry_code, subject_key),
  CONSTRAINT fk_tiktok_capability_tenant_resource
    FOREIGN KEY (tenant_id, resource_id)
    REFERENCES public.business_resources(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_capability_tenant_checker
    FOREIGN KEY (tenant_id, checked_by_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT tiktok_capability_kind_check CHECK (
    entry_kind IN ('capability', 'provider_decision')
  ),
  CONSTRAINT tiktok_capability_direction_check CHECK (
    direction IN ('read', 'write', 'export', 'decision')
  ),
  CONSTRAINT tiktok_capability_level_check CHECK (evidence_level IN ('E0', 'E1', 'E2', 'E3')),
  CONSTRAINT tiktok_capability_type_check CHECK (
    evidence_type IN (
      'unverified', 'official_docs', 'contract', 'mock', 'sandbox',
      'approved_export', 'real_account'
    )
  ),
  CONSTRAINT tiktok_capability_status_check CHECK (
    status IN ('unverified', 'verified', 'blocked', 'not_applicable')
  ),
  CONSTRAINT tiktok_capability_decision_check CHECK (
    decision IS NULL OR decision IN ('use', 'defer', 'reject')
  ),
  CONSTRAINT tiktok_capability_revision_check CHECK (revision > 0)
);

CREATE INDEX IF NOT EXISTS ix_tiktok_capability_tenant_kind_status
  ON public.tiktok_capability_evidence (tenant_id, entry_kind, status);

CREATE TABLE IF NOT EXISTS public.tiktok_data_validation_runs (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  mode varchar NOT NULL DEFAULT 'mock',
  catalog_version varchar NOT NULL,
  dataset_digest varchar NOT NULL,
  record_count integer NOT NULL DEFAULT 0,
  status varchar NOT NULL,
  workbench_ready_snapshot boolean NOT NULL DEFAULT false,
  real_data_ready_snapshot boolean NOT NULL DEFAULT false,
  checks_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  issues_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  started_by_user_id varchar NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_tiktok_dv_run_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT fk_tiktok_dv_run_tenant_starter
    FOREIGN KEY (tenant_id, started_by_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT tiktok_dv_run_mode_check CHECK (mode = 'mock'),
  CONSTRAINT tiktok_dv_run_status_check CHECK (status IN ('passed', 'failed')),
  CONSTRAINT tiktok_dv_run_record_count_check CHECK (record_count >= 0),
  CONSTRAINT tiktok_dv_run_real_ready_check CHECK (real_data_ready_snapshot = false)
);

CREATE INDEX IF NOT EXISTS ix_tiktok_dv_run_tenant_created
  ON public.tiktok_data_validation_runs (tenant_id, created_at DESC);

CREATE OR REPLACE FUNCTION public.reject_tiktok_data_validation_run_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'tiktok data validation runs are append-only';
END;
$$;

DROP TRIGGER IF EXISTS tiktok_data_validation_runs_append_only
  ON public.tiktok_data_validation_runs;
CREATE TRIGGER tiktok_data_validation_runs_append_only
BEFORE UPDATE OR DELETE ON public.tiktok_data_validation_runs
FOR EACH ROW EXECUTE FUNCTION public.reject_tiktok_data_validation_run_mutation();

ALTER TABLE public.tiktok_data_validation_scopes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_data_validation_scopes FORCE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_field_contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_field_contracts FORCE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_capability_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_capability_evidence FORCE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_data_validation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_data_validation_runs FORCE ROW LEVEL SECURITY;

DO $joukir_tiktok_data_validation_rls$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'tiktok_data_validation_scopes',
    'tiktok_field_contracts',
    'tiktok_capability_evidence',
    'tiktok_data_validation_runs'
  ]
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS runtime_tenant_isolation ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY runtime_tenant_isolation ON public.%I FOR ALL TO staffdeck_runtime '
      'USING (tenant_id = app.current_staffdeck_tenant_id()) '
      'WITH CHECK (tenant_id = app.current_staffdeck_tenant_id())',
      table_name
    );
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
$joukir_tiktok_data_validation_rls$;

GRANT SELECT, INSERT, UPDATE ON public.tiktok_data_validation_scopes TO staffdeck_runtime;
GRANT SELECT, INSERT, UPDATE ON public.tiktok_field_contracts TO staffdeck_runtime;
GRANT SELECT, INSERT, UPDATE ON public.tiktok_capability_evidence TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.tiktok_data_validation_runs TO staffdeck_runtime;

GRANT SELECT, INSERT, UPDATE ON public.tiktok_data_validation_scopes TO staffdeck_worker;
GRANT SELECT, INSERT, UPDATE ON public.tiktok_field_contracts TO staffdeck_worker;
GRANT SELECT, INSERT, UPDATE ON public.tiktok_capability_evidence TO staffdeck_worker;
GRANT SELECT, INSERT ON public.tiktok_data_validation_runs TO staffdeck_worker;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260922_tiktok_data_validation_workbench_v1', now(), 'postgresql', 4, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
