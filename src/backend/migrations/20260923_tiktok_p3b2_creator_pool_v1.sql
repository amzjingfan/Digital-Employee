BEGIN;

CREATE TABLE IF NOT EXISTS public.tiktok_creator_pool (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  creator_id varchar NOT NULL,
  identity_id varchar NOT NULL,
  market varchar NOT NULL DEFAULT 'US' CHECK (market = 'US'),
  source_ref varchar NOT NULL,
  sla_rule_version varchar NOT NULL,
  follow_up_window_hours integer NOT NULL CHECK (follow_up_window_hours BETWEEN 1 AND 720),
  state varchar NOT NULL DEFAULT 'public'
    CHECK (state IN ('public', 'claimed', 'reflow_candidate')),
  owner_user_id varchar,
  follow_up_due_at timestamptz,
  revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
  created_by_user_id varchar NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_tiktok_creator_pool_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_tiktok_creator_pool_creator UNIQUE (tenant_id, creator_id),
  CONSTRAINT fk_tiktok_creator_pool_creator FOREIGN KEY (tenant_id, creator_id)
    REFERENCES public.social_creators(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_creator_pool_identity FOREIGN KEY (tenant_id, identity_id, creator_id)
    REFERENCES public.social_platform_identities(tenant_id, id, creator_id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_creator_pool_owner FOREIGN KEY (tenant_id, owner_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_creator_pool_creator_user FOREIGN KEY (tenant_id, created_by_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT tiktok_creator_pool_assignment_check CHECK (
    (state = 'public' AND owner_user_id IS NULL AND follow_up_due_at IS NULL) OR
    (state <> 'public' AND owner_user_id IS NOT NULL AND follow_up_due_at IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS ix_tiktok_creator_pool_tenant_state
  ON public.tiktok_creator_pool (tenant_id, state);

CREATE TABLE IF NOT EXISTS public.tiktok_creator_pool_events (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  pool_id varchar NOT NULL,
  event_type varchar NOT NULL CHECK (
    event_type IN ('entered', 'claimed', 'follow_up', 'reflow_proposed', 'reflow_approved')
  ),
  actor_user_id varchar NOT NULL,
  previous_owner_user_id varchar,
  new_owner_user_id varchar,
  evidence_ref varchar,
  reason varchar,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_tiktok_creator_pool_event_pool FOREIGN KEY (tenant_id, pool_id)
    REFERENCES public.tiktok_creator_pool(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_creator_pool_event_actor FOREIGN KEY (tenant_id, actor_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_creator_pool_event_previous_owner
    FOREIGN KEY (tenant_id, previous_owner_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_creator_pool_event_new_owner
    FOREIGN KEY (tenant_id, new_owner_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS ix_tiktok_creator_pool_event_tenant_pool
  ON public.tiktok_creator_pool_events (tenant_id, pool_id, created_at);

CREATE OR REPLACE FUNCTION public.reject_tiktok_creator_pool_event_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'tiktok creator pool events are append-only';
END;
$$;
CREATE TRIGGER tiktok_creator_pool_events_append_only
BEFORE UPDATE OR DELETE ON public.tiktok_creator_pool_events
FOR EACH ROW EXECUTE FUNCTION public.reject_tiktok_creator_pool_event_mutation();

ALTER TABLE public.tiktok_creator_pool ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_creator_pool FORCE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_creator_pool_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_creator_pool_events FORCE ROW LEVEL SECURITY;
CREATE POLICY runtime_tenant_isolation ON public.tiktok_creator_pool
  FOR ALL TO staffdeck_runtime
  USING (tenant_id = app.current_staffdeck_tenant_id())
  WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
CREATE POLICY runtime_tenant_isolation ON public.tiktok_creator_pool_events
  FOR ALL TO staffdeck_runtime
  USING (tenant_id = app.current_staffdeck_tenant_id())
  WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
REVOKE ALL ON public.tiktok_creator_pool FROM PUBLIC;
REVOKE ALL ON public.tiktok_creator_pool_events FROM PUBLIC;
GRANT SELECT, INSERT ON public.tiktok_creator_pool TO staffdeck_runtime;
GRANT UPDATE (state, owner_user_id, follow_up_due_at, revision, updated_at)
  ON public.tiktok_creator_pool TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.tiktok_creator_pool_events TO staffdeck_runtime;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260923_tiktok_p3b2_creator_pool_v1', now(), 'postgresql', 2, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
