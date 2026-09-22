BEGIN;

ALTER TABLE public.tiktok_data_validation_runs
  ADD COLUMN source_label varchar,
  ADD COLUMN approval_ref varchar,
  ADD COLUMN approved_by_user_id varchar,
  ADD COLUMN approved_at timestamptz,
  ADD COLUMN approval_valid_until timestamptz,
  ADD COLUMN data_period_start timestamptz,
  ADD COLUMN data_period_end timestamptz,
  ADD COLUMN replay_as_of timestamptz,
  ADD COLUMN scope_id varchar,
  ADD COLUMN scope_revision integer,
  ADD COLUMN contract_digest varchar,
  ADD COLUMN attestation_version varchar;

ALTER TABLE public.tiktok_data_validation_runs
  DROP CONSTRAINT tiktok_dv_run_mode_check,
  DROP CONSTRAINT tiktok_dv_run_real_ready_check,
  ADD CONSTRAINT fk_tiktok_dv_run_tenant_approver
    FOREIGN KEY (tenant_id, approved_by_user_id)
    REFERENCES public.users(tenant_id, id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_tiktok_dv_run_tenant_scope
    FOREIGN KEY (tenant_id, scope_id)
    REFERENCES public.tiktok_data_validation_scopes(tenant_id, id) ON DELETE RESTRICT,
  ADD CONSTRAINT tiktok_dv_run_mode_check
    CHECK (mode IN ('mock', 'recorded')),
  ADD CONSTRAINT tiktok_dv_run_recorded_metadata_check CHECK (
    (
      mode = 'mock'
      AND source_label IS NULL
      AND approval_ref IS NULL
      AND approved_by_user_id IS NULL
      AND approved_at IS NULL
      AND approval_valid_until IS NULL
      AND data_period_start IS NULL
      AND data_period_end IS NULL
      AND replay_as_of IS NULL
      AND scope_id IS NULL
      AND scope_revision IS NULL
      AND contract_digest IS NULL
      AND attestation_version IS NULL
    )
    OR
    (
      mode = 'recorded'
      AND source_label IS NOT NULL
      AND approval_ref IS NOT NULL
      AND approved_by_user_id IS NOT NULL
      AND approved_at IS NOT NULL
      AND approval_valid_until IS NOT NULL
      AND data_period_start IS NOT NULL
      AND data_period_end IS NOT NULL
      AND replay_as_of IS NOT NULL
      AND scope_id IS NOT NULL
      AND scope_revision > 0
      AND contract_digest IS NOT NULL
      AND attestation_version = 'p3-b0-recorded.v1'
      AND approved_by_user_id <> started_by_user_id
      AND data_period_start <= data_period_end
      AND data_period_end <= replay_as_of
      AND replay_as_of <= approved_at
      AND approved_at < approval_valid_until
    )
  ),
  ADD CONSTRAINT tiktok_dv_run_real_ready_check CHECK (
    NOT real_data_ready_snapshot OR (mode = 'recorded' AND status = 'passed')
  );

CREATE INDEX IF NOT EXISTS ix_tiktok_dv_run_tenant_approver
  ON public.tiktok_data_validation_runs (tenant_id, approved_by_user_id);
CREATE INDEX IF NOT EXISTS ix_tiktok_dv_run_tenant_scope
  ON public.tiktok_data_validation_runs (tenant_id, scope_id);
CREATE INDEX IF NOT EXISTS ix_tiktok_dv_run_tenant_contract
  ON public.tiktok_data_validation_runs (tenant_id, contract_digest);

ALTER TABLE public.tiktok_data_validation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_data_validation_runs FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.tiktok_data_validation_runs FROM PUBLIC;
GRANT SELECT, INSERT ON public.tiktok_data_validation_runs TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.tiktok_data_validation_runs TO staffdeck_worker;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260922_tiktok_recorded_validation_v1', now(), 'postgresql', 1, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
