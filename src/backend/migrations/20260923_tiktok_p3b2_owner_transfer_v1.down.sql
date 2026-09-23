BEGIN;

-- PostgreSQL rejects this rollback while transferred or released events are retained.
ALTER TABLE public.tiktok_creator_pool_events
  DROP CONSTRAINT tiktok_creator_pool_events_event_type_check;
ALTER TABLE public.tiktok_creator_pool_events
  ADD CONSTRAINT tiktok_creator_pool_events_event_type_check CHECK (
    event_type IN (
      'entered', 'claimed', 'follow_up', 'reflow_proposed', 'reflow_approved'
    )
  );

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260923_tiktok_p3b2_owner_transfer_v1';

COMMIT;
