BEGIN;

DROP TRIGGER IF EXISTS offsite_channel_events_append_only ON public.offsite_channel_events;
DROP TRIGGER IF EXISTS offsite_channel_evidence_append_only ON public.offsite_channel_evidence;

DROP TABLE IF EXISTS public.offsite_channel_events;
DROP TABLE IF EXISTS public.offsite_channel_evidence;
DROP TABLE IF EXISTS public.offsite_channel_assets;

DROP FUNCTION IF EXISTS app.reject_offsite_channel_trace_mutation();

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260908_offsite_channel_assets_v1';

COMMIT;
