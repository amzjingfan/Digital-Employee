BEGIN;

CREATE TABLE IF NOT EXISTS public.external_authorizations (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  provider varchar NOT NULL DEFAULT 'tiktok',
  authorization_type varchar NOT NULL,
  subject_id varchar NOT NULL,
  resource_id varchar,
  scopes_json json NOT NULL DEFAULT '[]'::json,
  credential_ref varchar,
  token_fingerprint varchar,
  status varchar NOT NULL DEFAULT 'active',
  expires_at timestamp without time zone,
  revision integer NOT NULL DEFAULT 1,
  metadata_json json NOT NULL DEFAULT '{}'::json,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_external_authorization_subject_resource
    UNIQUE (tenant_id, provider, authorization_type, subject_id, resource_id),
  CONSTRAINT external_authorizations_provider_check CHECK (provider IN ('tiktok')),
  CONSTRAINT external_authorizations_type_check
    CHECK (authorization_type IN ('seller', 'creator', 'partner', 'ads', 'social')),
  CONSTRAINT external_authorizations_status_check
    CHECK (status IN ('active', 'expired', 'revoked', 'error'))
);

CREATE INDEX IF NOT EXISTS ix_external_authorizations_tenant_status
  ON public.external_authorizations (tenant_id, status);

CREATE TABLE IF NOT EXISTS public.connector_sync_states (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  connector_type varchar NOT NULL,
  resource_id varchar,
  cursor_ref varchar,
  watermark_at timestamp without time zone,
  status varchar NOT NULL DEFAULT 'idle',
  last_error_code varchar,
  revision integer NOT NULL DEFAULT 1,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_connector_sync_scope UNIQUE (tenant_id, connector_type, resource_id),
  CONSTRAINT connector_sync_states_status_check
    CHECK (status IN ('idle', 'running', 'succeeded', 'failed'))
);

CREATE INDEX IF NOT EXISTS ix_connector_sync_states_tenant_status
  ON public.connector_sync_states (tenant_id, status);

CREATE TABLE IF NOT EXISTS public.tiktok_oauth_states (
  state_hash varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  authorization_type varchar NOT NULL,
  subject_id varchar NOT NULL,
  resource_id varchar,
  scopes_json json NOT NULL DEFAULT '[]'::json,
  code_challenge varchar NOT NULL,
  flow varchar NOT NULL DEFAULT 'mock',
  return_to varchar NOT NULL DEFAULT '/enterprise/tiktok',
  code_hash varchar,
  code_expires_at timestamp without time zone,
  approved_at timestamp without time zone,
  expires_at timestamp without time zone NOT NULL,
  created_at timestamp without time zone NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_tiktok_oauth_states_tenant_expires
  ON public.tiktok_oauth_states (tenant_id, expires_at);
ALTER TABLE public.tiktok_oauth_states
  ADD COLUMN IF NOT EXISTS flow varchar NOT NULL DEFAULT 'mock';
CREATE INDEX IF NOT EXISTS ix_tiktok_oauth_states_flow
  ON public.tiktok_oauth_states (flow);

ALTER TABLE public.external_authorizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.external_authorizations FORCE ROW LEVEL SECURITY;
ALTER TABLE public.connector_sync_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.connector_sync_states FORCE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_oauth_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_oauth_states FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.external_authorizations;
DROP POLICY IF EXISTS worker_all_tenants ON public.external_authorizations;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.connector_sync_states;
DROP POLICY IF EXISTS worker_all_tenants ON public.connector_sync_states;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.tiktok_oauth_states;
DROP POLICY IF EXISTS worker_all_tenants ON public.tiktok_oauth_states;
CREATE POLICY runtime_tenant_isolation ON public.external_authorizations
  FOR ALL TO staffdeck_runtime
  USING (tenant_id = app.current_staffdeck_tenant_id())
  WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
CREATE POLICY worker_all_tenants ON public.external_authorizations
  FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);
CREATE POLICY runtime_tenant_isolation ON public.connector_sync_states
  FOR ALL TO staffdeck_runtime
  USING (tenant_id = app.current_staffdeck_tenant_id())
  WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
CREATE POLICY worker_all_tenants ON public.connector_sync_states
  FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);
CREATE POLICY runtime_tenant_isolation ON public.tiktok_oauth_states
  FOR ALL TO staffdeck_runtime
  USING (tenant_id = app.current_staffdeck_tenant_id())
  WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
CREATE POLICY worker_all_tenants ON public.tiktok_oauth_states
  FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.external_authorizations
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.connector_sync_states
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.tiktok_oauth_states
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260903_tiktok_authorizations_v1', now(), 'postgresql', 3, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
