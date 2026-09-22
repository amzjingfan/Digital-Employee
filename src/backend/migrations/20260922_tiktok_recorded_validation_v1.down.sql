BEGIN;

DO $joukir_recorded_validation_down$
BEGIN
  IF EXISTS (
    SELECT 1 FROM public.tiktok_data_validation_runs WHERE mode = 'recorded'
  ) THEN
    RAISE EXCEPTION 'cannot roll back recorded validation migration while audit rows exist';
  END IF;
END
$joukir_recorded_validation_down$;

DROP INDEX IF EXISTS public.ix_tiktok_dv_run_tenant_contract;
DROP INDEX IF EXISTS public.ix_tiktok_dv_run_tenant_scope;
DROP INDEX IF EXISTS public.ix_tiktok_dv_run_tenant_approver;

ALTER TABLE public.tiktok_data_validation_runs
  DROP CONSTRAINT tiktok_dv_run_real_ready_check,
  DROP CONSTRAINT tiktok_dv_run_recorded_metadata_check,
  DROP CONSTRAINT tiktok_dv_run_mode_check,
  DROP CONSTRAINT fk_tiktok_dv_run_tenant_scope,
  DROP CONSTRAINT fk_tiktok_dv_run_tenant_approver,
  DROP COLUMN attestation_version,
  DROP COLUMN contract_digest,
  DROP COLUMN scope_revision,
  DROP COLUMN scope_id,
  DROP COLUMN replay_as_of,
  DROP COLUMN data_period_end,
  DROP COLUMN data_period_start,
  DROP COLUMN approval_valid_until,
  DROP COLUMN approved_at,
  DROP COLUMN approved_by_user_id,
  DROP COLUMN approval_ref,
  DROP COLUMN source_label,
  ADD CONSTRAINT tiktok_dv_run_mode_check CHECK (mode = 'mock'),
  ADD CONSTRAINT tiktok_dv_run_real_ready_check CHECK (real_data_ready_snapshot = false);

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260922_tiktok_recorded_validation_v1';

COMMIT;
