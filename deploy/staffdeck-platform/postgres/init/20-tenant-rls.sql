\set ON_ERROR_STOP on
\connect staffdeck_app

CREATE EXTENSION IF NOT EXISTS vector;

SET ROLE staffdeck_migrator;

CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION staffdeck_migrator;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA app FROM PUBLIC;

CREATE OR REPLACE FUNCTION app.current_tenant_id()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
$$;

REVOKE ALL ON FUNCTION app.current_tenant_id() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.current_tenant_id() TO staffdeck_runtime, staffdeck_worker;

CREATE TABLE IF NOT EXISTS app.tenants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text NOT NULL,
  display_name text NOT NULL,
  default_locale text NOT NULL DEFAULT 'zh-CN',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT tenants_slug_unique UNIQUE (slug),
  CONSTRAINT tenants_locale_check CHECK (default_locale IN ('zh-CN', 'en'))
);

CREATE TABLE IF NOT EXISTS app.departments (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  code text NOT NULL,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id),
  CONSTRAINT departments_tenant_fk
    FOREIGN KEY (tenant_id) REFERENCES app.tenants(id) ON DELETE RESTRICT,
  CONSTRAINT departments_tenant_code_unique UNIQUE (tenant_id, code)
);

CREATE TABLE IF NOT EXISTS app.digital_employees (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  department_id uuid NOT NULL,
  employee_no text NOT NULL,
  role_code text NOT NULL,
  service_subject text NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id),
  CONSTRAINT digital_employees_department_fk
    FOREIGN KEY (tenant_id, department_id)
    REFERENCES app.departments(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT digital_employees_no_unique UNIQUE (tenant_id, employee_no),
  CONSTRAINT digital_employees_service_subject_unique UNIQUE (tenant_id, service_subject),
  CONSTRAINT digital_employees_status_check
    CHECK (status IN ('draft', 'active', 'suspended', 'retired'))
);

CREATE TABLE IF NOT EXISTS app.authorization_decisions (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  subject_id text NOT NULL,
  subject_type text NOT NULL,
  domain text NOT NULL,
  object text NOT NULL,
  action text NOT NULL,
  effect text NOT NULL,
  reason text,
  policy_version text NOT NULL,
  request_id text NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id),
  CONSTRAINT authorization_decisions_tenant_fk
    FOREIGN KEY (tenant_id) REFERENCES app.tenants(id) ON DELETE RESTRICT,
  CONSTRAINT authorization_decisions_effect_check CHECK (effect IN ('allow', 'deny')),
  CONSTRAINT authorization_decisions_subject_type_check
    CHECK (subject_type IN ('human', 'service'))
);

CREATE INDEX IF NOT EXISTS idx_authorization_decisions_tenant_occurred
  ON app.authorization_decisions (tenant_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_authorization_decisions_request
  ON app.authorization_decisions (tenant_id, request_id);

CREATE TABLE IF NOT EXISTS app.tenant_access_probes (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  payload text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id),
  CONSTRAINT tenant_access_probes_tenant_fk
    FOREIGN KEY (tenant_id) REFERENCES app.tenants(id) ON DELETE RESTRICT
);

INSERT INTO app.tenants (id, slug, display_name, default_locale)
VALUES
  ('11111111-1111-4111-8111-111111111111', 'tenant-demo-a', 'Demo Tenant A', 'zh-CN'),
  ('22222222-2222-4222-8222-222222222222', 'tenant-demo-b', 'Demo Tenant B', 'en')
ON CONFLICT (id) DO NOTHING;

INSERT INTO app.tenant_access_probes (tenant_id, payload)
SELECT '11111111-1111-4111-8111-111111111111', 'tenant-a-only'
WHERE NOT EXISTS (
  SELECT 1 FROM app.tenant_access_probes
  WHERE tenant_id = '11111111-1111-4111-8111-111111111111'
);

INSERT INTO app.tenant_access_probes (tenant_id, payload)
SELECT '22222222-2222-4222-8222-222222222222', 'tenant-b-only'
WHERE NOT EXISTS (
  SELECT 1 FROM app.tenant_access_probes
  WHERE tenant_id = '22222222-2222-4222-8222-222222222222'
);

ALTER TABLE app.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.tenants FORCE ROW LEVEL SECURITY;
ALTER TABLE app.departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.departments FORCE ROW LEVEL SECURITY;
ALTER TABLE app.digital_employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.digital_employees FORCE ROW LEVEL SECURITY;
ALTER TABLE app.authorization_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.authorization_decisions FORCE ROW LEVEL SECURITY;
ALTER TABLE app.tenant_access_probes ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.tenant_access_probes FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenants_isolation ON app.tenants;
CREATE POLICY tenants_isolation ON app.tenants
  FOR ALL
  USING (id = app.current_tenant_id())
  WITH CHECK (id = app.current_tenant_id());

DROP POLICY IF EXISTS departments_isolation ON app.departments;
CREATE POLICY departments_isolation ON app.departments
  FOR ALL
  USING (tenant_id = app.current_tenant_id())
  WITH CHECK (tenant_id = app.current_tenant_id());

DROP POLICY IF EXISTS digital_employees_isolation ON app.digital_employees;
CREATE POLICY digital_employees_isolation ON app.digital_employees
  FOR ALL
  USING (tenant_id = app.current_tenant_id())
  WITH CHECK (tenant_id = app.current_tenant_id());

DROP POLICY IF EXISTS authorization_decisions_isolation ON app.authorization_decisions;
CREATE POLICY authorization_decisions_isolation ON app.authorization_decisions
  FOR ALL
  USING (tenant_id = app.current_tenant_id())
  WITH CHECK (tenant_id = app.current_tenant_id());

DROP POLICY IF EXISTS tenant_access_probes_isolation ON app.tenant_access_probes;
CREATE POLICY tenant_access_probes_isolation ON app.tenant_access_probes
  FOR ALL
  USING (tenant_id = app.current_tenant_id())
  WITH CHECK (tenant_id = app.current_tenant_id());

GRANT USAGE ON SCHEMA app TO staffdeck_runtime, staffdeck_worker;
GRANT SELECT ON app.tenants TO staffdeck_runtime, staffdeck_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.departments TO staffdeck_runtime, staffdeck_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.digital_employees TO staffdeck_runtime, staffdeck_worker;
GRANT SELECT, INSERT ON app.authorization_decisions TO staffdeck_runtime, staffdeck_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.tenant_access_probes TO staffdeck_runtime, staffdeck_worker;

RESET ROLE;

