BEGIN;

DROP TRIGGER IF EXISTS account_lifecycle_events_append_only
  ON public.account_lifecycle_events;
DROP FUNCTION IF EXISTS app.reject_account_lifecycle_event_mutation();
DROP TABLE IF EXISTS public.account_lifecycle_events;
DROP TABLE IF EXISTS public.user_invitations;

DROP INDEX IF EXISTS public.uq_tenants_casdoor_organization;
DROP INDEX IF EXISTS public.ix_tenants_status;
DROP INDEX IF EXISTS public.ix_tenants_identity_sync_status;
ALTER TABLE public.tenants
  DROP COLUMN IF EXISTS status,
  DROP COLUMN IF EXISTS casdoor_organization,
  DROP COLUMN IF EXISTS identity_sync_status,
  DROP COLUMN IF EXISTS default_locale,
  DROP COLUMN IF EXISTS default_timezone,
  DROP COLUMN IF EXISTS default_currency;

ALTER TABLE public.users
  DROP COLUMN IF EXISTS status,
  DROP COLUMN IF EXISTS session_version,
  DROP COLUMN IF EXISTS failed_login_attempts,
  DROP COLUMN IF EXISTS locked_until,
  DROP COLUMN IF EXISTS identity_sync_status,
  DROP COLUMN IF EXISTS preferred_locale,
  DROP COLUMN IF EXISTS preferred_timezone;

DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260902_account_lifecycle_v1';

COMMIT;
