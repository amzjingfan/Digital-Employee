BEGIN;

ALTER TABLE public.product_launch_gates
  ADD COLUMN IF NOT EXISTS supplier_lead_time_confirmed boolean NOT NULL DEFAULT false;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260902_product_lifecycle_v3', now(), 'postgresql', 0, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
