BEGIN;

DROP TRIGGER IF EXISTS bi_daily_metrics_version_guard ON public.bi_daily_metrics;
DROP TRIGGER IF EXISTS bi_daily_facts_version_guard ON public.bi_daily_commerce_facts;
DROP TRIGGER IF EXISTS bi_metric_definitions_append_only ON public.bi_metric_definitions;
DROP TRIGGER IF EXISTS bi_quality_checks_append_only ON public.bi_data_quality_checks;
DROP TABLE IF EXISTS public.bi_daily_metrics;
DROP TABLE IF EXISTS public.bi_metric_definitions;
DROP TABLE IF EXISTS public.bi_daily_commerce_facts;
DROP TABLE IF EXISTS public.bi_data_quality_checks;
DROP TABLE IF EXISTS public.bi_ingestion_batches;
DROP FUNCTION IF EXISTS app.protect_bi_versioned_row();
DROP FUNCTION IF EXISTS app.reject_bi_append_only_mutation();
DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260908_bi_metric_pipeline_v1';

COMMIT;
