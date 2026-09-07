BEGIN;

DROP TABLE IF EXISTS public.organization_memberships;
DROP TABLE IF EXISTS public.organization_units;
ALTER TABLE public.business_resources
  DROP CONSTRAINT IF EXISTS business_resources_type_check;
ALTER TABLE public.business_resources
  ADD CONSTRAINT business_resources_type_check CHECK (
    resource_type IN ('store', 'carrier', 'ad_account', 'supplier')
  );
DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260903_tiktok_business_unit_v1';

COMMIT;
