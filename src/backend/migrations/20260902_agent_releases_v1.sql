BEGIN;

ALTER TABLE public.agent_profiles
  ADD COLUMN IF NOT EXISTS release_state varchar NOT NULL DEFAULT 'draft',
  ADD COLUMN IF NOT EXISTS published_release_id varchar,
  ADD COLUMN IF NOT EXISTS published_release_version integer NOT NULL DEFAULT 0;

ALTER TABLE public.agent_profiles
  DROP CONSTRAINT IF EXISTS agent_profiles_release_state_check;
ALTER TABLE public.agent_profiles
  ADD CONSTRAINT agent_profiles_release_state_check
    CHECK (release_state IN ('draft', 'published'));
ALTER TABLE public.agent_profiles
  DROP CONSTRAINT IF EXISTS agent_profiles_release_version_check;
ALTER TABLE public.agent_profiles
  ADD CONSTRAINT agent_profiles_release_version_check
    CHECK (published_release_version >= 0);

CREATE INDEX IF NOT EXISTS ix_agent_profiles_release_state
  ON public.agent_profiles (release_state);
CREATE INDEX IF NOT EXISTS ix_agent_profiles_published_release_id
  ON public.agent_profiles (published_release_id);
CREATE INDEX IF NOT EXISTS ix_agent_profiles_published_release_version
  ON public.agent_profiles (published_release_version);

CREATE TABLE IF NOT EXISTS public.agent_releases (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  agent_id varchar NOT NULL,
  version integer NOT NULL,
  status varchar NOT NULL DEFAULT 'published',
  snapshot_json json NOT NULL DEFAULT '{}'::json,
  snapshot_digest varchar NOT NULL,
  source_release_id varchar,
  created_by_user_id varchar NOT NULL,
  release_reason varchar NOT NULL,
  created_at timestamp without time zone NOT NULL,
  published_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_agent_release_version UNIQUE (tenant_id, agent_id, version),
  CONSTRAINT agent_releases_status_check
    CHECK (status IN ('published', 'superseded')),
  CONSTRAINT agent_releases_version_check CHECK (version > 0)
);

CREATE INDEX IF NOT EXISTS ix_agent_releases_tenant_id
  ON public.agent_releases (tenant_id);
CREATE INDEX IF NOT EXISTS ix_agent_releases_agent_id
  ON public.agent_releases (agent_id);
CREATE INDEX IF NOT EXISTS ix_agent_releases_version
  ON public.agent_releases (version);
CREATE INDEX IF NOT EXISTS ix_agent_releases_status
  ON public.agent_releases (status);
CREATE INDEX IF NOT EXISTS ix_agent_releases_snapshot_digest
  ON public.agent_releases (snapshot_digest);
CREATE INDEX IF NOT EXISTS ix_agent_releases_source_release_id
  ON public.agent_releases (source_release_id);
CREATE INDEX IF NOT EXISTS ix_agent_releases_created_by_user_id
  ON public.agent_releases (created_by_user_id);
