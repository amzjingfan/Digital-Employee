BEGIN;

CREATE TABLE IF NOT EXISTS public.organization_units (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  parent_id varchar,
  unit_type varchar NOT NULL DEFAULT 'department',
  code varchar NOT NULL,
  name varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'active',
  revision integer NOT NULL DEFAULT 1,
  metadata_json json NOT NULL DEFAULT '{}'::json,
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_organization_unit_tenant_code UNIQUE (tenant_id, code),
  CONSTRAINT organization_units_type_check CHECK (unit_type IN ('business_unit', 'department')),
  CONSTRAINT organization_units_status_check CHECK (status IN ('active', 'inactive', 'archived'))
);

CREATE INDEX IF NOT EXISTS ix_organization_units_tenant_parent
  ON public.organization_units (tenant_id, parent_id);

CREATE TABLE IF NOT EXISTS public.organization_memberships (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  unit_id varchar NOT NULL REFERENCES public.organization_units(id) ON DELETE RESTRICT,
  user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  business_role varchar NOT NULL,
  membership_type varchar NOT NULL DEFAULT 'primary',
  source varchar NOT NULL DEFAULT 'casdoor',
  status varchar NOT NULL DEFAULT 'active',
  synced_at timestamp without time zone NOT NULL,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_organization_membership_user_type
    UNIQUE (tenant_id, user_id, membership_type),
  CONSTRAINT organization_memberships_type_check
    CHECK (membership_type IN ('primary', 'manager')),
  CONSTRAINT organization_memberships_status_check
    CHECK (status IN ('active', 'inactive'))
);

CREATE INDEX IF NOT EXISTS ix_organization_memberships_tenant_unit
  ON public.organization_memberships (tenant_id, unit_id);

ALTER TABLE public.business_resources
  DROP CONSTRAINT IF EXISTS business_resources_type_check;
ALTER TABLE public.business_resources
  ADD CONSTRAINT business_resources_type_check CHECK (
    resource_type IN (
      'store', 'carrier', 'ad_account', 'supplier',
      'creator_account', 'partner_account', 'social_account', 'live_room'
    )
  );

ALTER TABLE public.organization_units ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organization_units FORCE ROW LEVEL SECURITY;
ALTER TABLE public.organization_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organization_memberships FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.organization_units;
DROP POLICY IF EXISTS worker_all_tenants ON public.organization_units;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.organization_memberships;
DROP POLICY IF EXISTS worker_all_tenants ON public.organization_memberships;
CREATE POLICY runtime_tenant_isolation ON public.organization_units
  FOR ALL TO staffdeck_runtime
  USING (tenant_id = app.current_staffdeck_tenant_id())
  WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
CREATE POLICY worker_all_tenants ON public.organization_units
  FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);
CREATE POLICY runtime_tenant_isolation ON public.organization_memberships
  FOR ALL TO staffdeck_runtime
  USING (tenant_id = app.current_staffdeck_tenant_id())
  WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
CREATE POLICY worker_all_tenants ON public.organization_memberships
  FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.organization_units
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.organization_memberships
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260903_tiktok_business_unit_v1', now(), 'postgresql', 3, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
