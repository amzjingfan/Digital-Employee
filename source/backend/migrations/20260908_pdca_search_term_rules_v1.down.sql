BEGIN;

DROP TABLE IF EXISTS public.pdca_actions;
DROP TABLE IF EXISTS public.pdca_fact_search_terms;
DROP TABLE IF EXISTS public.pdca_search_term_runs;
DROP FUNCTION IF EXISTS app.reject_pdca_evidence_mutation();

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260908_pdca_search_term_rules_v1';

COMMIT;
