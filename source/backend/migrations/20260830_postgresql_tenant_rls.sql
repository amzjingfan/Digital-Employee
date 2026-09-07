BEGIN;

CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION staffdeck_migrator;

CREATE OR REPLACE FUNCTION app.current_staffdeck_tenant_id()
RETURNS text
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')
$$;

REVOKE ALL ON FUNCTION app.current_staffdeck_tenant_id() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.current_staffdeck_tenant_id()
  TO staffdeck_runtime, staffdeck_worker;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO staffdeck_runtime, staffdeck_worker;

DO $staffdeck_rls$
DECLARE
  item record;
BEGIN
  FOR item IN
    SELECT DISTINCT table_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND column_name = 'tenant_id'
    ORDER BY table_name
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', item.table_name);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', item.table_name);
    EXECUTE format('DROP POLICY IF EXISTS runtime_tenant_isolation ON public.%I', item.table_name);
    EXECUTE format(
      'CREATE POLICY runtime_tenant_isolation ON public.%I FOR ALL TO staffdeck_runtime '
      'USING (tenant_id = app.current_staffdeck_tenant_id()) '
      'WITH CHECK (tenant_id = app.current_staffdeck_tenant_id())',
      item.table_name
    );
    EXECUTE format('DROP POLICY IF EXISTS worker_all_tenants ON public.%I', item.table_name);
    EXECUTE format(
      'CREATE POLICY worker_all_tenants ON public.%I FOR ALL TO staffdeck_worker '
      'USING (true) WITH CHECK (true)',
      item.table_name
    );
  END LOOP;
END
$staffdeck_rls$;

ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenants FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.tenants;
CREATE POLICY runtime_tenant_isolation ON public.tenants
  FOR SELECT TO staffdeck_runtime
  USING (id = app.current_staffdeck_tenant_id());
DROP POLICY IF EXISTS worker_all_tenants ON public.tenants;
CREATE POLICY worker_all_tenants ON public.tenants
  FOR ALL TO staffdeck_worker
  USING (true) WITH CHECK (true);

ALTER TABLE public.user_avatars ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_avatars FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.user_avatars;
CREATE POLICY runtime_tenant_isolation ON public.user_avatars
  FOR ALL TO staffdeck_runtime
  USING (
    EXISTS (
      SELECT 1 FROM public.users
      WHERE users.id = user_avatars.user_id
        AND users.tenant_id = app.current_staffdeck_tenant_id()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.users
      WHERE users.id = user_avatars.user_id
        AND users.tenant_id = app.current_staffdeck_tenant_id()
    )
  );
DROP POLICY IF EXISTS worker_all_tenants ON public.user_avatars;
CREATE POLICY worker_all_tenants ON public.user_avatars
  FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

ALTER TABLE public.team_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.team_members FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.team_members;
CREATE POLICY runtime_tenant_isolation ON public.team_members
  FOR ALL TO staffdeck_runtime
  USING (
    EXISTS (
      SELECT 1 FROM public.teams
      WHERE teams.id = team_members.team_id
        AND teams.tenant_id = app.current_staffdeck_tenant_id()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.teams
      WHERE teams.id = team_members.team_id
        AND teams.tenant_id = app.current_staffdeck_tenant_id()
    )
  );
DROP POLICY IF EXISTS worker_all_tenants ON public.team_members;
CREATE POLICY worker_all_tenants ON public.team_members
  FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

ALTER TABLE public.team_task_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.team_task_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.team_task_events;
CREATE POLICY runtime_tenant_isolation ON public.team_task_events
  FOR ALL TO staffdeck_runtime
  USING (
    EXISTS (
      SELECT 1 FROM public.team_tasks
      WHERE team_tasks.id = team_task_events.task_id
        AND team_tasks.tenant_id = app.current_staffdeck_tenant_id()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.team_tasks
      WHERE team_tasks.id = team_task_events.task_id
        AND team_tasks.tenant_id = app.current_staffdeck_tenant_id()
    )
  );
DROP POLICY IF EXISTS worker_all_tenants ON public.team_task_events;
CREATE POLICY worker_all_tenants ON public.team_task_events
  FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
  TO staffdeck_runtime, staffdeck_worker;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public
  TO staffdeck_runtime, staffdeck_worker;

REVOKE INSERT, UPDATE, DELETE ON public.tenants FROM staffdeck_runtime;
REVOKE ALL ON public.mock_orders FROM staffdeck_runtime, staffdeck_worker;
REVOKE ALL ON public.staffdeck_schema_migrations FROM staffdeck_runtime, staffdeck_worker;
GRANT SELECT, INSERT, DELETE ON public.oidc_login_states TO staffdeck_runtime;

ALTER DEFAULT PRIVILEGES FOR ROLE staffdeck_migrator IN SCHEMA public
  REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE staffdeck_migrator IN SCHEMA public
  REVOKE ALL ON SEQUENCES FROM PUBLIC;

COMMIT;
