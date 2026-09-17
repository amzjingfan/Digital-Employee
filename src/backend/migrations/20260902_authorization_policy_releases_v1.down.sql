BEGIN;

DROP TRIGGER IF EXISTS authorization_policy_events_append_only
  ON public.authorization_policy_events;
DROP TRIGGER IF EXISTS authorization_policy_release_guard
  ON public.authorization_policy_releases;
DROP FUNCTION IF EXISTS app.reject_authorization_policy_event_mutation();
DROP FUNCTION IF EXISTS app.protect_authorization_policy_release();
DROP TABLE IF EXISTS public.authorization_policy_events;
DROP TABLE IF EXISTS public.authorization_policy_releases;

ALTER TABLE public.authorization_decisions
  DROP COLUMN IF EXISTS resource_type,
  DROP COLUMN IF EXISTS store_id,
  DROP COLUMN IF EXISTS department_id;

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260902_authorization_policy_releases_v1';

COMMIT;