CREATE INDEX IF NOT EXISTS ix_agent_releases_created_at
  ON public.agent_releases (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_agent_releases_published_at
  ON public.agent_releases (published_at DESC);
CREATE INDEX IF NOT EXISTS ix_agent_releases_tenant_agent_status
  ON public.agent_releases (tenant_id, agent_id, status, version DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_release_single_published
  ON public.agent_releases (tenant_id, agent_id)
  WHERE status = 'published';

CREATE TABLE IF NOT EXISTS public.agent_release_events (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  agent_id varchar NOT NULL,
  release_id varchar,
  event_type varchar NOT NULL,
  actor_user_id varchar NOT NULL,
  detail_json json NOT NULL DEFAULT '{}'::json,
  occurred_at timestamp without time zone NOT NULL,
  CONSTRAINT agent_release_events_type_check
    CHECK (event_type IN ('published', 'rolled_back', 'draft_changed', 'deactivated'))
);

CREATE INDEX IF NOT EXISTS ix_agent_release_events_tenant_id
  ON public.agent_release_events (tenant_id);
CREATE INDEX IF NOT EXISTS ix_agent_release_events_agent_id
  ON public.agent_release_events (agent_id);
CREATE INDEX IF NOT EXISTS ix_agent_release_events_release_id
  ON public.agent_release_events (release_id);
CREATE INDEX IF NOT EXISTS ix_agent_release_events_event_type
  ON public.agent_release_events (event_type);
CREATE INDEX IF NOT EXISTS ix_agent_release_events_actor_user_id
  ON public.agent_release_events (actor_user_id);
CREATE INDEX IF NOT EXISTS ix_agent_release_events_occurred_at
  ON public.agent_release_events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_agent_release_events_tenant_agent_time
  ON public.agent_release_events (tenant_id, agent_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION app.protect_agent_release()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'agent releases cannot be deleted';
  END IF;
  IF NEW.id IS DISTINCT FROM OLD.id OR
     NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR
     NEW.agent_id IS DISTINCT FROM OLD.agent_id OR
     NEW.version IS DISTINCT FROM OLD.version OR
     NEW.snapshot_json IS DISTINCT FROM OLD.snapshot_json OR
     NEW.snapshot_digest IS DISTINCT FROM OLD.snapshot_digest OR
     NEW.source_release_id IS DISTINCT FROM OLD.source_release_id OR
     NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id OR
     NEW.release_reason IS DISTINCT FROM OLD.release_reason OR
     NEW.created_at IS DISTINCT FROM OLD.created_at OR
     NEW.published_at IS DISTINCT FROM OLD.published_at THEN
    RAISE EXCEPTION 'agent release content is immutable';
  END IF;
  IF OLD.status = 'superseded' OR NEW.status NOT IN ('published', 'superseded') THEN
    RAISE EXCEPTION 'invalid agent release status transition';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS agent_release_guard ON public.agent_releases;
CREATE TRIGGER agent_release_guard
BEFORE UPDATE OR DELETE ON public.agent_releases
FOR EACH ROW EXECUTE FUNCTION app.protect_agent_release();

CREATE OR REPLACE FUNCTION app.reject_agent_release_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'agent_release_events is append-only';
END;
$$;

DROP TRIGGER IF EXISTS agent_release_events_append_only ON public.agent_release_events;
CREATE TRIGGER agent_release_events_append_only
BEFORE UPDATE OR DELETE ON public.agent_release_events
FOR EACH ROW EXECUTE FUNCTION app.reject_agent_release_event_mutation();

ALTER TABLE public.agent_releases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_releases FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.agent_releases;
CREATE POLICY runtime_tenant_isolation ON public.agent_releases
FOR ALL TO staffdeck_runtime
USING (tenant_id = app.current_staffdeck_tenant_id())
WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
DROP POLICY IF EXISTS worker_all_tenants ON public.agent_releases;
CREATE POLICY worker_all_tenants ON public.agent_releases
FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

ALTER TABLE public.agent_release_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_release_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.agent_release_events;
CREATE POLICY runtime_tenant_isolation ON public.agent_release_events
FOR ALL TO staffdeck_runtime
USING (tenant_id = app.current_staffdeck_tenant_id())
WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
DROP POLICY IF EXISTS worker_all_tenants ON public.agent_release_events;
CREATE POLICY worker_all_tenants ON public.agent_release_events
FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

REVOKE ALL ON public.agent_releases FROM PUBLIC;
REVOKE ALL ON public.agent_release_events FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON public.agent_releases TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.agent_release_events TO staffdeck_runtime;
GRANT SELECT, INSERT, UPDATE ON public.agent_releases TO staffdeck_worker;
GRANT SELECT, INSERT ON public.agent_release_events TO staffdeck_worker;
GRANT SELECT, INSERT, UPDATE ON public.agent_releases TO staffdeck_migrator;
GRANT SELECT, INSERT ON public.agent_release_events TO staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260902_agent_releases_v1', now(), 'postgresql', 2, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
