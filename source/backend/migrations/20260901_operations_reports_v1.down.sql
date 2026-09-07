BEGIN;

DROP TRIGGER IF EXISTS operations_report_comments_append_only ON public.operations_report_comments;
DROP TRIGGER IF EXISTS operations_report_sources_append_only ON public.operations_report_sources;
DROP TABLE IF EXISTS public.operations_report_comments;
DROP TABLE IF EXISTS public.operations_report_sources;
DROP TABLE IF EXISTS public.operations_reports;
DROP FUNCTION IF EXISTS app.reject_operations_report_evidence_mutation();
DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260901_operations_reports_v1';

COMMIT;

