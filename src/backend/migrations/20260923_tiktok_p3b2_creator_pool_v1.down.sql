BEGIN;

DROP TABLE IF EXISTS public.tiktok_creator_pool_events;
DROP TABLE IF EXISTS public.tiktok_creator_pool;
DROP FUNCTION IF EXISTS public.reject_tiktok_creator_pool_event_mutation();
DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260923_tiktok_p3b2_creator_pool_v1';

COMMIT;
