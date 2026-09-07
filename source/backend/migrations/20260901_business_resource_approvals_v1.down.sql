BEGIN;

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260901_business_resource_approvals_v1';

DROP TABLE IF EXISTS public.high_risk_action_events;
DROP TABLE IF EXISTS public.high_risk_action_requests;
DROP TABLE IF EXISTS public.business_resource_scopes;
DROP TABLE IF EXISTS public.business_resources;

COMMIT;
