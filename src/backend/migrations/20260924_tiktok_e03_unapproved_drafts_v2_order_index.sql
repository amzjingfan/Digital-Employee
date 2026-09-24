BEGIN;

-- Block concurrent parent inserts while historical references are copied and the trigger is installed.
SET LOCAL lock_timeout = '5s';
LOCK TABLE public.tiktok_commission_drafts IN SHARE ROW EXCLUSIVE MODE;

CREATE TABLE public.tiktok_commission_draft_order_refs (
  tenant_id varchar NOT NULL,
  draft_id varchar NOT NULL,
  order_ref varchar NOT NULL,
  PRIMARY KEY (tenant_id, draft_id, order_ref),
  CONSTRAINT fk_tiktok_commission_draft_order_ref_draft
    FOREIGN KEY (tenant_id, draft_id)
    REFERENCES public.tiktok_commission_drafts(tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT tiktok_commission_draft_order_ref_format
    CHECK (order_ref ~ '^order:[0-9a-f]{32}$')
);
CREATE INDEX ix_tiktok_commission_draft_order_ref_lookup
  ON public.tiktok_commission_draft_order_refs (tenant_id, order_ref, draft_id);

ALTER TABLE public.tiktok_commission_draft_order_refs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_commission_draft_order_refs FORCE ROW LEVEL SECURITY;
CREATE POLICY runtime_tenant_isolation ON public.tiktok_commission_draft_order_refs
  FOR SELECT TO staffdeck_runtime
  USING (tenant_id = app.current_staffdeck_tenant_id());
CREATE POLICY trigger_tenant_insert ON public.tiktok_commission_draft_order_refs
  FOR INSERT TO staffdeck_migrator
  WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
REVOKE ALL ON public.tiktok_commission_draft_order_refs FROM PUBLIC;
GRANT SELECT ON public.tiktok_commission_draft_order_refs TO staffdeck_runtime;

-- These policies exist only inside this transaction and are dropped before commit.
CREATE POLICY migration_draft_order_ref_read ON public.tiktok_commission_drafts
  FOR SELECT TO staffdeck_migrator USING (true);
CREATE POLICY migration_draft_order_ref_insert ON public.tiktok_commission_draft_order_refs
  FOR INSERT TO staffdeck_migrator WITH CHECK (true);
INSERT INTO public.tiktok_commission_draft_order_refs (tenant_id, draft_id, order_ref)
SELECT draft.tenant_id, draft.id, refs.value
FROM public.tiktok_commission_drafts AS draft
CROSS JOIN LATERAL pg_catalog.jsonb_array_elements_text(
  draft.order_refs_json::jsonb
) AS refs(value);
DROP POLICY migration_draft_order_ref_read ON public.tiktok_commission_drafts;
DROP POLICY migration_draft_order_ref_insert ON public.tiktok_commission_draft_order_refs;

CREATE FUNCTION public.index_tiktok_commission_draft_order_refs()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  INSERT INTO public.tiktok_commission_draft_order_refs (tenant_id, draft_id, order_ref)
  SELECT NEW.tenant_id, NEW.id, refs.value
  FROM pg_catalog.jsonb_array_elements_text(NEW.order_refs_json::jsonb) AS refs(value);
  RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION public.index_tiktok_commission_draft_order_refs() FROM PUBLIC;
CREATE TRIGGER tiktok_commission_drafts_index_order_refs
AFTER INSERT ON public.tiktok_commission_drafts
FOR EACH ROW EXECUTE FUNCTION public.index_tiktok_commission_draft_order_refs();
CREATE TRIGGER tiktok_commission_draft_order_refs_append_only
BEFORE UPDATE OR DELETE ON public.tiktok_commission_draft_order_refs
FOR EACH ROW EXECUTE FUNCTION public.reject_tiktok_commission_draft_mutation();

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260924_tiktok_e03_unapproved_drafts_v2_order_index', now(), 'postgresql', 1, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
