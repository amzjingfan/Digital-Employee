BEGIN;

CREATE TABLE IF NOT EXISTS public.creative_evidence_records (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  evidence_type varchar NOT NULL,
  source_ref varchar NOT NULL,
  version varchar NOT NULL,
  payload_json json NOT NULL DEFAULT '{}'::json,
  content_digest varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'draft',
  effective_at timestamp without time zone NOT NULL,
  expires_at timestamp without time zone,
  synced_at timestamp without time zone NOT NULL,
  sync_error varchar,
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_creative_evidence_version UNIQUE (tenant_id, evidence_type, source_ref, version),
  CONSTRAINT creative_evidence_status_check CHECK (
    status IN ('draft', 'verified', 'expired', 'revoked')
  ),
  CONSTRAINT creative_evidence_type_check CHECK (
    evidence_type IN ('facts', 'brand', 'platform_spec')
  )
);
CREATE INDEX IF NOT EXISTS ix_creative_evidence_active_lookup
  ON public.creative_evidence_records (tenant_id, evidence_type, source_ref, version, status);
CREATE INDEX IF NOT EXISTS ix_creative_evidence_expiry
  ON public.creative_evidence_records (tenant_id, status, expires_at);

CREATE TABLE IF NOT EXISTS public.creative_delivery_checklists (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  brief_id varchar NOT NULL REFERENCES public.creative_briefs(id) ON DELETE RESTRICT,
  store_resource_id varchar NOT NULL REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  product_key varchar NOT NULL,
  asset_version_ids_json json NOT NULL DEFAULT '[]'::json,
  qc_report_ids_json json NOT NULL DEFAULT '[]'::json,
  checklist_json json NOT NULL DEFAULT '[]'::json,
  blockers_json json NOT NULL DEFAULT '[]'::json,
  delivery_digest varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'blocked',
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  delivered_at timestamp without time zone,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_creative_delivery_digest UNIQUE (tenant_id, brief_id, delivery_digest),
  CONSTRAINT creative_delivery_status_check CHECK (
    status IN ('blocked', 'ready', 'delivered', 'failed')
  )
);
CREATE INDEX IF NOT EXISTS ix_creative_delivery_brief_created
  ON public.creative_delivery_checklists (tenant_id, brief_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_creative_delivery_status
  ON public.creative_delivery_checklists (tenant_id, status);

CREATE TABLE IF NOT EXISTS public.creative_generation_requests (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  brief_id varchar NOT NULL REFERENCES public.creative_briefs(id) ON DELETE RESTRICT,
  provider_key varchar NOT NULL,
  idempotency_key varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'queued',
  request_json json NOT NULL DEFAULT '{}'::json,
  response_json json NOT NULL DEFAULT '{}'::json,
  external_request_id varchar,
  error_code varchar,
  error_message varchar,
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_creative_generation_key UNIQUE (tenant_id, provider_key, idempotency_key),
  CONSTRAINT creative_generation_status_check CHECK (
    status IN ('queued', 'submitted', 'succeeded', 'failed', 'cancelled')
  )
);
CREATE INDEX IF NOT EXISTS ix_creative_generation_brief_created
  ON public.creative_generation_requests (tenant_id, brief_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_creative_generation_status
  ON public.creative_generation_requests (tenant_id, status);

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'creative_evidence_records',
    'creative_delivery_checklists',
    'creative_generation_requests'
  ] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS runtime_tenant_isolation ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY runtime_tenant_isolation ON public.%I FOR ALL TO staffdeck_runtime '
      'USING (tenant_id = app.current_staffdeck_tenant_id()) '
      'WITH CHECK (tenant_id = app.current_staffdeck_tenant_id())', table_name
    );
    EXECUTE format('DROP POLICY IF EXISTS worker_all_tenants ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY worker_all_tenants ON public.%I FOR ALL TO staffdeck_worker '
      'USING (true) WITH CHECK (true)', table_name
    );
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC', table_name);
  END LOOP;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON public.creative_evidence_records
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT, UPDATE ON public.creative_delivery_checklists
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT, UPDATE ON public.creative_generation_requests
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260907_creative_production_v1', now(), 'postgresql', 3, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
