BEGIN;

CREATE TABLE IF NOT EXISTS public.business_resources (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  resource_type varchar NOT NULL,
  code varchar NOT NULL,
  name varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'active',
  created_by_user_id varchar NOT NULL,
  metadata_json json NOT NULL DEFAULT '{}'::json,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_business_resource_code UNIQUE (tenant_id, resource_type, code),
  CONSTRAINT business_resources_type_check
    CHECK (resource_type IN ('store', 'carrier', 'ad_account', 'supplier')),
  CONSTRAINT business_resources_status_check
    CHECK (status IN ('active', 'inactive', 'archived'))
);

CREATE TABLE IF NOT EXISTS public.business_resource_scopes (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  resource_id varchar NOT NULL,
  business_role varchar NOT NULL,
  access_level varchar NOT NULL DEFAULT 'operator',
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_business_resource_role_scope UNIQUE (tenant_id, resource_id, business_role),
  CONSTRAINT business_resource_scopes_access_check
    CHECK (access_level IN ('viewer', 'operator')),
  CONSTRAINT business_resource_scopes_resource_fk
    FOREIGN KEY (resource_id) REFERENCES public.business_resources(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.high_risk_action_requests (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  resource_id varchar NOT NULL,
  resource_type varchar NOT NULL,
  resource_name varchar NOT NULL,
  action_type varchar NOT NULL,
  summary varchar NOT NULL,
  payload_json json NOT NULL DEFAULT '{}'::json,
  status varchar NOT NULL DEFAULT 'pending',
  requester_user_id varchar NOT NULL,
  requester_business_role varchar NOT NULL,
  decided_by_user_id varchar,
  decision_reason varchar,
  requested_at timestamp without time zone NOT NULL,
  decided_at timestamp without time zone,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT high_risk_action_requests_status_check
    CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
  CONSTRAINT high_risk_action_requests_resource_fk
    FOREIGN KEY (resource_id) REFERENCES public.business_resources(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS public.high_risk_action_events (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  request_id varchar NOT NULL,
  event_type varchar NOT NULL,
  actor_user_id varchar NOT NULL,
  actor_business_role varchar NOT NULL,
  detail_json json NOT NULL DEFAULT '{}'::json,
  occurred_at timestamp without time zone NOT NULL,
  CONSTRAINT high_risk_action_events_type_check
    CHECK (event_type IN ('requested', 'approved', 'rejected', 'cancelled')),
  CONSTRAINT high_risk_action_events_request_fk
    FOREIGN KEY (request_id) REFERENCES public.high_risk_action_requests(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_business_resources_tenant_id ON public.business_resources (tenant_id);
CREATE INDEX IF NOT EXISTS ix_business_resources_resource_type ON public.business_resources (resource_type);
CREATE INDEX IF NOT EXISTS ix_business_resources_status ON public.business_resources (status);
CREATE INDEX IF NOT EXISTS ix_business_resources_created_by_user_id ON public.business_resources (created_by_user_id);
CREATE INDEX IF NOT EXISTS ix_business_resources_created_at ON public.business_resources (created_at);
CREATE INDEX IF NOT EXISTS ix_business_resources_tenant_type_status
  ON public.business_resources (tenant_id, resource_type, status);

CREATE INDEX IF NOT EXISTS ix_business_resource_scopes_tenant_id ON public.business_resource_scopes (tenant_id);
CREATE INDEX IF NOT EXISTS ix_business_resource_scopes_resource_id ON public.business_resource_scopes (resource_id);
CREATE INDEX IF NOT EXISTS ix_business_resource_scopes_business_role ON public.business_resource_scopes (business_role);
CREATE INDEX IF NOT EXISTS ix_business_resource_scopes_access_level ON public.business_resource_scopes (access_level);
CREATE INDEX IF NOT EXISTS ix_business_resource_scopes_tenant_role
  ON public.business_resource_scopes (tenant_id, business_role, access_level);

CREATE INDEX IF NOT EXISTS ix_high_risk_action_requests_tenant_id ON public.high_risk_action_requests (tenant_id);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_requests_resource_id ON public.high_risk_action_requests (resource_id);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_requests_resource_type ON public.high_risk_action_requests (resource_type);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_requests_action_type ON public.high_risk_action_requests (action_type);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_requests_status ON public.high_risk_action_requests (status);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_requests_requester_user_id ON public.high_risk_action_requests (requester_user_id);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_requests_requester_business_role ON public.high_risk_action_requests (requester_business_role);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_requests_decided_by_user_id ON public.high_risk_action_requests (decided_by_user_id);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_requests_requested_at ON public.high_risk_action_requests (requested_at DESC);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_requests_decided_at ON public.high_risk_action_requests (decided_at DESC);
CREATE INDEX IF NOT EXISTS ix_high_risk_actions_tenant_status_requested
  ON public.high_risk_action_requests (tenant_id, status, requested_at DESC);

CREATE INDEX IF NOT EXISTS ix_high_risk_action_events_tenant_id ON public.high_risk_action_events (tenant_id);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_events_request_id ON public.high_risk_action_events (request_id);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_events_event_type ON public.high_risk_action_events (event_type);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_events_actor_user_id ON public.high_risk_action_events (actor_user_id);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_events_actor_business_role ON public.high_risk_action_events (actor_business_role);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_events_occurred_at ON public.high_risk_action_events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_high_risk_action_events_request_time
  ON public.high_risk_action_events (request_id, occurred_at);

DO $staffdeck_business_resource_rls$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'business_resources',
    'business_resource_scopes',
    'high_risk_action_requests',
    'high_risk_action_events'
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
    EXECUTE format(
      'CREATE POLICY worker_all_tenants ON public.%I FOR ALL TO staffdeck_worker '
      'USING (true) WITH CHECK (true)',
      table_name
    );
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC', table_name);
    EXECUTE format(
      'GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO staffdeck_runtime, staffdeck_worker',
      table_name
    );
  END LOOP;
END
$staffdeck_business_resource_rls$;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES (
  '20260901_business_resource_approvals_v1', now(), 'postgresql', 4, 0
)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
