BEGIN;

DROP TRIGGER IF EXISTS memory_review_events_append_only ON public.memory_review_events;
DROP TABLE IF EXISTS public.memory_review_events;
DROP TABLE IF EXISTS public.memory_review_requests;
DROP FUNCTION IF EXISTS app.reject_memory_review_event_mutation();
DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260902_memory_reviews_v1';

COMMIT;
