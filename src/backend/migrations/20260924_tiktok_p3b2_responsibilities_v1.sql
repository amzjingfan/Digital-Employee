BEGIN;

ALTER TABLE public.tiktok_creator_pool
  ADD COLUMN fulfillment_user_id varchar,
  ADD COLUMN maintenance_user_id varchar,
  ADD CONSTRAINT fk_tiktok_creator_pool_fulfillment
    FOREIGN KEY (tenant_id, fulfillment_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_tiktok_creator_pool_maintenance
    FOREIGN KEY (tenant_id, maintenance_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  ADD CONSTRAINT tiktok_creator_pool_public_responsibilities_check
    CHECK (state <> 'public' OR
      (fulfillment_user_id IS NULL AND maintenance_user_id IS NULL));

ALTER TABLE public.tiktok_creator_pool_events
  ADD COLUMN previous_fulfillment_user_id varchar,
  ADD COLUMN new_fulfillment_user_id varchar,
  ADD COLUMN previous_maintenance_user_id varchar,
  ADD COLUMN new_maintenance_user_id varchar,
  ADD CONSTRAINT fk_tiktok_creator_pool_event_previous_fulfillment
    FOREIGN KEY (tenant_id, previous_fulfillment_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_tiktok_creator_pool_event_new_fulfillment
    FOREIGN KEY (tenant_id, new_fulfillment_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_tiktok_creator_pool_event_previous_maintenance
    FOREIGN KEY (tenant_id, previous_maintenance_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_tiktok_creator_pool_event_new_maintenance
    FOREIGN KEY (tenant_id, new_maintenance_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT;

ALTER TABLE public.tiktok_creator_pool_events
  DROP CONSTRAINT tiktok_creator_pool_events_event_type_check;
ALTER TABLE public.tiktok_creator_pool_events
  ADD CONSTRAINT tiktok_creator_pool_events_event_type_check CHECK (
    event_type IN (
      'entered', 'claimed', 'follow_up', 'reflow_proposed', 'reflow_approved',
      'transferred', 'released', 'responsibilities_changed'
    )
  );

GRANT UPDATE (fulfillment_user_id, maintenance_user_id)
  ON public.tiktok_creator_pool TO staffdeck_runtime;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260924_tiktok_p3b2_responsibilities_v1', now(), 'postgresql', 2, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
