BEGIN;

CREATE TABLE public.tiktok_commission_drafts (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  pool_id varchar NOT NULL,
  pool_revision integer NOT NULL CHECK (pool_revision > 0),
  owner_user_id varchar NOT NULL,
  fulfillment_user_id varchar NOT NULL,
  maintenance_user_id varchar NOT NULL,
  rule_version varchar NOT NULL,
  rule_expires_at timestamptz NOT NULL,
  order_refs_json text NOT NULL,
  development_bps integer NOT NULL,
  fulfillment_bps integer NOT NULL,
  maintenance_bps integer NOT NULL,
  calculation_evidence_ref varchar NOT NULL,
  approval_state varchar NOT NULL DEFAULT 'unapproved',
  idempotency_key varchar NOT NULL,
  request_digest varchar NOT NULL,
  created_by_user_id varchar NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_tiktok_commission_draft_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_tiktok_commission_draft_idempotency UNIQUE (tenant_id, idempotency_key),
  CONSTRAINT fk_tiktok_commission_draft_pool FOREIGN KEY (tenant_id, pool_id)
    REFERENCES public.tiktok_creator_pool(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_commission_draft_actor FOREIGN KEY (tenant_id, created_by_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_commission_draft_owner FOREIGN KEY (tenant_id, owner_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_commission_draft_fulfillment FOREIGN KEY (tenant_id, fulfillment_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_tiktok_commission_draft_maintenance FOREIGN KEY (tenant_id, maintenance_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT tiktok_commission_draft_unapproved_check CHECK (approval_state = 'unapproved'),
  CONSTRAINT tiktok_commission_draft_split_check CHECK (
    development_bps BETWEEN 0 AND 10000 AND fulfillment_bps BETWEEN 0 AND 10000
    AND maintenance_bps BETWEEN 0 AND 10000
    AND development_bps + fulfillment_bps + maintenance_bps = 10000
  )
);
CREATE INDEX ix_tiktok_commission_draft_tenant_pool
  ON public.tiktok_commission_drafts (tenant_id, pool_id, created_at);

CREATE FUNCTION public.reject_tiktok_commission_draft_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'tiktok commission drafts are append-only';
END;
$$;
CREATE TRIGGER tiktok_commission_drafts_append_only
BEFORE UPDATE OR DELETE ON public.tiktok_commission_drafts
FOR EACH ROW EXECUTE FUNCTION public.reject_tiktok_commission_draft_mutation();

ALTER TABLE public.tiktok_commission_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_commission_drafts FORCE ROW LEVEL SECURITY;
CREATE POLICY runtime_tenant_isolation ON public.tiktok_commission_drafts
  FOR ALL TO staffdeck_runtime
  USING (tenant_id = app.current_staffdeck_tenant_id())
  WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
REVOKE ALL ON public.tiktok_commission_drafts FROM PUBLIC;
GRANT SELECT, INSERT ON public.tiktok_commission_drafts TO staffdeck_runtime;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260924_tiktok_e03_unapproved_drafts_v1', now(), 'postgresql', 1, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
