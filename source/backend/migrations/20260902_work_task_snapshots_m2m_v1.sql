BEGIN;

CREATE TABLE IF NOT EXISTS public.agent_service_identities (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  agent_id varchar NOT NULL,
  business_role varchar NOT NULL,
  provider varchar NOT NULL DEFAULT 'casdoor',
  issuer varchar NOT NULL,
  token_endpoint varchar NOT NULL,
  jwks_uri varchar NOT NULL,
  application_owner varchar NOT NULL,
  application_name varchar NOT NULL,
  client_id varchar NOT NULL,
  client_id_fingerprint varchar NOT NULL,
  credential_ref varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'active',
  token_ttl_seconds integer NOT NULL DEFAULT 900,
  last_verified_at timestamp without time zone,
  last_verified_subject varchar,
  last_error_code varchar,
  metadata_json json NOT NULL DEFAULT '{}'::json,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_agent_service_identity_agent UNIQUE (tenant_id, agent_id),
  CONSTRAINT uq_agent_service_identity_client UNIQUE (provider, client_id),
  CONSTRAINT agent_service_identities_status_check
    CHECK (status IN ('active', 'disabled', 'error')),
  CONSTRAINT agent_service_identities_token_ttl_check
    CHECK (token_ttl_seconds BETWEEN 60 AND 3600),
  CONSTRAINT agent_service_identities_agent_fk
    FOREIGN KEY (agent_id) REFERENCES public.agent_profiles(id) ON DELETE RESTRICT
);

ALTER TABLE public.work_task_runs
  ADD COLUMN IF NOT EXISTS service_identity_id varchar,
  ADD COLUMN IF NOT EXISTS execution_snapshot_id varchar,
  ADD COLUMN IF NOT EXISTS snapshot_digest varchar;

CREATE TABLE IF NOT EXISTS public.work_task_execution_snapshots (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  task_id varchar NOT NULL,
  run_id varchar NOT NULL,
  service_identity_id varchar NOT NULL,
  agent_id varchar NOT NULL,
  agent_snapshot_json json NOT NULL DEFAULT '{}'::json,
  sop_snapshots_json json NOT NULL DEFAULT '[]'::json,
  knowledge_snapshots_json json NOT NULL DEFAULT '[]'::json,
  tool_snapshots_json json NOT NULL DEFAULT '[]'::json,
  capability_snapshot_json json NOT NULL DEFAULT '{}'::json,
  service_identity_snapshot_json json NOT NULL DEFAULT '{}'::json,
  snapshot_digest varchar NOT NULL,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_work_task_execution_snapshot_run UNIQUE (tenant_id, run_id),
  CONSTRAINT work_task_execution_snapshots_task_fk
    FOREIGN KEY (task_id) REFERENCES public.work_tasks(id) ON DELETE RESTRICT,
  CONSTRAINT work_task_execution_snapshots_run_fk
    FOREIGN KEY (run_id) REFERENCES public.work_task_runs(id) ON DELETE RESTRICT,
  CONSTRAINT work_task_execution_snapshots_identity_fk
    FOREIGN KEY (service_identity_id) REFERENCES public.agent_service_identities(id) ON DELETE RESTRICT,
  CONSTRAINT work_task_execution_snapshots_agent_fk
    FOREIGN KEY (agent_id) REFERENCES public.agent_profiles(id) ON DELETE RESTRICT
);

DO $work_task_snapshot_foreign_keys$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'work_task_runs_service_identity_fk'
  ) THEN
    ALTER TABLE public.work_task_runs
      ADD CONSTRAINT work_task_runs_service_identity_fk
      FOREIGN KEY (service_identity_id) REFERENCES public.agent_service_identities(id) ON DELETE RESTRICT;
  END IF;
END
$work_task_snapshot_foreign_keys$;

CREATE INDEX IF NOT EXISTS ix_agent_service_identities_tenant_id
  ON public.agent_service_identities (tenant_id);
CREATE INDEX IF NOT EXISTS ix_agent_service_identities_agent_id
  ON public.agent_service_identities (agent_id);
CREATE INDEX IF NOT EXISTS ix_agent_service_identities_business_role
  ON public.agent_service_identities (business_role);
CREATE INDEX IF NOT EXISTS ix_agent_service_identities_status
  ON public.agent_service_identities (status);
