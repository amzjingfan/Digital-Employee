BEGIN;

DROP TRIGGER IF EXISTS integration_health_events_append_only ON public.integration_health_events;
DROP TRIGGER IF EXISTS logistics_anomaly_events_append_only ON public.logistics_anomaly_events;
DROP TRIGGER IF EXISTS after_sales_case_events_append_only ON public.after_sales_case_events;

DROP TABLE IF EXISTS public.integration_health_events;
DROP TABLE IF EXISTS public.integration_health_states;
DROP TABLE IF EXISTS public.logistics_anomaly_events;
DROP TABLE IF EXISTS public.logistics_anomalies;
DROP TABLE IF EXISTS public.after_sales_case_events;
DROP TABLE IF EXISTS public.after_sales_cases;

DROP FUNCTION IF EXISTS app.reject_crossborder_trace_mutation();

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260902_crossborder_casework_v1';

COMMIT;
