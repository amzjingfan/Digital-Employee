BEGIN;

CREATE TABLE IF NOT EXISTS public.offsite_channel_assets (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  brand_key varchar NOT NULL,
  store_resource_id varchar NOT NULL REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  store_code varchar NOT NULL,
  asset_type varchar NOT NULL,
  canonical_name varchar NOT NULL,
  stable_external_ref varchar NOT NULL,
  stable_external_digest varchar NOT NULL,
  region varchar NOT NULL,
  language varchar NOT NULL,
  categories_json json NOT NULL DEFAULT '[]'::json,
  tier varchar NOT NULL DEFAULT 'unassigned',
  lifecycle_status varchar NOT NULL DEFAULT 'discovered',
  owner_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  idempotency_key varchar NOT NULL,
  creation_digest varchar NOT NULL,
  last_verified_at timestamp without time zone,
  reviewed_by_user_id varchar REFERENCES public.users(id) ON DELETE RESTRICT,
  review_reason varchar,
  reviewed_at timestamp without time zone,
  version integer NOT NULL DEFAULT 0,
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_offsite_channel_asset_idempotency UNIQUE (tenant_id, idempotency_key),
  CONSTRAINT uq_offsite_channel_asset_identity UNIQUE (
    tenant_id, brand_key, asset_type, stable_external_digest
  ),
  CONSTRAINT uq_offsite_channel_asset_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_offsite_channel_asset_tenant_brand_id UNIQUE (tenant_id, brand_key, id),
  CONSTRAINT offsite_channel_assets_type_check CHECK (
    asset_type IN (
      'facebook_group', 'deal_site', 'creator', 'media_outlet',
      'author', 'affiliate', 'community'
    )
  ),
  CONSTRAINT offsite_channel_assets_status_check CHECK (
    lifecycle_status IN (
      'discovered', 'candidate', 'verifying', 'verified', 'piloting', 'active',
      'needs_review', 'paused', 'rejected', 'archived'
    )
  ),
  CONSTRAINT offsite_channel_assets_tier_check CHECK (
    tier IN ('unassigned', 'tier_1', 'tier_2', 'tier_3')
  ),
  CONSTRAINT offsite_channel_assets_version_check CHECK (version >= 0)
);

