BEGIN;

DROP TABLE IF EXISTS public.automation_usage_ledger;
DROP TABLE IF EXISTS public.execution_automation_policies;
DROP TABLE IF EXISTS public.advertising_effect_follow_ups;
DROP TABLE IF EXISTS public.advertising_recommendations;
DROP FUNCTION IF EXISTS app.protect_advertising_recommendation_evidence();
DROP FUNCTION IF EXISTS app.reject_advertising_ledger_mutation();

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260902_advertising_governance_v1';

COMMIT;
