BEGIN;

DROP TABLE IF EXISTS public.design_qc_reports;

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260907_design_qc_reports_v1';

COMMIT;
