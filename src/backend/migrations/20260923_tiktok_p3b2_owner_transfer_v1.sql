BEGIN;

ALTER TABLE public.tiktok_creator_pool_events
  DROP CONSTRAINT tiktok_creator_pool_events_event_type_check;
ALTER TABLE public.tiktok_creator_pool_events
  ADD CONSTRAINT tiktok_creator_pool_events_event_type_check CHECK (
    event_type IN (
      'entered', 'claimed', 'follow_up', 'reflow_proposed', 'reflow_approved',
      'transferred', 'released'
    )
  );

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260923_tiktok_p3b2_owner_transfer_v1', now(), 'postgresql', 1, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
