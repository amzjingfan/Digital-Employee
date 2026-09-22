BEGIN;

DROP INDEX IF EXISTS public.ix_sessions_deleted_at;

ALTER TABLE public.sessions
  DROP COLUMN IF EXISTS deleted_at;

COMMIT;
