DROP INDEX IF EXISTS public.ix_creative_briefs_snapshot_digest;
ALTER TABLE public.creative_briefs DROP COLUMN IF EXISTS snapshot_digest;
ALTER TABLE public.creative_briefs DROP COLUMN IF EXISTS platform_spec_snapshot_json;
ALTER TABLE public.creative_briefs DROP COLUMN IF EXISTS brand_snapshot_json;
ALTER TABLE public.creative_briefs DROP COLUMN IF EXISTS fact_snapshot_json;
