BEGIN;

CREATE TABLE IF NOT EXISTS public.social_creators (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  canonical_name varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'active',
  idempotency_key varchar NOT NULL,
  request_digest varchar NOT NULL,
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_social_creator_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_social_creator_idempotency UNIQUE (tenant_id, idempotency_key),
  CONSTRAINT social_creators_status_check
    CHECK (status IN ('active', 'needs_review', 'archived'))
);
CREATE INDEX IF NOT EXISTS ix_social_creators_tenant_status
  ON public.social_creators (tenant_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS public.social_platform_identities (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  creator_id varchar NOT NULL,
  platform varchar NOT NULL,
  provider_identity_id varchar NOT NULL,
  public_handle varchar NOT NULL,
  profile_url varchar,
  verified boolean NOT NULL DEFAULT false,
  status varchar NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_social_identity_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_social_identity_creator UNIQUE (tenant_id, id, creator_id),
  CONSTRAINT uq_social_identity_provider
    UNIQUE (tenant_id, platform, provider_identity_id),
  CONSTRAINT fk_social_identity_creator
    FOREIGN KEY (tenant_id, creator_id)
    REFERENCES public.social_creators (tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT social_platform_identities_status_check
    CHECK (status IN ('active', 'needs_review', 'archived'))
);
CREATE INDEX IF NOT EXISTS ix_social_identities_tenant_creator
  ON public.social_platform_identities (tenant_id, creator_id, platform);

CREATE TABLE IF NOT EXISTS public.social_creator_evidence (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  creator_id varchar NOT NULL,
  identity_id varchar NOT NULL,
  country_code varchar,
  language_code varchar,
  category varchar,
  followers_count bigint NOT NULL DEFAULT 0,
  engagement_rate_bps integer NOT NULL DEFAULT 0,
  audience_country_code varchar,
  estimated_cost_minor bigint,
  currency varchar,
  quality_score integer NOT NULL DEFAULT 0,
  source_ref varchar NOT NULL,
  data_rights_basis varchar NOT NULL,
  contact_basis varchar NOT NULL DEFAULT 'none',
  observed_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  idempotency_key varchar NOT NULL,
  request_digest varchar NOT NULL,
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_social_evidence_idempotency UNIQUE (tenant_id, idempotency_key),
  CONSTRAINT fk_social_evidence_creator
    FOREIGN KEY (tenant_id, creator_id)
    REFERENCES public.social_creators (tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT fk_social_evidence_identity
    FOREIGN KEY (tenant_id, identity_id, creator_id)
    REFERENCES public.social_platform_identities (tenant_id, id, creator_id) ON DELETE RESTRICT,
  CONSTRAINT social_evidence_followers_check CHECK (followers_count >= 0),
  CONSTRAINT social_evidence_engagement_check
    CHECK (engagement_rate_bps >= 0 AND engagement_rate_bps <= 10000),
  CONSTRAINT social_evidence_cost_check
    CHECK (estimated_cost_minor IS NULL OR estimated_cost_minor >= 0),
  CONSTRAINT social_evidence_quality_check
    CHECK (quality_score >= 0 AND quality_score <= 100),
  CONSTRAINT social_evidence_rights_check
    CHECK (data_rights_basis IN ('contract_authorized', 'public_business', 'user_provided')),
  CONSTRAINT social_evidence_contact_basis_check
    CHECK (contact_basis IN ('none', 'contract_authorized', 'public_business')),
  CONSTRAINT social_evidence_time_check CHECK (expires_at > observed_at),
  CONSTRAINT social_evidence_cost_currency_check CHECK (
    (estimated_cost_minor IS NULL AND currency IS NULL)
    OR (estimated_cost_minor IS NOT NULL AND currency IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS ix_social_evidence_tenant_identity_observed
  ON public.social_creator_evidence (tenant_id, identity_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS ix_social_evidence_tenant_expiry
  ON public.social_creator_evidence (tenant_id, expires_at);

CREATE TABLE IF NOT EXISTS public.social_audience_snapshots (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  brand_id varchar NOT NULL REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  status varchar NOT NULL DEFAULT 'frozen',
  filters_json json NOT NULL DEFAULT '{}'::json,
  creator_ids_json json NOT NULL DEFAULT '[]'::json,
  identity_ids_json json NOT NULL DEFAULT '[]'::json,
  evidence_ids_json json NOT NULL DEFAULT '[]'::json,
  creator_count integer NOT NULL DEFAULT 0,
  audience_hash varchar NOT NULL,
  idempotency_key varchar NOT NULL,
  request_digest varchar NOT NULL,
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_social_audience_idempotency
    UNIQUE (tenant_id, brand_id, idempotency_key),
  CONSTRAINT social_audience_status_check CHECK (status = 'frozen'),
  CONSTRAINT social_audience_count_check CHECK (creator_count >= 0),
  CONSTRAINT social_audience_member_count_check CHECK (
    json_array_length(creator_ids_json) = creator_count
    AND json_array_length(identity_ids_json) = creator_count
    AND json_array_length(evidence_ids_json) = creator_count
  )
);
CREATE INDEX IF NOT EXISTS ix_social_audiences_tenant_brand_created
  ON public.social_audience_snapshots (tenant_id, brand_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.social_domain_events (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  brand_id varchar REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  aggregate_type varchar NOT NULL,
  aggregate_id varchar NOT NULL,
  event_type varchar NOT NULL,
  actor_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  request_id varchar NOT NULL,
  detail_json json NOT NULL DEFAULT '{}'::json,
  occurred_at timestamptz NOT NULL,
  CONSTRAINT social_domain_events_aggregate_check
    CHECK (aggregate_type IN ('creator', 'creator_evidence', 'audience_snapshot'))
);
CREATE INDEX IF NOT EXISTS ix_social_events_tenant_aggregate_time
  ON public.social_domain_events (tenant_id, aggregate_type, aggregate_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION public.reject_social_append_only_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'social evidence, audience snapshots, and audit events are append-only';
END;
$$;

CREATE OR REPLACE FUNCTION public.enforce_social_brand_tenant_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.brand_id IS NOT NULL AND NOT EXISTS (
    SELECT 1
    FROM public.business_resources AS resource
    WHERE resource.id = NEW.brand_id
      AND resource.tenant_id = NEW.tenant_id
      AND resource.status = 'active'
      AND resource.resource_type IN ('store', 'social_account')
  ) THEN
    RAISE EXCEPTION 'social brand scope is missing, inactive, or belongs to another tenant';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS social_audience_brand_tenant_scope
  ON public.social_audience_snapshots;
CREATE TRIGGER social_audience_brand_tenant_scope
BEFORE INSERT ON public.social_audience_snapshots
FOR EACH ROW EXECUTE FUNCTION public.enforce_social_brand_tenant_scope();

DROP TRIGGER IF EXISTS social_event_brand_tenant_scope
  ON public.social_domain_events;
CREATE TRIGGER social_event_brand_tenant_scope
BEFORE INSERT ON public.social_domain_events
FOR EACH ROW EXECUTE FUNCTION public.enforce_social_brand_tenant_scope();

DROP TRIGGER IF EXISTS social_creator_evidence_append_only
  ON public.social_creator_evidence;
CREATE TRIGGER social_creator_evidence_append_only
BEFORE UPDATE OR DELETE ON public.social_creator_evidence
FOR EACH ROW EXECUTE FUNCTION public.reject_social_append_only_change();

DROP TRIGGER IF EXISTS social_audience_snapshots_append_only
  ON public.social_audience_snapshots;
CREATE TRIGGER social_audience_snapshots_append_only
BEFORE UPDATE OR DELETE ON public.social_audience_snapshots
FOR EACH ROW EXECUTE FUNCTION public.reject_social_append_only_change();

DROP TRIGGER IF EXISTS social_domain_events_append_only
  ON public.social_domain_events;
CREATE TRIGGER social_domain_events_append_only
BEFORE UPDATE OR DELETE ON public.social_domain_events
FOR EACH ROW EXECUTE FUNCTION public.reject_social_append_only_change();

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'social_creators',
    'social_platform_identities',
    'social_creator_evidence',
    'social_audience_snapshots',
    'social_domain_events'
  ] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS runtime_tenant_isolation ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY runtime_tenant_isolation ON public.%I FOR ALL TO staffdeck_runtime '
      'USING (tenant_id = app.current_staffdeck_tenant_id()) '
      'WITH CHECK (tenant_id = app.current_staffdeck_tenant_id())', table_name
    );
    EXECUTE format('DROP POLICY IF EXISTS worker_all_tenants ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY worker_all_tenants ON public.%I FOR ALL TO staffdeck_worker '
      'USING (true) WITH CHECK (true)', table_name
    );
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC', table_name);
  END LOOP;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON public.social_creators
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT, UPDATE ON public.social_platform_identities
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT ON public.social_creator_evidence
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT ON public.social_audience_snapshots
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT ON public.social_domain_events
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260908_social_creator_audiences_v1', now(), 'postgresql', 5, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
