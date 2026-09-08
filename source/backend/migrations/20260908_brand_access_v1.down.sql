BEGIN;

DROP TRIGGER IF EXISTS brand_access_events_append_only ON public.brand_access_events;
DROP TRIGGER IF EXISTS store_accesses_validate_resource ON public.store_accesses;
DROP FUNCTION IF EXISTS app.reject_brand_access_event_mutation();
DROP FUNCTION IF EXISTS app.validate_store_access_resource();

DROP TABLE IF EXISTS public.brand_access_events;
DROP TABLE IF EXISTS public.store_accesses;
DROP TABLE IF EXISTS public.brand_memberships;
DROP TABLE IF EXISTS public.brands;

DROP INDEX IF EXISTS public.uq_business_resources_tenant_id_id;
DROP INDEX IF EXISTS public.uq_users_tenant_id_id;

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260908_brand_access_v1';

COMMIT;
