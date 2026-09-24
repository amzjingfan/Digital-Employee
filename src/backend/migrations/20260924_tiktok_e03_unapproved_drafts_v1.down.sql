BEGIN;

DROP TABLE public.tiktok_commission_drafts;
DROP FUNCTION public.reject_tiktok_commission_draft_mutation();
DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260924_tiktok_e03_unapproved_drafts_v1';

COMMIT;
