BEGIN;

CREATE TABLE IF NOT EXISTS public.listing_rule_sets (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  platform varchar NOT NULL,
  marketplace varchar NOT NULL,
  category varchar NOT NULL,
  version varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'draft',
  rules_json json NOT NULL DEFAULT '{}'::json,
  content_digest varchar NOT NULL,
  source_references_json json NOT NULL DEFAULT '[]'::json,
  effective_at timestamp without time zone NOT NULL,
  expires_at timestamp without time zone,
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  reviewed_by_user_id varchar REFERENCES public.users(id) ON DELETE RESTRICT,
  reviewed_at timestamp without time zone,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_listing_rule_set_version UNIQUE (
    tenant_id, platform, marketplace, category, version
  ),
  CONSTRAINT listing_rule_sets_status_check CHECK (
    status IN ('draft', 'published', 'retired')
  ),
  CONSTRAINT listing_rule_sets_expiry_check CHECK (
    expires_at IS NULL OR expires_at > effective_at
  )
);
CREATE INDEX IF NOT EXISTS ix_listing_rule_sets_tenant_id
  ON public.listing_rule_sets (tenant_id);
CREATE INDEX IF NOT EXISTS ix_listing_rule_sets_content_digest
  ON public.listing_rule_sets (content_digest);
CREATE INDEX IF NOT EXISTS ix_listing_rule_sets_scope_status
  ON public.listing_rule_sets (tenant_id, platform, marketplace, category, status);

CREATE TABLE IF NOT EXISTS public.listing_compliance_checks (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  check_key varchar NOT NULL,
  store_resource_id varchar NOT NULL REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  product_key varchar NOT NULL,
  sku varchar NOT NULL,
  language varchar NOT NULL,
  rule_set_id varchar NOT NULL REFERENCES public.listing_rule_sets(id) ON DELETE RESTRICT,
  rule_version varchar NOT NULL,
  rule_digest varchar NOT NULL,
  sku_fact_version varchar NOT NULL,
  sku_facts_json json NOT NULL DEFAULT '{}'::json,
  content_json json NOT NULL DEFAULT '{}'::json,
  asset_version_ids_json json NOT NULL DEFAULT '[]'::json,
  findings_json json NOT NULL DEFAULT '[]'::json,
  gate_status varchar NOT NULL DEFAULT 'block',
  input_digest varchar NOT NULL,
  task_id varchar NOT NULL REFERENCES public.work_tasks(id) ON DELETE RESTRICT,
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_listing_compliance_check_key UNIQUE (tenant_id, check_key),
  CONSTRAINT listing_compliance_checks_gate_check CHECK (
    gate_status IN ('pass', 'warn', 'block')
  )
);
CREATE INDEX IF NOT EXISTS ix_listing_compliance_checks_tenant_id
  ON public.listing_compliance_checks (tenant_id);
CREATE INDEX IF NOT EXISTS ix_listing_compliance_checks_store_resource_id
  ON public.listing_compliance_checks (store_resource_id);
CREATE INDEX IF NOT EXISTS ix_listing_compliance_checks_product_time
  ON public.listing_compliance_checks (tenant_id, product_key, created_at DESC);

CREATE TABLE IF NOT EXISTS public.creative_briefs (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  brief_key varchar NOT NULL,
  store_resource_id varchar NOT NULL REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  product_key varchar NOT NULL,
  language varchar NOT NULL,
  dimensions_json json NOT NULL DEFAULT '{}'::json,
  selling_points_json json NOT NULL DEFAULT '[]'::json,
  scenes_json json NOT NULL DEFAULT '[]'::json,
  required_assets_json json NOT NULL DEFAULT '[]'::json,
  constraints_json json NOT NULL DEFAULT '{}'::json,
  status varchar NOT NULL DEFAULT 'open',
  task_id varchar NOT NULL REFERENCES public.work_tasks(id) ON DELETE RESTRICT,
  due_at timestamp without time zone,
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_creative_brief_key UNIQUE (tenant_id, brief_key),
  CONSTRAINT creative_briefs_status_check CHECK (
    status IN ('open', 'in_progress', 'completed', 'cancelled')
  )
);
CREATE INDEX IF NOT EXISTS ix_creative_briefs_tenant_id
  ON public.creative_briefs (tenant_id);
CREATE INDEX IF NOT EXISTS ix_creative_briefs_store_resource_id
  ON public.creative_briefs (store_resource_id);
CREATE INDEX IF NOT EXISTS ix_creative_briefs_product_status
  ON public.creative_briefs (tenant_id, product_key, status);