CREATE INDEX IF NOT EXISTS ix_agent_service_identities_tenant_role
  ON public.agent_service_identities (tenant_id, business_role, status);
CREATE INDEX IF NOT EXISTS ix_work_task_runs_service_identity_id
  ON public.work_task_runs (service_identity_id);
CREATE INDEX IF NOT EXISTS ix_work_task_runs_execution_snapshot_id
  ON public.work_task_runs (execution_snapshot_id);
CREATE INDEX IF NOT EXISTS ix_work_task_runs_snapshot_digest
  ON public.work_task_runs (snapshot_digest);
CREATE INDEX IF NOT EXISTS ix_work_task_execution_snapshots_tenant_id
  ON public.work_task_execution_snapshots (tenant_id);
CREATE INDEX IF NOT EXISTS ix_work_task_execution_snapshots_task_id
  ON public.work_task_execution_snapshots (task_id);
CREATE INDEX IF NOT EXISTS ix_work_task_execution_snapshots_run_id
  ON public.work_task_execution_snapshots (run_id);
CREATE INDEX IF NOT EXISTS ix_work_task_execution_snapshots_service_identity_id
  ON public.work_task_execution_snapshots (service_identity_id);
CREATE INDEX IF NOT EXISTS ix_work_task_execution_snapshots_agent_id
  ON public.work_task_execution_snapshots (agent_id);
CREATE INDEX IF NOT EXISTS ix_work_task_execution_snapshots_snapshot_digest
  ON public.work_task_execution_snapshots (snapshot_digest);
CREATE INDEX IF NOT EXISTS ix_work_task_execution_snapshots_task_time
  ON public.work_task_execution_snapshots (task_id, created_at DESC);

CREATE OR REPLACE FUNCTION app.reject_work_task_snapshot_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'work_task_execution_snapshots is append-only';
END;
$$;

DROP TRIGGER IF EXISTS work_task_execution_snapshots_append_only
  ON public.work_task_execution_snapshots;
CREATE TRIGGER work_task_execution_snapshots_append_only
BEFORE UPDATE OR DELETE ON public.work_task_execution_snapshots
FOR EACH ROW EXECUTE FUNCTION app.reject_work_task_snapshot_mutation();

ALTER TABLE public.agent_service_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_service_identities FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.agent_service_identities;
CREATE POLICY runtime_tenant_isolation ON public.agent_service_identities
FOR ALL TO staffdeck_runtime
USING (tenant_id = app.current_staffdeck_tenant_id())
WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
DROP POLICY IF EXISTS worker_all_tenants ON public.agent_service_identities;
CREATE POLICY worker_all_tenants ON public.agent_service_identities
FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS migrator_all_tenants ON public.agent_service_identities;
CREATE POLICY migrator_all_tenants ON public.agent_service_identities
FOR ALL TO staffdeck_migrator USING (true) WITH CHECK (true);

ALTER TABLE public.work_task_execution_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.work_task_execution_snapshots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.work_task_execution_snapshots;
CREATE POLICY runtime_tenant_isolation ON public.work_task_execution_snapshots
FOR ALL TO staffdeck_runtime
USING (tenant_id = app.current_staffdeck_tenant_id())
WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
DROP POLICY IF EXISTS worker_all_tenants ON public.work_task_execution_snapshots;
CREATE POLICY worker_all_tenants ON public.work_task_execution_snapshots
FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

REVOKE ALL ON public.agent_service_identities FROM PUBLIC;
REVOKE ALL ON public.work_task_execution_snapshots FROM PUBLIC;
REVOKE INSERT, UPDATE, DELETE ON public.agent_service_identities
  FROM staffdeck_runtime, staffdeck_worker;
GRANT SELECT ON public.agent_service_identities TO staffdeck_runtime, staffdeck_worker;
GRANT UPDATE (last_verified_at, last_verified_subject, last_error_code, updated_at)
  ON public.agent_service_identities TO staffdeck_runtime, staffdeck_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.agent_service_identities TO staffdeck_migrator;
GRANT SELECT, INSERT ON public.work_task_execution_snapshots TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.work_task_execution_snapshots TO staffdeck_worker;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260902_work_task_snapshots_m2m_v1', now(), 'postgresql', 2, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
