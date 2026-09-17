BEGIN;

ALTER TABLE public.authorization_decisions
  ADD COLUMN IF NOT EXISTS department_id varchar NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS store_id varchar NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS resource_type varchar NOT NULL DEFAULT 'api';

CREATE INDEX IF NOT EXISTS ix_authorization_decisions_department_id
  ON public.authorization_decisions (department_id);
CREATE INDEX IF NOT EXISTS ix_authorization_decisions_store_id
  ON public.authorization_decisions (store_id);
CREATE INDEX IF NOT EXISTS ix_authorization_decisions_resource_type
  ON public.authorization_decisions (resource_type);

CREATE TABLE IF NOT EXISTS public.authorization_policy_releases (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  version integer NOT NULL,
  status varchar NOT NULL DEFAULT 'draft',
  policy_text varchar NOT NULL,
  policy_digest varchar NOT NULL,
  description varchar NOT NULL DEFAULT '',
  source_release_id varchar,
  created_by_user_id varchar NOT NULL,
  published_by_user_id varchar,
  publish_reason varchar NOT NULL DEFAULT '',
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  published_at timestamp without time zone,
  CONSTRAINT uq_authorization_policy_release_version UNIQUE (tenant_id, version),
  CONSTRAINT authorization_policy_releases_status_check
    CHECK (status IN ('draft', 'published', 'superseded')),
  CONSTRAINT authorization_policy_releases_version_check CHECK (version > 0)
);

CREATE INDEX IF NOT EXISTS ix_authorization_policy_releases_tenant_id
  ON public.authorization_policy_releases (tenant_id);
CREATE INDEX IF NOT EXISTS ix_authorization_policy_releases_version
  ON public.authorization_policy_releases (version);
CREATE INDEX IF NOT EXISTS ix_authorization_policy_releases_status
  ON public.authorization_policy_releases (status);
CREATE INDEX IF NOT EXISTS ix_authorization_policy_releases_policy_digest
  ON public.authorization_policy_releases (policy_digest);
CREATE INDEX IF NOT EXISTS ix_authorization_policy_releases_source_release_id
  ON public.authorization_policy_releases (source_release_id);
CREATE INDEX IF NOT EXISTS ix_authorization_policy_releases_created_by_user_id
  ON public.authorization_policy_releases (created_by_user_id);
CREATE INDEX IF NOT EXISTS ix_authorization_policy_releases_published_by_user_id
  ON public.authorization_policy_releases (published_by_user_id);
CREATE INDEX IF NOT EXISTS ix_authorization_policy_releases_created_at
  ON public.authorization_policy_releases (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_authorization_policy_releases_published_at
  ON public.authorization_policy_releases (published_at DESC);
CREATE INDEX IF NOT EXISTS ix_authorization_policy_releases_tenant_status
  ON public.authorization_policy_releases (tenant_id, status, version DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_authorization_policy_single_published
  ON public.authorization_policy_releases (tenant_id)
  WHERE status = 'published';

CREATE TABLE IF NOT EXISTS public.authorization_policy_events (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  release_id varchar NOT NULL,
  event_type varchar NOT NULL,
  actor_user_id varchar NOT NULL,
  detail_json json NOT NULL DEFAULT '{}'::json,
  occurred_at timestamp without time zone NOT NULL,
  CONSTRAINT authorization_policy_events_type_check
    CHECK (event_type IN ('draft_created', 'draft_updated', 'published', 'rolled_back'))
);

CREATE INDEX IF NOT EXISTS ix_authorization_policy_events_tenant_id
  ON public.authorization_policy_events (tenant_id);
CREATE INDEX IF NOT EXISTS ix_authorization_policy_events_release_id
  ON public.authorization_policy_events (release_id);
CREATE INDEX IF NOT EXISTS ix_authorization_policy_events_event_type
  ON public.authorization_policy_events (event_type);
CREATE INDEX IF NOT EXISTS ix_authorization_policy_events_actor_user_id
  ON public.authorization_policy_events (actor_user_id);
CREATE INDEX IF NOT EXISTS ix_authorization_policy_events_occurred_at
  ON public.authorization_policy_events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_authorization_policy_events_tenant_time
  ON public.authorization_policy_events (tenant_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION app.protect_authorization_policy_release()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'authorization policy releases cannot be deleted';
  END IF;
  IF OLD.status <> 'draft' AND (
    NEW.policy_text IS DISTINCT FROM OLD.policy_text OR
    NEW.policy_digest IS DISTINCT FROM OLD.policy_digest
  ) THEN
    RAISE EXCEPTION 'published authorization policy content is immutable';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS authorization_policy_release_guard
  ON public.authorization_policy_releases;
CREATE TRIGGER authorization_policy_release_guard
BEFORE UPDATE OR DELETE ON public.authorization_policy_releases
FOR EACH ROW EXECUTE FUNCTION app.protect_authorization_policy_release();

CREATE OR REPLACE FUNCTION app.reject_authorization_policy_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'authorization_policy_events is append-only';
END;
$$;

DROP TRIGGER IF EXISTS authorization_policy_events_append_only
  ON public.authorization_policy_events;
CREATE TRIGGER authorization_policy_events_append_only
BEFORE UPDATE OR DELETE ON public.authorization_policy_events
FOR EACH ROW EXECUTE FUNCTION app.reject_authorization_policy_event_mutation();

ALTER TABLE public.authorization_policy_releases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.authorization_policy_releases FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.authorization_policy_releases;
CREATE POLICY runtime_tenant_isolation ON public.authorization_policy_releases
FOR ALL TO staffdeck_runtime
USING (tenant_id = app.current_staffdeck_tenant_id())
WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
DROP POLICY IF EXISTS worker_all_tenants ON public.authorization_policy_releases;
CREATE POLICY worker_all_tenants ON public.authorization_policy_releases
FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

ALTER TABLE public.authorization_policy_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.authorization_policy_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.authorization_policy_events;
CREATE POLICY runtime_tenant_isolation ON public.authorization_policy_events
FOR ALL TO staffdeck_runtime
USING (tenant_id = app.current_staffdeck_tenant_id())
WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
DROP POLICY IF EXISTS worker_all_tenants ON public.authorization_policy_events;
CREATE POLICY worker_all_tenants ON public.authorization_policy_events
FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

REVOKE ALL ON public.authorization_policy_releases FROM PUBLIC;
REVOKE ALL ON public.authorization_policy_events FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON public.authorization_policy_releases TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.authorization_policy_events TO staffdeck_runtime;
GRANT SELECT, INSERT, UPDATE ON public.authorization_policy_releases TO staffdeck_worker;
GRANT SELECT, INSERT ON public.authorization_policy_events TO staffdeck_worker;
GRANT SELECT, INSERT, UPDATE ON public.authorization_policy_releases TO staffdeck_migrator;
GRANT SELECT, INSERT ON public.authorization_policy_events TO staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260902_authorization_policy_releases_v1', now(), 'postgresql', 2, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
