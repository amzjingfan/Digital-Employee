BEGIN;

DROP TRIGGER IF EXISTS tenant_lifecycle_events_append_only
  ON public.tenant_lifecycle_events;
DROP FUNCTION IF EXISTS app.reject_tenant_lifecycle_event_mutation();
DROP TABLE IF EXISTS public.tenant_lifecycle_events;
DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260902_tenant_provisioning_v1';

COMMIT;
