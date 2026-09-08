BEGIN;

DROP TRIGGER IF EXISTS social_domain_events_append_only
  ON public.social_domain_events;
DROP TRIGGER IF EXISTS social_audience_snapshots_append_only
  ON public.social_audience_snapshots;
DROP TRIGGER IF EXISTS social_creator_evidence_append_only
  ON public.social_creator_evidence;
DROP TRIGGER IF EXISTS social_event_brand_tenant_scope
  ON public.social_domain_events;
DROP TRIGGER IF EXISTS social_audience_brand_tenant_scope
  ON public.social_audience_snapshots;

DROP TABLE IF EXISTS public.social_domain_events;
DROP TABLE IF EXISTS public.social_audience_snapshots;
DROP TABLE IF EXISTS public.social_creator_evidence;
DROP TABLE IF EXISTS public.social_platform_identities;
DROP TABLE IF EXISTS public.social_creators;

DROP FUNCTION IF EXISTS public.reject_social_append_only_change();
DROP FUNCTION IF EXISTS public.enforce_social_brand_tenant_scope();

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260908_social_creator_audiences_v1';

COMMIT;