CREATE INDEX IF NOT EXISTS ix_offsite_channel_assets_tenant_status_updated
  ON public.offsite_channel_assets (tenant_id, lifecycle_status, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_offsite_channel_assets_tenant_store
  ON public.offsite_channel_assets (tenant_id, store_resource_id);
CREATE INDEX IF NOT EXISTS ix_offsite_channel_assets_brand_type
  ON public.offsite_channel_assets (tenant_id, brand_key, asset_type);
CREATE INDEX IF NOT EXISTS ix_offsite_channel_assets_external_digest
  ON public.offsite_channel_assets (tenant_id, stable_external_digest);

CREATE TABLE IF NOT EXISTS public.offsite_channel_evidence (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  brand_key varchar NOT NULL,
  asset_id varchar NOT NULL,
  evidence_type varchar NOT NULL,
  evidence_class varchar NOT NULL,
  value_json json NOT NULL DEFAULT '{}'::json,
  source_type varchar NOT NULL,
  source_record_id varchar NOT NULL,
  ingestion_batch_id varchar,
  captured_at timestamp without time zone NOT NULL,
  expires_at timestamp without time zone NOT NULL,
  confidence double precision NOT NULL,
  collector_type varchar NOT NULL DEFAULT 'human',
  collector_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  rule_version varchar NOT NULL,
  raw_hash varchar NOT NULL,
  idempotency_key varchar NOT NULL,
  payload_digest varchar NOT NULL,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_offsite_channel_evidence_idempotency UNIQUE (
    tenant_id, asset_id, idempotency_key
  ),
  CONSTRAINT offsite_channel_evidence_asset_fk FOREIGN KEY (tenant_id, brand_key, asset_id)
    REFERENCES public.offsite_channel_assets(tenant_id, brand_key, id) ON DELETE RESTRICT,
  CONSTRAINT offsite_channel_evidence_class_check CHECK (
    evidence_class IN ('observed_fact', 'source_claim', 'human_judgment')
  ),
  CONSTRAINT offsite_channel_evidence_source_check CHECK (
    source_type IN (
      'public_web', 'authorized_api', 'authorized_import',
      'business_record', 'human_observation'
    )
  ),
  CONSTRAINT offsite_channel_evidence_confidence_check CHECK (
    confidence >= 0 AND confidence <= 1
  ),
  CONSTRAINT offsite_channel_evidence_window_check CHECK (expires_at > captured_at)
);

CREATE INDEX IF NOT EXISTS ix_offsite_channel_evidence_asset_type_captured
  ON public.offsite_channel_evidence (asset_id, evidence_type, captured_at DESC);
CREATE INDEX IF NOT EXISTS ix_offsite_channel_evidence_tenant_expiry
  ON public.offsite_channel_evidence (tenant_id, expires_at);
CREATE INDEX IF NOT EXISTS ix_offsite_channel_evidence_source_record
  ON public.offsite_channel_evidence (tenant_id, source_type, source_record_id);

CREATE TABLE IF NOT EXISTS public.offsite_channel_events (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  brand_key varchar NOT NULL,
  asset_id varchar NOT NULL,
  event_type varchar NOT NULL,
  actor_type varchar NOT NULL DEFAULT 'human',
  actor_id varchar REFERENCES public.users(id) ON DELETE RESTRICT,
  actor_business_role varchar,
  from_status varchar,
  to_status varchar,
  detail_json json NOT NULL DEFAULT '{}'::json,
  occurred_at timestamp without time zone NOT NULL,
  CONSTRAINT offsite_channel_events_asset_fk FOREIGN KEY (tenant_id, brand_key, asset_id)
    REFERENCES public.offsite_channel_assets(tenant_id, brand_key, id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_offsite_channel_events_asset_time
  ON public.offsite_channel_events (asset_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_offsite_channel_events_tenant_type
  ON public.offsite_channel_events (tenant_id, brand_key, event_type);

CREATE OR REPLACE FUNCTION app.reject_offsite_channel_trace_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;

DROP TRIGGER IF EXISTS offsite_channel_evidence_append_only ON public.offsite_channel_evidence;
CREATE TRIGGER offsite_channel_evidence_append_only
BEFORE UPDATE OR DELETE ON public.offsite_channel_evidence
FOR EACH ROW EXECUTE FUNCTION app.reject_offsite_channel_trace_mutation();

DROP TRIGGER IF EXISTS offsite_channel_events_append_only ON public.offsite_channel_events;
CREATE TRIGGER offsite_channel_events_append_only
BEFORE UPDATE OR DELETE ON public.offsite_channel_events
FOR EACH ROW EXECUTE FUNCTION app.reject_offsite_channel_trace_mutation();

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'offsite_channel_assets',
    'offsite_channel_evidence',
    'offsite_channel_events'
  ] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS runtime_tenant_isolation ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY runtime_tenant_isolation ON public.%I FOR ALL TO staffdeck_runtime '
      'USING (tenant_id = app.current_staffdeck_tenant_id()) '
      'WITH CHECK (tenant_id = app.current_staffdeck_tenant_id())',
      table_name
    );
    EXECUTE format('DROP POLICY IF EXISTS worker_all_tenants ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY worker_all_tenants ON public.%I FOR ALL TO staffdeck_worker '
      'USING (true) WITH CHECK (true)',
      table_name
    );
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC', table_name);
  END LOOP;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON public.offsite_channel_assets
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT ON public.offsite_channel_evidence
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT ON public.offsite_channel_events
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260908_offsite_channel_assets_v1', now(), 'postgresql', 3, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
