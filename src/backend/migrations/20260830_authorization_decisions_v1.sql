BEGIN;

CREATE TABLE IF NOT EXISTS public.authorization_decisions (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  subject_id varchar NOT NULL,
  subject_type varchar NOT NULL DEFAULT 'human',
  role varchar NOT NULL,
  object varchar NOT NULL,
  action varchar NOT NULL,
  effect varchar NOT NULL,
  reason varchar NOT NULL,
  policy_version varchar NOT NULL,
  request_id varchar NOT NULL,
  occurred_at timestamp without time zone NOT NULL,
  CONSTRAINT authorization_decisions_effect_check CHECK (effect IN ('allow', 'deny')),
  CONSTRAINT authorization_decisions_subject_type_check CHECK (subject_type IN ('human', 'service'))
);

CREATE INDEX IF NOT EXISTS ix_authorization_decisions_tenant_id
  ON public.authorization_decisions (tenant_id);
CREATE INDEX IF NOT EXISTS ix_authorization_decisions_subject_id
  ON public.authorization_decisions (subject_id);
CREATE INDEX IF NOT EXISTS ix_authorization_decisions_effect
  ON public.authorization_decisions (effect);
CREATE INDEX IF NOT EXISTS ix_authorization_decisions_policy_version
  ON public.authorization_decisions (policy_version);
CREATE INDEX IF NOT EXISTS ix_authorization_decisions_request_id
  ON public.authorization_decisions (request_id);
CREATE INDEX IF NOT EXISTS ix_authorization_decisions_occurred_at
  ON public.authorization_decisions (occurred_at DESC);

ALTER TABLE public.authorization_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.authorization_decisions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS runtime_tenant_isolation ON public.authorization_decisions;
CREATE POLICY runtime_tenant_isolation ON public.authorization_decisions
  FOR ALL TO staffdeck_runtime
  USING (tenant_id = app.current_staffdeck_tenant_id())
  WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());

DROP POLICY IF EXISTS worker_all_tenants ON public.authorization_decisions;
CREATE POLICY worker_all_tenants ON public.authorization_decisions
  FOR ALL TO staffdeck_worker
  USING (true)
  WITH CHECK (true);

REVOKE ALL ON public.authorization_decisions FROM PUBLIC;
GRANT SELECT, INSERT ON public.authorization_decisions TO staffdeck_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.authorization_decisions TO staffdeck_worker;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES (
  '20260830_authorization_decisions_v1', now(), 'postgresql', 1, 0
)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