CREATE TABLE IF NOT EXISTS public.creative_asset_versions (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  asset_key varchar NOT NULL,
  version integer NOT NULL,
  brief_id varchar NOT NULL REFERENCES public.creative_briefs(id) ON DELETE RESTRICT,
  parent_version_id varchar REFERENCES public.creative_asset_versions(id) ON DELETE RESTRICT,
  store_resource_id varchar NOT NULL REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  product_key varchar NOT NULL,
  asset_type varchar NOT NULL,
  file_reference varchar NOT NULL,
  file_digest varchar NOT NULL,
  provenance_json json NOT NULL DEFAULT '{}'::json,
  generation_parameters_json json NOT NULL DEFAULT '{}'::json,
  checks_json json NOT NULL DEFAULT '{}'::json,
  required_human_approval boolean NOT NULL DEFAULT true,
  status varchar NOT NULL DEFAULT 'pending_review',
  creator_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  reviewed_by_user_id varchar REFERENCES public.users(id) ON DELETE RESTRICT,
  review_note varchar,
  reviewed_at timestamp without time zone,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_creative_asset_version UNIQUE (tenant_id, asset_key, version),
  CONSTRAINT creative_asset_versions_status_check CHECK (
    status IN ('draft', 'pending_review', 'approved', 'rejected')
  ),
  CONSTRAINT creative_asset_versions_version_check CHECK (version > 0)
);
CREATE INDEX IF NOT EXISTS ix_creative_asset_versions_tenant_id
  ON public.creative_asset_versions (tenant_id);
CREATE INDEX IF NOT EXISTS ix_creative_asset_versions_brief_id
  ON public.creative_asset_versions (brief_id);
CREATE INDEX IF NOT EXISTS ix_creative_asset_versions_file_digest
  ON public.creative_asset_versions (file_digest);
CREATE INDEX IF NOT EXISTS ix_creative_asset_versions_product_status
  ON public.creative_asset_versions (tenant_id, product_key, status);

CREATE TABLE IF NOT EXISTS public.procurement_recommendations (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  recommendation_key varchar NOT NULL,
  supplier_resource_id varchar NOT NULL REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  store_resource_id varchar REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  product_key varchar NOT NULL,
  sku varchar NOT NULL,
  input_snapshot_json json NOT NULL DEFAULT '{}'::json,
  formula varchar NOT NULL,
  recommended_quantity integer NOT NULL,
  estimated_landed_cost double precision NOT NULL,
  lead_time_days integer NOT NULL,
  risk_level varchar NOT NULL DEFAULT 'medium',
  risk_reasons_json json NOT NULL DEFAULT '[]'::json,
  status varchar NOT NULL DEFAULT 'draft',
  task_id varchar NOT NULL REFERENCES public.work_tasks(id) ON DELETE RESTRICT,
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  reviewed_by_user_id varchar REFERENCES public.users(id) ON DELETE RESTRICT,
  review_note varchar,
  reviewed_at timestamp without time zone,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_procurement_recommendation_key UNIQUE (tenant_id, recommendation_key),
  CONSTRAINT procurement_recommendations_status_check CHECK (
    status IN ('draft', 'reviewed', 'rejected')
  ),
  CONSTRAINT procurement_recommendations_quantity_check CHECK (
    recommended_quantity >= 0 AND estimated_landed_cost >= 0 AND lead_time_days >= 0
  ),
  CONSTRAINT procurement_recommendations_risk_check CHECK (
    risk_level IN ('low', 'medium', 'high', 'critical')
  )
);
CREATE INDEX IF NOT EXISTS ix_procurement_recommendations_tenant_id
  ON public.procurement_recommendations (tenant_id);
CREATE INDEX IF NOT EXISTS ix_procurement_recommendations_supplier_resource_id
  ON public.procurement_recommendations (supplier_resource_id);
CREATE INDEX IF NOT EXISTS ix_procurement_recommendations_product_status
  ON public.procurement_recommendations (tenant_id, product_key, status);

CREATE TABLE IF NOT EXISTS public.product_launch_gates (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  launch_key varchar NOT NULL,
  store_resource_id varchar NOT NULL REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  supplier_resource_id varchar NOT NULL REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  product_key varchar NOT NULL,
  sku varchar NOT NULL,
  sku_fact_version varchar NOT NULL,
  bom_version varchar NOT NULL,
  packaging_version varchar NOT NULL,
  certification_ids_json json NOT NULL DEFAULT '[]'::json,
  supplier_lead_time_confirmed boolean NOT NULL DEFAULT false,
  listing_check_id varchar NOT NULL REFERENCES public.listing_compliance_checks(id) ON DELETE RESTRICT,
  asset_version_ids_json json NOT NULL DEFAULT '[]'::json,
  procurement_recommendation_id varchar NOT NULL
    REFERENCES public.procurement_recommendations(id) ON DELETE RESTRICT,
  blockers_json json NOT NULL DEFAULT '[]'::json,
  evidence_digest varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'blocked',
  approval_request_id varchar REFERENCES public.high_risk_action_requests(id) ON DELETE RESTRICT,
  task_id varchar NOT NULL REFERENCES public.work_tasks(id) ON DELETE RESTRICT,
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  version integer NOT NULL DEFAULT 0,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_product_launch_gate_key UNIQUE (tenant_id, launch_key),
  CONSTRAINT product_launch_gates_status_check CHECK (
    status IN ('blocked', 'ready', 'waiting_approval', 'approved', 'rejected')
  ),
  CONSTRAINT product_launch_gates_version_check CHECK (version >= 0)
);
CREATE INDEX IF NOT EXISTS ix_product_launch_gates_tenant_id
  ON public.product_launch_gates (tenant_id);
