BEGIN;

ALTER TABLE public.tenants
  ADD COLUMN IF NOT EXISTS status varchar NOT NULL DEFAULT 'active',
  ADD COLUMN IF NOT EXISTS casdoor_organization varchar,
  ADD COLUMN IF NOT EXISTS identity_sync_status varchar NOT NULL DEFAULT 'not_configured',
  ADD COLUMN IF NOT EXISTS default_locale varchar NOT NULL DEFAULT 'en',
  ADD COLUMN IF NOT EXISTS default_timezone varchar NOT NULL DEFAULT 'UTC',
  ADD COLUMN IF NOT EXISTS default_currency varchar NOT NULL DEFAULT 'USD';

CREATE INDEX IF NOT EXISTS ix_tenants_status ON public.tenants (status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tenants_casdoor_organization
  ON public.tenants (casdoor_organization)
  WHERE casdoor_organization IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_tenants_identity_sync_status
  ON public.tenants (identity_sync_status);

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS status varchar NOT NULL DEFAULT 'active',
  ADD COLUMN IF NOT EXISTS session_version integer NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS failed_login_attempts integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS locked_until timestamp without time zone,
  ADD COLUMN IF NOT EXISTS identity_sync_status varchar NOT NULL DEFAULT 'not_configured',
  ADD COLUMN IF NOT EXISTS preferred_locale varchar,
  ADD COLUMN IF NOT EXISTS preferred_timezone varchar;

CREATE INDEX IF NOT EXISTS ix_users_status ON public.users (status);
CREATE INDEX IF NOT EXISTS ix_users_locked_until ON public.users (locked_until);
CREATE INDEX IF NOT EXISTS ix_users_identity_sync_status ON public.users (identity_sync_status);

ALTER TABLE public.tenants DROP CONSTRAINT IF EXISTS tenants_status_check;
ALTER TABLE public.tenants ADD CONSTRAINT tenants_status_check
  CHECK (status IN ('provisioning', 'active', 'suspended', 'provisioning_failed'));
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_status_check;
ALTER TABLE public.users ADD CONSTRAINT users_status_check
  CHECK (status IN ('active', 'suspended'));
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_session_version_check;
ALTER TABLE public.users ADD CONSTRAINT users_session_version_check
  CHECK (session_version >= 1);
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_failed_login_attempts_check;
ALTER TABLE public.users ADD CONSTRAINT users_failed_login_attempts_check
  CHECK (failed_login_attempts >= 0);

CREATE TABLE IF NOT EXISTS public.user_invitations (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  username varchar NOT NULL,
  display_name varchar,
  role varchar NOT NULL DEFAULT 'member',
  business_role varchar NOT NULL DEFAULT 'member',
  auth_source varchar NOT NULL DEFAULT 'local',
  token_digest varchar NOT NULL,
  status varchar NOT NULL DEFAULT 'pending',
  invited_by_user_id varchar NOT NULL,
  accepted_by_user_id varchar,
  expires_at timestamp without time zone NOT NULL,
  accepted_at timestamp without time zone,
  cancelled_at timestamp without time zone,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_user_invitation_token_digest UNIQUE (tenant_id, token_digest),
  CONSTRAINT user_invitations_status_check
    CHECK (status IN ('pending', 'accepted', 'cancelled', 'expired')),
  CONSTRAINT user_invitations_auth_source_check
    CHECK (auth_source IN ('local', 'oidc'))
);

CREATE INDEX IF NOT EXISTS ix_user_invitations_tenant_id
  ON public.user_invitations (tenant_id);
CREATE INDEX IF NOT EXISTS ix_user_invitations_username
  ON public.user_invitations (username);
CREATE INDEX IF NOT EXISTS ix_user_invitations_role
  ON public.user_invitations (role);
CREATE INDEX IF NOT EXISTS ix_user_invitations_business_role
  ON public.user_invitations (business_role);
CREATE INDEX IF NOT EXISTS ix_user_invitations_auth_source
  ON public.user_invitations (auth_source);
CREATE INDEX IF NOT EXISTS ix_user_invitations_token_digest
  ON public.user_invitations (token_digest);
CREATE INDEX IF NOT EXISTS ix_user_invitations_status
  ON public.user_invitations (status);
CREATE INDEX IF NOT EXISTS ix_user_invitations_invited_by_user_id
  ON public.user_invitations (invited_by_user_id);
CREATE INDEX IF NOT EXISTS ix_user_invitations_accepted_by_user_id
  ON public.user_invitations (accepted_by_user_id);
CREATE INDEX IF NOT EXISTS ix_user_invitations_expires_at
  ON public.user_invitations (expires_at);
CREATE INDEX IF NOT EXISTS ix_user_invitations_accepted_at
  ON public.user_invitations (accepted_at);
CREATE INDEX IF NOT EXISTS ix_user_invitations_cancelled_at
  ON public.user_invitations (cancelled_at);
CREATE INDEX IF NOT EXISTS ix_user_invitations_created_at
  ON public.user_invitations (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_user_invitations_tenant_status_expires
  ON public.user_invitations (tenant_id, status, expires_at);

CREATE TABLE IF NOT EXISTS public.account_lifecycle_events (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  event_type varchar NOT NULL,
  actor_user_id varchar,
  subject_user_id varchar,
  subject_ref varchar NOT NULL DEFAULT '',
  outcome varchar NOT NULL DEFAULT 'allowed',
  reason varchar NOT NULL DEFAULT '',
  detail_json json NOT NULL DEFAULT '{}'::json,
  occurred_at timestamp without time zone NOT NULL,
  CONSTRAINT account_lifecycle_outcome_check
    CHECK (outcome IN ('allowed', 'denied', 'degraded'))
);

CREATE INDEX IF NOT EXISTS ix_account_lifecycle_events_tenant_id
  ON public.account_lifecycle_events (tenant_id);
CREATE INDEX IF NOT EXISTS ix_account_lifecycle_events_event_type
  ON public.account_lifecycle_events (event_type);
CREATE INDEX IF NOT EXISTS ix_account_lifecycle_events_actor_user_id
  ON public.account_lifecycle_events (actor_user_id);
CREATE INDEX IF NOT EXISTS ix_account_lifecycle_events_subject_user_id
  ON public.account_lifecycle_events (subject_user_id);
CREATE INDEX IF NOT EXISTS ix_account_lifecycle_events_subject_ref
  ON public.account_lifecycle_events (subject_ref);
CREATE INDEX IF NOT EXISTS ix_account_lifecycle_events_outcome
  ON public.account_lifecycle_events (outcome);
CREATE INDEX IF NOT EXISTS ix_account_lifecycle_events_occurred_at
  ON public.account_lifecycle_events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_account_lifecycle_tenant_subject_time
  ON public.account_lifecycle_events (tenant_id, subject_user_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION app.reject_account_lifecycle_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'account_lifecycle_events is append-only';
END;
$$;

DROP TRIGGER IF EXISTS account_lifecycle_events_append_only
  ON public.account_lifecycle_events;
CREATE TRIGGER account_lifecycle_events_append_only
BEFORE UPDATE OR DELETE ON public.account_lifecycle_events
FOR EACH ROW EXECUTE FUNCTION app.reject_account_lifecycle_event_mutation();

ALTER TABLE public.user_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_invitations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.user_invitations;
CREATE POLICY runtime_tenant_isolation ON public.user_invitations
FOR ALL TO staffdeck_runtime
USING (tenant_id = app.current_staffdeck_tenant_id())
WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
DROP POLICY IF EXISTS worker_all_tenants ON public.user_invitations;
CREATE POLICY worker_all_tenants ON public.user_invitations
FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

ALTER TABLE public.account_lifecycle_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.account_lifecycle_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.account_lifecycle_events;
CREATE POLICY runtime_tenant_isolation ON public.account_lifecycle_events
FOR ALL TO staffdeck_runtime
USING (tenant_id = app.current_staffdeck_tenant_id())
WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
DROP POLICY IF EXISTS worker_all_tenants ON public.account_lifecycle_events;
CREATE POLICY worker_all_tenants ON public.account_lifecycle_events
FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

REVOKE ALL ON public.user_invitations FROM PUBLIC;
REVOKE ALL ON public.account_lifecycle_events FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON public.user_invitations TO staffdeck_runtime;
GRANT SELECT, INSERT ON public.account_lifecycle_events TO staffdeck_runtime;
GRANT SELECT, INSERT, UPDATE ON public.user_invitations TO staffdeck_worker;
GRANT SELECT, INSERT ON public.account_lifecycle_events TO staffdeck_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_invitations TO staffdeck_migrator;
GRANT SELECT, INSERT ON public.account_lifecycle_events TO staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260902_account_lifecycle_v1', now(), 'postgresql', 2, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
