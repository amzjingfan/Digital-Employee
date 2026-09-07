BEGIN;

DROP POLICY IF EXISTS runtime_tenant_isolation ON public.tiktok_shadow_runs;
DROP POLICY IF EXISTS worker_all_tenants ON public.tiktok_shadow_runs;
DROP TABLE IF EXISTS public.tiktok_shadow_runs;
DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260903_tiktok_shadow_runs_v1';

COMMIT;
