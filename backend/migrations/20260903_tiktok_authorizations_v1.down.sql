BEGIN;

DROP TABLE IF EXISTS public.connector_sync_states;
DROP TABLE IF EXISTS public.tiktok_oauth_states;
DROP TABLE IF EXISTS public.external_authorizations;
DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260903_tiktok_authorizations_v1';

COMMIT;
