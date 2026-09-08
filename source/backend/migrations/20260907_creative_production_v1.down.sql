BEGIN;

DROP TABLE IF EXISTS public.creative_generation_requests;
DROP TABLE IF EXISTS public.creative_delivery_checklists;
DROP TABLE IF EXISTS public.creative_evidence_records;

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260907_creative_production_v1';

COMMIT;
