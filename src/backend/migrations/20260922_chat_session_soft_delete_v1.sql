BEGIN;

ALTER TABLE public.sessions
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_sessions_deleted_at
  ON public.sessions (deleted_at);

COMMIT;
