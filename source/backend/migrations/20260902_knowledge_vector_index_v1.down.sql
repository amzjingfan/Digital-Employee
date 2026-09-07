BEGIN;

DROP TABLE IF EXISTS public.knowledge_chunk_embeddings;
ALTER TABLE public.knowledge_chunks
  DROP CONSTRAINT IF EXISTS uq_knowledge_chunks_tenant_id;
DELETE FROM public.staffdeck_schema_migrations
WHERE migration_id = '20260902_knowledge_vector_index_v1';

COMMIT;
