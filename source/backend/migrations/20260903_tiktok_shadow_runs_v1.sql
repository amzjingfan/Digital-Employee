BEGIN;

CREATE TABLE IF NOT EXISTS public.tiktok_shadow_runs (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  status varchar NOT NULL DEFAULT 'running',
  started_at timestamp without time zone NOT NULL,
  ends_at timestamp without time zone NOT NULL,
  last_heartbeat_at timestamp without time zone NOT NULL,
  observation_count integer NOT NULL DEFAULT 0,
  error_count integer NOT NULL DEFAULT 0,
  started_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  baseline_json json NOT NULL DEFAULT '{}'::json,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT tiktok_shadow_runs_status_check
    CHECK (status IN ('planned', 'running', 'completed', 'expired', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS ix_tiktok_shadow_runs_tenant_status
  ON public.tiktok_shadow_runs (tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_tiktok_shadow_runs_tenant_ends
  ON public.tiktok_shadow_runs (tenant_id, ends_at);

ALTER TABLE public.tiktok_shadow_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_shadow_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.tiktok_shadow_runs;
DROP POLICY IF EXISTS worker_all_tenants ON public.tiktok_shadow_runs;
CREATE POLICY runtime_tenant_isolation ON public.tiktok_shadow_runs
  FOR ALL TO staffdeck_runtime
  USING (tenant_id = app.current_staffdeck_tenant_id())
  WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
CREATE POLICY worker_all_tenants ON public.tiktok_shadow_runs
  FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.tiktok_shadow_runs
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260903_tiktok_shadow_runs_v1', now(), 'postgresql', 1, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
