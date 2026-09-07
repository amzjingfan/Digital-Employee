BEGIN;

DROP TABLE IF EXISTS public.commerce_governance_events;
DROP TABLE IF EXISTS public.product_quality_issues;
DROP TABLE IF EXISTS public.product_launch_gates;
DROP TABLE IF EXISTS public.procurement_recommendations;
DROP TABLE IF EXISTS public.creative_asset_versions;
DROP TABLE IF EXISTS public.creative_briefs;
DROP TABLE IF EXISTS public.listing_compliance_checks;
DROP TABLE IF EXISTS public.listing_rule_sets;
DROP FUNCTION IF EXISTS app.reject_commerce_event_mutation();
DROP FUNCTION IF EXISTS app.protect_listing_rule_set();
DROP FUNCTION IF EXISTS app.protect_creative_asset_version();
DROP FUNCTION IF EXISTS app.protect_procurement_recommendation();
DROP FUNCTION IF EXISTS app.protect_product_lifecycle_immutable_evidence();

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260902_product_lifecycle_v1';

COMMIT;
