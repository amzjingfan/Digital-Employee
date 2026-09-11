BEGIN;

CREATE OR REPLACE FUNCTION app.protect_agent_release()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'agent releases cannot be deleted';
  END IF;
  IF NEW.id IS DISTINCT FROM OLD.id OR
     NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR
     NEW.agent_id IS DISTINCT FROM OLD.agent_id OR
     NEW.version IS DISTINCT FROM OLD.version OR
     NEW.snapshot_json::jsonb IS DISTINCT FROM OLD.snapshot_json::jsonb OR
     NEW.snapshot_digest IS DISTINCT FROM OLD.snapshot_digest OR
     NEW.source_release_id IS DISTINCT FROM OLD.source_release_id OR
     NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id OR
     NEW.release_reason IS DISTINCT FROM OLD.release_reason OR
     NEW.created_at IS DISTINCT FROM OLD.created_at OR
     NEW.published_at IS DISTINCT FROM OLD.published_at THEN
    RAISE EXCEPTION 'agent release content is immutable';
  END IF;
  IF OLD.status = 'superseded' OR NEW.status NOT IN ('published', 'superseded') THEN
    RAISE EXCEPTION 'invalid agent release status transition';
  END IF;
  RETURN NEW;
END;
$$;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260902_agent_releases_v2_trigger_fix', now(), 'postgresql', 1, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
