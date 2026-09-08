BEGIN;

CREATE TABLE IF NOT EXISTS public.design_qc_reports (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  asset_version_id varchar NOT NULL REFERENCES public.creative_asset_versions(id) ON DELETE RESTRICT,
  asset_digest varchar NOT NULL,
  brief_id varchar NOT NULL REFERENCES public.creative_briefs(id) ON DELETE RESTRICT,
  store_resource_id varchar NOT NULL REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  snapshot_digest varchar NOT NULL,
  checker_version varchar NOT NULL,
  overall_status varchar NOT NULL DEFAULT 'unknown',
  findings_json json NOT NULL DEFAULT '[]'::json,
  input_digest varchar NOT NULL,
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_design_qc_input UNIQUE (tenant_id, asset_version_id, input_digest),
  CONSTRAINT design_qc_reports_status_check CHECK (
    overall_status IN ('pass', 'fail', 'unknown', 'not_applicable')
  )
);
CREATE INDEX IF NOT EXISTS ix_design_qc_reports_tenant_id
  ON public.design_qc_reports (tenant_id);
CREATE INDEX IF NOT EXISTS ix_design_qc_reports_asset_created
  ON public.design_qc_reports (tenant_id, asset_version_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_design_qc_reports_store_status
  ON public.design_qc_reports (tenant_id, store_resource_id, overall_status);
CREATE INDEX IF NOT EXISTS ix_design_qc_reports_input_digest
  ON public.design_qc_reports (input_digest);

CREATE OR REPLACE FUNCTION app.reject_design_qc_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'design QC reports are append-only';
END;
$$;

DROP TRIGGER IF EXISTS design_qc_reports_append_only ON public.design_qc_reports;
CREATE TRIGGER design_qc_reports_append_only
BEFORE UPDATE OR DELETE ON public.design_qc_reports
FOR EACH ROW EXECUTE FUNCTION app.reject_design_qc_mutation();

ALTER TABLE public.design_qc_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.design_qc_reports FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.design_qc_reports;
CREATE POLICY runtime_tenant_isolation ON public.design_qc_reports FOR ALL TO staffdeck_runtime
  USING (tenant_id = app.current_staffdeck_tenant_id())
  WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
DROP POLICY IF EXISTS worker_all_tenants ON public.design_qc_reports;
CREATE POLICY worker_all_tenants ON public.design_qc_reports FOR ALL TO staffdeck_worker
  USING (true) WITH CHECK (true);
REVOKE ALL ON public.design_qc_reports FROM PUBLIC;
GRANT SELECT, INSERT ON public.design_qc_reports
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260907_design_qc_reports_v1', now(), 'postgresql', 1, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
