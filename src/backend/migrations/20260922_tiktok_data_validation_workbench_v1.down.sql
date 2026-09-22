BEGIN;

DROP TRIGGER IF EXISTS tiktok_data_validation_runs_append_only
  ON public.tiktok_data_validation_runs;
DROP TABLE IF EXISTS public.tiktok_data_validation_runs;
DROP TABLE IF EXISTS public.tiktok_capability_evidence;
DROP TABLE IF EXISTS public.tiktok_field_contracts;
DROP TABLE IF EXISTS public.tiktok_data_validation_scopes;
DROP FUNCTION IF EXISTS public.reject_tiktok_data_validation_run_mutation();
DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260922_tiktok_data_validation_workbench_v1';

COMMIT;
