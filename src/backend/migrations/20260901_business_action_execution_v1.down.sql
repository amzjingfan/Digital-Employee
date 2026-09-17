BEGIN;

DROP TRIGGER IF EXISTS business_action_execution_events_append_only
  ON public.business_action_execution_events;
DROP TABLE IF EXISTS public.business_action_execution_events;
DROP TABLE IF EXISTS public.business_action_executions;
DROP FUNCTION IF EXISTS app.reject_business_execution_event_mutation();
DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260901_business_action_execution_v1';

COMMIT;
