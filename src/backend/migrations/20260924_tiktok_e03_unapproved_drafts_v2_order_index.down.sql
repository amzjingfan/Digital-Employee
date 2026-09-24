BEGIN;

DROP TRIGGER tiktok_commission_drafts_index_order_refs ON public.tiktok_commission_drafts;
DROP FUNCTION public.index_tiktok_commission_draft_order_refs();
DROP TABLE public.tiktok_commission_draft_order_refs;
DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260924_tiktok_e03_unapproved_drafts_v2_order_index';

COMMIT;
