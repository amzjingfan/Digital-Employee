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

ALTER TABLE public.tiktok_creator_pool_events
  DROP COLUMN previous_fulfillment_user_id,
  DROP COLUMN new_fulfillment_user_id,
  DROP COLUMN previous_maintenance_user_id,
  DROP COLUMN new_maintenance_user_id;

ALTER TABLE public.tiktok_creator_pool
  DROP COLUMN fulfillment_user_id,
  DROP COLUMN maintenance_user_id;

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260924_tiktok_p3b2_responsibilities_v1';

COMMIT;
