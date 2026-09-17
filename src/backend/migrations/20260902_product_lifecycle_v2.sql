BEGIN;

CREATE OR REPLACE FUNCTION app.protect_listing_rule_set()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION '% evidence cannot be deleted', TG_TABLE_NAME;
  END IF;
  IF OLD.status = 'published' THEN
    RAISE EXCEPTION 'published listing rule sets are immutable';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION app.protect_creative_asset_version()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION '% evidence cannot be deleted', TG_TABLE_NAME;
  END IF;
  IF (
    OLD.asset_key IS DISTINCT FROM NEW.asset_key OR
    OLD.version IS DISTINCT FROM NEW.version OR
    OLD.brief_id IS DISTINCT FROM NEW.brief_id OR
    OLD.parent_version_id IS DISTINCT FROM NEW.parent_version_id OR
    OLD.file_reference IS DISTINCT FROM NEW.file_reference OR
    OLD.file_digest IS DISTINCT FROM NEW.file_digest OR
    OLD.provenance_json::text IS DISTINCT FROM NEW.provenance_json::text OR
    OLD.generation_parameters_json::text IS DISTINCT FROM NEW.generation_parameters_json::text OR
    OLD.checks_json::text IS DISTINCT FROM NEW.checks_json::text
  ) THEN
    RAISE EXCEPTION 'creative asset evidence is immutable; create a new version';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION app.protect_procurement_recommendation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION '% evidence cannot be deleted', TG_TABLE_NAME;
  END IF;
  IF (
    OLD.input_snapshot_json::text IS DISTINCT FROM NEW.input_snapshot_json::text OR
    OLD.formula IS DISTINCT FROM NEW.formula OR
    OLD.recommended_quantity IS DISTINCT FROM NEW.recommended_quantity OR
    OLD.estimated_landed_cost IS DISTINCT FROM NEW.estimated_landed_cost OR
    OLD.risk_reasons_json::text IS DISTINCT FROM NEW.risk_reasons_json::text
  ) THEN
    RAISE EXCEPTION 'procurement calculation evidence is immutable';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS listing_rule_sets_immutable ON public.listing_rule_sets;
CREATE TRIGGER listing_rule_sets_immutable
BEFORE UPDATE OR DELETE ON public.listing_rule_sets
FOR EACH ROW EXECUTE FUNCTION app.protect_listing_rule_set();

DROP TRIGGER IF EXISTS creative_asset_versions_immutable
  ON public.creative_asset_versions;
CREATE TRIGGER creative_asset_versions_immutable
BEFORE UPDATE OR DELETE ON public.creative_asset_versions
FOR EACH ROW EXECUTE FUNCTION app.protect_creative_asset_version();

DROP TRIGGER IF EXISTS procurement_recommendations_immutable
  ON public.procurement_recommendations;
CREATE TRIGGER procurement_recommendations_immutable
BEFORE UPDATE OR DELETE ON public.procurement_recommendations
FOR EACH ROW EXECUTE FUNCTION app.protect_procurement_recommendation();

DROP FUNCTION IF EXISTS app.protect_product_lifecycle_immutable_evidence();

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260902_product_lifecycle_v2', now(), 'postgresql', 0, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
