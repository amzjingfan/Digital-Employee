BEGIN;

DELETE FROM public.staffdeck_schema_migrations WHERE migration_id = '20260901_work_tasks_v1';
DROP TABLE IF EXISTS public.work_task_events;
DROP TABLE IF EXISTS public.work_task_evidence;
DROP TABLE IF EXISTS public.work_tasks;
DROP FUNCTION IF EXISTS app.reject_work_task_append_only_mutation();

COMMIT;

