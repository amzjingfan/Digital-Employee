BEGIN;

DROP TRIGGER IF EXISTS agent_release_events_append_only ON public.agent_release_events;
DROP TRIGGER IF EXISTS agent_release_guard ON public.agent_releases;
DROP FUNCTION IF EXISTS app.reject_agent_release_event_mutation();
DROP FUNCTION IF EXISTS app.protect_agent_release();
DROP TABLE IF EXISTS public.agent_release_events;
DROP TABLE IF EXISTS public.agent_releases;

ALTER TABLE public.agent_profiles
  DROP CONSTRAINT IF EXISTS agent_profiles_release_version_check,
  DROP CONSTRAINT IF EXISTS agent_profiles_release_state_check,
  DROP COLUMN IF EXISTS published_release_version,
  DROP COLUMN IF EXISTS published_release_id,
  DROP COLUMN IF EXISTS release_state;

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260902_agent_releases_v1';

COMMIT;
