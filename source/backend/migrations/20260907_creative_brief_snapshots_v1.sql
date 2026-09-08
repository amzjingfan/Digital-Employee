BEGIN;

-- Versioned product evidence captured at Brief creation time.
ALTER TABLE public.creative_briefs
    ADD COLUMN IF NOT EXISTS fact_snapshot_json JSON NOT NULL DEFAULT '{}'::json;
ALTER TABLE public.creative_briefs
    ADD COLUMN IF NOT EXISTS brand_snapshot_json JSON NOT NULL DEFAULT '{}'::json;
ALTER TABLE public.creative_briefs
    ADD COLUMN IF NOT EXISTS platform_spec_snapshot_json JSON NOT NULL DEFAULT '{}'::json;
ALTER TABLE public.creative_briefs
    ADD COLUMN IF NOT EXISTS snapshot_digest VARCHAR NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS ix_creative_briefs_snapshot_digest
    ON public.creative_briefs (tenant_id, snapshot_digest);

INSERT INTO public.staffdeck_schema_migrations (
    migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260907_creative_brief_snapshots_v1', now(), 'postgresql', 1, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
