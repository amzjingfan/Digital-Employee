BEGIN;

CREATE TABLE IF NOT EXISTS public.memory_review_requests (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  memory_id varchar NOT NULL,
  memory_owner_user_id varchar NOT NULL,
  agent_id varchar,
  idempotency_key varchar NOT NULL,
  memory_digest varchar NOT NULL,
  memory_snapshot_json json NOT NULL DEFAULT '{}'::json,
  status varchar NOT NULL DEFAULT 'pending',
  requester_user_id varchar NOT NULL,
  request_note varchar,
  decided_by_user_id varchar,
  decision_note varchar,
  requested_at timestamp without time zone NOT NULL,
  decided_at timestamp without time zone,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_memory_review_idempotency UNIQUE (tenant_id, idempotency_key),
  CONSTRAINT memory_review_requests_status_check
    CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled', 'invalidated'))
);

CREATE TABLE IF NOT EXISTS public.memory_review_events (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  review_request_id varchar NOT NULL,
  event_type varchar NOT NULL,
  actor_user_id varchar NOT NULL,
  actor_business_role varchar NOT NULL,
  detail_json json NOT NULL DEFAULT '{}'::json,
  occurred_at timestamp without time zone NOT NULL,
  CONSTRAINT memory_review_events_type_check
    CHECK (event_type IN ('submitted', 'approved', 'rejected', 'cancelled', 'invalidated')),
  CONSTRAINT memory_review_events_request_fk
    FOREIGN KEY (review_request_id) REFERENCES public.memory_review_requests(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_memory_review_requests_tenant_id
  ON public.memory_review_requests (tenant_id);
CREATE INDEX IF NOT EXISTS ix_memory_review_requests_memory_id
  ON public.memory_review_requests (memory_id);
CREATE INDEX IF NOT EXISTS ix_memory_review_requests_memory_owner_user_id
  ON public.memory_review_requests (memory_owner_user_id);
CREATE INDEX IF NOT EXISTS ix_memory_review_requests_agent_id
  ON public.memory_review_requests (agent_id);
CREATE INDEX IF NOT EXISTS ix_memory_review_requests_idempotency_key
  ON public.memory_review_requests (idempotency_key);
CREATE INDEX IF NOT EXISTS ix_memory_review_requests_memory_digest
  ON public.memory_review_requests (memory_digest);
CREATE INDEX IF NOT EXISTS ix_memory_review_requests_status
  ON public.memory_review_requests (status);
CREATE INDEX IF NOT EXISTS ix_memory_review_requests_requester_user_id
  ON public.memory_review_requests (requester_user_id);
CREATE INDEX IF NOT EXISTS ix_memory_review_requests_decided_by_user_id
  ON public.memory_review_requests (decided_by_user_id);
CREATE INDEX IF NOT EXISTS ix_memory_review_requests_requested_at
  ON public.memory_review_requests (requested_at DESC);
CREATE INDEX IF NOT EXISTS ix_memory_review_requests_decided_at
  ON public.memory_review_requests (decided_at DESC);
CREATE INDEX IF NOT EXISTS ix_memory_review_tenant_status_time
  ON public.memory_review_requests (tenant_id, status, requested_at DESC);
CREATE INDEX IF NOT EXISTS ix_memory_review_events_tenant_id
  ON public.memory_review_events (tenant_id);
CREATE INDEX IF NOT EXISTS ix_memory_review_events_review_request_id
  ON public.memory_review_events (review_request_id);
CREATE INDEX IF NOT EXISTS ix_memory_review_events_event_type
  ON public.memory_review_events (event_type);
CREATE INDEX IF NOT EXISTS ix_memory_review_events_actor_user_id
  ON public.memory_review_events (actor_user_id);
CREATE INDEX IF NOT EXISTS ix_memory_review_events_actor_business_role
  ON public.memory_review_events (actor_business_role);
CREATE INDEX IF NOT EXISTS ix_memory_review_events_occurred_at
  ON public.memory_review_events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_memory_review_events_request_time
  ON public.memory_review_events (review_request_id, occurred_at);

CREATE OR REPLACE FUNCTION app.reject_memory_review_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'memory_review_events is append-only';
END;
$$;

DROP TRIGGER IF EXISTS memory_review_events_append_only ON public.memory_review_events;
CREATE TRIGGER memory_review_events_append_only
BEFORE UPDATE OR DELETE ON public.memory_review_events
FOR EACH ROW EXECUTE FUNCTION app.reject_memory_review_event_mutation();

ALTER TABLE public.memory_review_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_review_requests FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.memory_review_requests;
CREATE POLICY runtime_tenant_isolation ON public.memory_review_requests
FOR ALL TO staffdeck_runtime
USING (tenant_id = app.current_staffdeck_tenant_id())
WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
DROP POLICY IF EXISTS worker_all_tenants ON public.memory_review_requests;
CREATE POLICY worker_all_tenants ON public.memory_review_requests
FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

ALTER TABLE public.memory_review_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_review_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.memory_review_events;
CREATE POLICY runtime_tenant_isolation ON public.memory_review_events
FOR ALL TO staffdeck_runtime
USING (tenant_id = app.current_staffdeck_tenant_id())
WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
DROP POLICY IF EXISTS worker_all_tenants ON public.memory_review_events;
CREATE POLICY worker_all_tenants ON public.memory_review_events
FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

REVOKE ALL ON public.memory_review_requests FROM PUBLIC;
REVOKE ALL ON public.memory_review_events FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON public.memory_review_requests TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.memory_review_events TO staffdeck_runtime;
GRANT SELECT, INSERT, UPDATE ON public.memory_review_requests TO staffdeck_worker;
GRANT SELECT, INSERT ON public.memory_review_events TO staffdeck_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.memory_review_requests TO staffdeck_migrator;
GRANT SELECT, INSERT ON public.memory_review_events TO staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260902_memory_reviews_v1', now(), 'postgresql', 2, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
