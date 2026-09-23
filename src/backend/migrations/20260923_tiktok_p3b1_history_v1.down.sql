BEGIN;

DROP TABLE IF EXISTS public.tiktok_history_signoffs;
DROP TABLE IF EXISTS public.tiktok_history_reconciliations;
DROP TABLE IF EXISTS public.tiktok_history_metric_definitions;
DROP TABLE IF EXISTS public.tiktok_history_facts;
DROP TABLE IF EXISTS public.tiktok_history_batches;
DROP FUNCTION IF EXISTS public.reject_tiktok_history_mutation();
DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260923_tiktok_p3b1_history_v1';

COMMIT;