CREATE INDEX IF NOT EXISTS ix_product_launch_gates_listing_check_id
  ON public.product_launch_gates (listing_check_id);
CREATE INDEX IF NOT EXISTS ix_product_launch_gates_approval_request_id
  ON public.product_launch_gates (approval_request_id);
CREATE INDEX IF NOT EXISTS ix_product_launch_gates_product_status
  ON public.product_launch_gates (tenant_id, product_key, status);

CREATE TABLE IF NOT EXISTS public.product_quality_issues (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  source_case_id varchar NOT NULL REFERENCES public.after_sales_cases(id) ON DELETE RESTRICT,
  store_resource_id varchar NOT NULL REFERENCES public.business_resources(id) ON DELETE RESTRICT,
  product_key varchar NOT NULL DEFAULT 'unknown',
  category varchar NOT NULL,
  root_cause varchar NOT NULL,
  task_ids_json json NOT NULL DEFAULT '[]'::json,
  status varchar NOT NULL DEFAULT 'open',
  created_by_user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_product_quality_issue_case UNIQUE (tenant_id, source_case_id),
  CONSTRAINT product_quality_issues_status_check CHECK (
    status IN ('open', 'investigating', 'resolved')
  )
);
CREATE INDEX IF NOT EXISTS ix_product_quality_issues_tenant_id
  ON public.product_quality_issues (tenant_id);
CREATE INDEX IF NOT EXISTS ix_product_quality_issues_source_case_id
  ON public.product_quality_issues (source_case_id);
CREATE INDEX IF NOT EXISTS ix_product_quality_issues_tenant_status_time
  ON public.product_quality_issues (tenant_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS public.commerce_governance_events (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL REFERENCES public.tenants(id) ON DELETE RESTRICT,
  aggregate_type varchar NOT NULL,
  aggregate_id varchar NOT NULL,
  event_type varchar NOT NULL,
  actor_type varchar NOT NULL DEFAULT 'human',
  actor_id varchar,
  actor_business_role varchar,
  detail_json json NOT NULL DEFAULT '{}'::json,
  occurred_at timestamp without time zone NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_commerce_governance_events_tenant_id
  ON public.commerce_governance_events (tenant_id);
CREATE INDEX IF NOT EXISTS ix_commerce_governance_events_aggregate_time
  ON public.commerce_governance_events (aggregate_type, aggregate_id, occurred_at);

CREATE OR REPLACE FUNCTION app.reject_commerce_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;

DROP TRIGGER IF EXISTS commerce_governance_events_append_only
  ON public.commerce_governance_events;
CREATE TRIGGER commerce_governance_events_append_only
BEFORE UPDATE OR DELETE ON public.commerce_governance_events
FOR EACH ROW EXECUTE FUNCTION app.reject_commerce_event_mutation();

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

DROP TRIGGER IF EXISTS listing_compliance_checks_immutable
  ON public.listing_compliance_checks;
CREATE TRIGGER listing_compliance_checks_immutable
BEFORE UPDATE OR DELETE ON public.listing_compliance_checks
FOR EACH ROW EXECUTE FUNCTION app.reject_commerce_event_mutation();

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

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'listing_rule_sets',
    'listing_compliance_checks',
    'creative_briefs',
    'creative_asset_versions',
    'procurement_recommendations',
    'product_launch_gates',
    'product_quality_issues',
    'commerce_governance_events'
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

GRANT SELECT, INSERT, UPDATE ON public.listing_rule_sets
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT ON public.listing_compliance_checks
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT, UPDATE ON public.creative_briefs
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT, UPDATE ON public.creative_asset_versions
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT, UPDATE ON public.procurement_recommendations
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT, UPDATE ON public.product_launch_gates
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT, UPDATE ON public.product_quality_issues
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;
GRANT SELECT, INSERT ON public.commerce_governance_events
  TO staffdeck_runtime, staffdeck_worker, staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260902_product_lifecycle_v1', now(), 'postgresql', 8, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
