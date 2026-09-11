BEGIN;

CREATE TABLE IF NOT EXISTS public.tenant_lifecycle_events (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  event_type varchar NOT NULL,
  actor_ref varchar NOT NULL,
  outcome varchar NOT NULL DEFAULT 'allowed',
  reason varchar NOT NULL DEFAULT '',
  detail_json json NOT NULL DEFAULT '{}'::json,
  occurred_at timestamp without time zone NOT NULL,
  CONSTRAINT tenant_lifecycle_outcome_check
    CHECK (outcome IN ('allowed', 'denied', 'degraded'))
);

CREATE INDEX IF NOT EXISTS ix_tenant_lifecycle_events_tenant_id
  ON public.tenant_lifecycle_events (tenant_id);
CREATE INDEX IF NOT EXISTS ix_tenant_lifecycle_events_event_type
  ON public.tenant_lifecycle_events (event_type);
CREATE INDEX IF NOT EXISTS ix_tenant_lifecycle_events_actor_ref
  ON public.tenant_lifecycle_events (actor_ref);
CREATE INDEX IF NOT EXISTS ix_tenant_lifecycle_events_outcome
  ON public.tenant_lifecycle_events (outcome);
CREATE INDEX IF NOT EXISTS ix_tenant_lifecycle_events_occurred_at
  ON public.tenant_lifecycle_events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_tenant_lifecycle_tenant_time
  ON public.tenant_lifecycle_events (tenant_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION app.reject_tenant_lifecycle_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'tenant_lifecycle_events is append-only';
END;
$$;

DROP TRIGGER IF EXISTS tenant_lifecycle_events_append_only
  ON public.tenant_lifecycle_events;
CREATE TRIGGER tenant_lifecycle_events_append_only
BEFORE UPDATE OR DELETE ON public.tenant_lifecycle_events
FOR EACH ROW EXECUTE FUNCTION app.reject_tenant_lifecycle_event_mutation();

ALTER TABLE public.tenant_lifecycle_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenant_lifecycle_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.tenant_lifecycle_events;
CREATE POLICY runtime_tenant_isolation ON public.tenant_lifecycle_events
FOR SELECT TO staffdeck_runtime
USING (tenant_id = app.current_staffdeck_tenant_id());
DROP POLICY IF EXISTS worker_all_tenants ON public.tenant_lifecycle_events;
CREATE POLICY worker_all_tenants ON public.tenant_lifecycle_events
FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

REVOKE ALL ON public.tenant_lifecycle_events FROM PUBLIC;
GRANT SELECT ON public.tenant_lifecycle_events TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.tenant_lifecycle_events TO staffdeck_worker;
GRANT SELECT, INSERT ON public.tenant_lifecycle_events TO staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260902_tenant_provisioning_v1', now(), 'postgresql', 1, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
