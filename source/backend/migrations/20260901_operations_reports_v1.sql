BEGIN;

CREATE TABLE IF NOT EXISTS public.operations_reports (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  report_key varchar NOT NULL,
  report_type varchar NOT NULL,
  title varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'draft',
  timezone varchar NOT NULL DEFAULT 'Asia/Shanghai',
  period_start timestamp without time zone NOT NULL,
  period_end timestamp without time zone NOT NULL,
  scope_json json NOT NULL DEFAULT '{}'::json,
  metrics_json json NOT NULL DEFAULT '{}'::json,
  sections_json json NOT NULL DEFAULT '{}'::json,
  data_status varchar NOT NULL DEFAULT 'partial',
  source_count integer NOT NULL DEFAULT 0,
  generated_by_user_id varchar NOT NULL,
  generated_at timestamp without time zone NOT NULL,
  reviewed_by_user_id varchar,
  review_note varchar,
  reviewed_at timestamp without time zone,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_operations_report_key UNIQUE (tenant_id, report_key),
  CONSTRAINT operations_reports_type_check CHECK (report_type IN ('daily', 'weekly')),
  CONSTRAINT operations_reports_status_check CHECK (status IN ('draft', 'confirmed', 'rejected')),
  CONSTRAINT operations_reports_data_status_check CHECK (data_status IN ('available', 'partial', 'no_data')),
  CONSTRAINT operations_reports_period_check CHECK (period_end > period_start),
  CONSTRAINT operations_reports_source_count_check CHECK (source_count >= 0)
);

CREATE TABLE IF NOT EXISTS public.operations_report_sources (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  report_id varchar NOT NULL,
  source_type varchar NOT NULL,
  source_id varchar NOT NULL,
  business_key varchar NOT NULL,
  severity varchar NOT NULL DEFAULT 'info',
  label varchar NOT NULL,
  summary varchar NOT NULL,
  source_route varchar NOT NULL,
  occurred_at timestamp without time zone NOT NULL,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_operations_report_source UNIQUE (tenant_id, report_id, source_type, source_id),
  CONSTRAINT operations_report_sources_report_fk
    FOREIGN KEY (report_id) REFERENCES public.operations_reports(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS public.operations_report_comments (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  report_id varchar NOT NULL,
  action_type varchar NOT NULL DEFAULT 'comment',
  author_user_id varchar NOT NULL,
  author_business_role varchar NOT NULL,
  body varchar NOT NULL,
  detail_json json NOT NULL DEFAULT '{}'::json,
  created_at timestamp without time zone NOT NULL,
  CONSTRAINT operations_report_comments_action_check
    CHECK (action_type IN ('comment', 'confirmed', 'rejected', 'follow_up_created')),
  CONSTRAINT operations_report_comments_report_fk
    FOREIGN KEY (report_id) REFERENCES public.operations_reports(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_operations_reports_tenant_id ON public.operations_reports (tenant_id);
CREATE INDEX IF NOT EXISTS ix_operations_reports_report_key ON public.operations_reports (report_key);
CREATE INDEX IF NOT EXISTS ix_operations_reports_report_type ON public.operations_reports (report_type);
CREATE INDEX IF NOT EXISTS ix_operations_reports_status ON public.operations_reports (status);
CREATE INDEX IF NOT EXISTS ix_operations_reports_period_start ON public.operations_reports (period_start DESC);
CREATE INDEX IF NOT EXISTS ix_operations_reports_period_end ON public.operations_reports (period_end DESC);
CREATE INDEX IF NOT EXISTS ix_operations_reports_generated_at ON public.operations_reports (generated_at DESC);
CREATE INDEX IF NOT EXISTS ix_operations_reports_tenant_period
  ON public.operations_reports (tenant_id, report_type, period_start, period_end);
CREATE INDEX IF NOT EXISTS ix_operations_report_sources_tenant_id ON public.operations_report_sources (tenant_id);
CREATE INDEX IF NOT EXISTS ix_operations_report_sources_report_id ON public.operations_report_sources (report_id);
CREATE INDEX IF NOT EXISTS ix_operations_report_sources_source_type ON public.operations_report_sources (source_type);
CREATE INDEX IF NOT EXISTS ix_operations_report_sources_source_id ON public.operations_report_sources (source_id);
CREATE INDEX IF NOT EXISTS ix_operations_report_sources_business_key ON public.operations_report_sources (business_key);
CREATE INDEX IF NOT EXISTS ix_operations_report_sources_severity ON public.operations_report_sources (severity);
CREATE INDEX IF NOT EXISTS ix_operations_report_sources_report_time
  ON public.operations_report_sources (report_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_operations_report_comments_tenant_id ON public.operations_report_comments (tenant_id);
CREATE INDEX IF NOT EXISTS ix_operations_report_comments_report_id ON public.operations_report_comments (report_id);
CREATE INDEX IF NOT EXISTS ix_operations_report_comments_action_type ON public.operations_report_comments (action_type);
CREATE INDEX IF NOT EXISTS ix_operations_report_comments_author_user_id ON public.operations_report_comments (author_user_id);
CREATE INDEX IF NOT EXISTS ix_operations_report_comments_report_time
  ON public.operations_report_comments (report_id, created_at);

CREATE OR REPLACE FUNCTION app.reject_operations_report_evidence_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'operations report evidence is append-only';
END;
$$;

DROP TRIGGER IF EXISTS operations_report_sources_append_only ON public.operations_report_sources;
CREATE TRIGGER operations_report_sources_append_only
BEFORE UPDATE OR DELETE ON public.operations_report_sources
FOR EACH ROW EXECUTE FUNCTION app.reject_operations_report_evidence_mutation();

DROP TRIGGER IF EXISTS operations_report_comments_append_only ON public.operations_report_comments;
CREATE TRIGGER operations_report_comments_append_only
BEFORE UPDATE OR DELETE ON public.operations_report_comments
FOR EACH ROW EXECUTE FUNCTION app.reject_operations_report_evidence_mutation();

DO $staffdeck_operations_reports_rls$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'operations_reports',
    'operations_report_sources',
    'operations_report_comments'
  ]
  LOOP
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
END
$staffdeck_operations_reports_rls$;

GRANT SELECT, INSERT, UPDATE ON public.operations_reports TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.operations_report_sources TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.operations_report_comments TO staffdeck_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.operations_reports TO staffdeck_worker;
GRANT SELECT, INSERT ON public.operations_report_sources TO staffdeck_worker;
GRANT SELECT, INSERT ON public.operations_report_comments TO staffdeck_worker;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260901_operations_reports_v1', now(), 'postgresql', 3, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;

