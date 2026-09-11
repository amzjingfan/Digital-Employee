BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_tenant_id_id
  ON public.users (tenant_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_business_resources_tenant_id_id
  ON public.business_resources (tenant_id, id);

CREATE TABLE IF NOT EXISTS public.brands (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  code varchar NOT NULL,
  name varchar NOT NULL,
  timezone varchar NOT NULL DEFAULT 'UTC',
  status varchar NOT NULL DEFAULT 'active',
  revision integer NOT NULL DEFAULT 1,
  created_by_user_id varchar NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_brands_tenant_code UNIQUE (tenant_id, code),
  CONSTRAINT uq_brands_tenant_id_id UNIQUE (tenant_id, id),
  CONSTRAINT brands_status_check CHECK (status IN ('active', 'inactive', 'archived'))
);

CREATE TABLE IF NOT EXISTS public.brand_memberships (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  brand_id varchar NOT NULL,
  user_id varchar NOT NULL,
  access_level varchar NOT NULL DEFAULT 'viewer',
  status varchar NOT NULL DEFAULT 'active',
  created_by_user_id varchar NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_brand_memberships_tenant_brand_user
    UNIQUE (tenant_id, brand_id, user_id),
  CONSTRAINT fk_brand_memberships_tenant_brand
    FOREIGN KEY (tenant_id, brand_id)
    REFERENCES public.brands (tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_brand_memberships_tenant_user
    FOREIGN KEY (tenant_id, user_id)
    REFERENCES public.users (tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT brand_memberships_access_check CHECK (access_level IN ('viewer', 'operator')),
  CONSTRAINT brand_memberships_status_check CHECK (status IN ('active', 'inactive'))
);

CREATE TABLE IF NOT EXISTS public.store_accesses (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  brand_id varchar NOT NULL,
  resource_id varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'active',
  created_by_user_id varchar NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_store_accesses_tenant_resource UNIQUE (tenant_id, resource_id),
  CONSTRAINT fk_store_accesses_tenant_brand
    FOREIGN KEY (tenant_id, brand_id)
    REFERENCES public.brands (tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_store_accesses_tenant_resource
    FOREIGN KEY (tenant_id, resource_id)
    REFERENCES public.business_resources (tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT store_accesses_status_check CHECK (status IN ('active', 'inactive'))
);

CREATE TABLE IF NOT EXISTS public.brand_access_events (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  brand_id varchar NOT NULL,
  event_type varchar NOT NULL,
  actor_user_id varchar NOT NULL,
  subject_user_id varchar,
  resource_id varchar,
  detail_json json NOT NULL DEFAULT '{}'::json,
  occurred_at timestamptz NOT NULL,
  CONSTRAINT fk_brand_access_events_tenant_brand
    FOREIGN KEY (tenant_id, brand_id)
    REFERENCES public.brands (tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT brand_access_events_type_check
    CHECK (event_type IN ('brand_created', 'membership_changed', 'store_access_changed'))
);

CREATE INDEX IF NOT EXISTS ix_brands_tenant_status_name
  ON public.brands (tenant_id, status, name);
CREATE INDEX IF NOT EXISTS ix_brand_memberships_tenant_user_status
  ON public.brand_memberships (tenant_id, user_id, status);
CREATE INDEX IF NOT EXISTS ix_store_accesses_tenant_brand_status
  ON public.store_accesses (tenant_id, brand_id, status);
CREATE INDEX IF NOT EXISTS ix_brand_access_events_tenant_brand_time
  ON public.brand_access_events (tenant_id, brand_id, occurred_at);

CREATE OR REPLACE FUNCTION app.validate_store_access_resource()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM public.business_resources AS resource
    WHERE resource.tenant_id = NEW.tenant_id
      AND resource.id = NEW.resource_id
      AND resource.resource_type = 'store'
  ) THEN
    RAISE EXCEPTION 'store_accesses.resource_id must reference a store in the same tenant';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS store_accesses_validate_resource ON public.store_accesses;
CREATE TRIGGER store_accesses_validate_resource
BEFORE INSERT OR UPDATE ON public.store_accesses
FOR EACH ROW EXECUTE FUNCTION app.validate_store_access_resource();

CREATE OR REPLACE FUNCTION app.reject_brand_access_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'brand_access_events is append-only';
END;
$$;

DROP TRIGGER IF EXISTS brand_access_events_append_only ON public.brand_access_events;
CREATE TRIGGER brand_access_events_append_only
BEFORE UPDATE OR DELETE ON public.brand_access_events
FOR EACH ROW EXECUTE FUNCTION app.reject_brand_access_event_mutation();

DO $brand_rls$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'brands',
    'brand_memberships',
    'store_accesses',
    'brand_access_events'
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
    EXECUTE format('DROP POLICY IF EXISTS worker_tenant_isolation ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY worker_tenant_isolation ON public.%I FOR ALL TO staffdeck_worker '
      'USING (tenant_id = app.current_staffdeck_tenant_id()) '
      'WITH CHECK (tenant_id = app.current_staffdeck_tenant_id())',
      table_name
    );
  END LOOP;
END
$brand_rls$;

REVOKE ALL ON public.brands FROM PUBLIC;
REVOKE ALL ON public.brand_memberships FROM PUBLIC;
REVOKE ALL ON public.store_accesses FROM PUBLIC;
REVOKE ALL ON public.brand_access_events FROM PUBLIC;

GRANT SELECT, INSERT, UPDATE ON public.brands
  TO staffdeck_runtime, staffdeck_worker;
GRANT SELECT, INSERT, UPDATE ON public.brand_memberships
  TO staffdeck_runtime, staffdeck_worker;
GRANT SELECT, INSERT, UPDATE ON public.store_accesses
  TO staffdeck_runtime, staffdeck_worker;
GRANT SELECT, INSERT ON public.brand_access_events
  TO staffdeck_runtime, staffdeck_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.brands, public.brand_memberships,
  public.store_accesses, public.brand_access_events TO staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260908_brand_access_v1', now(), 'postgresql', 4, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
