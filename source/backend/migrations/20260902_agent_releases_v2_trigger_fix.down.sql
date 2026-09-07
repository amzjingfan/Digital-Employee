BEGIN;

DROP TRIGGER IF EXISTS agent_release_guard ON public.agent_releases;
DROP FUNCTION IF EXISTS app.protect_agent_release();

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260902_agent_releases_v2_trigger_fix';

COMMIT;
