BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_knowledge_chunks_tenant_id'
      AND conrelid = 'public.knowledge_chunks'::regclass
  ) THEN
    ALTER TABLE public.knowledge_chunks
      ADD CONSTRAINT uq_knowledge_chunks_tenant_id UNIQUE (tenant_id, id);
  END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS public.knowledge_chunk_embeddings (
  id varchar PRIMARY KEY,
  tenant_id varchar NOT NULL,
  knowledge_base_id varchar NOT NULL,
  knowledge_base_version_id varchar,
  document_id varchar NOT NULL,
  bucket_id varchar NOT NULL,
  chunk_id varchar NOT NULL,
  embedding_model varchar NOT NULL,
  embedding_dimensions integer NOT NULL,
  content_digest varchar NOT NULL,
  embedding vector(256) NOT NULL,
  created_at timestamp without time zone NOT NULL,
  updated_at timestamp without time zone NOT NULL,
  CONSTRAINT uq_knowledge_chunk_embeddings_tenant_chunk UNIQUE (tenant_id, chunk_id),
  CONSTRAINT knowledge_chunk_embeddings_dimensions_check CHECK (embedding_dimensions = 256),
  CONSTRAINT knowledge_chunk_embeddings_chunk_fk
    FOREIGN KEY (tenant_id, chunk_id)
    REFERENCES public.knowledge_chunks (tenant_id, id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_embeddings_tenant_id
  ON public.knowledge_chunk_embeddings (tenant_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_embeddings_knowledge_base_id
  ON public.knowledge_chunk_embeddings (knowledge_base_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_embeddings_version_id
  ON public.knowledge_chunk_embeddings (knowledge_base_version_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_embeddings_document_id
  ON public.knowledge_chunk_embeddings (document_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_embeddings_bucket_id
  ON public.knowledge_chunk_embeddings (bucket_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_embeddings_chunk_id
  ON public.knowledge_chunk_embeddings (chunk_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_embeddings_model
  ON public.knowledge_chunk_embeddings (embedding_model);
CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_embeddings_tenant_bucket
  ON public.knowledge_chunk_embeddings (tenant_id, bucket_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_chunk_embeddings_hnsw
  ON public.knowledge_chunk_embeddings
  USING hnsw (embedding vector_cosine_ops);

ALTER TABLE public.knowledge_chunk_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.knowledge_chunk_embeddings FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS runtime_tenant_isolation ON public.knowledge_chunk_embeddings;
CREATE POLICY runtime_tenant_isolation ON public.knowledge_chunk_embeddings
FOR ALL TO staffdeck_runtime
USING (tenant_id = app.current_staffdeck_tenant_id())
WITH CHECK (tenant_id = app.current_staffdeck_tenant_id());
DROP POLICY IF EXISTS worker_all_tenants ON public.knowledge_chunk_embeddings;
CREATE POLICY worker_all_tenants ON public.knowledge_chunk_embeddings
FOR ALL TO staffdeck_worker USING (true) WITH CHECK (true);

REVOKE ALL ON public.knowledge_chunk_embeddings FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.knowledge_chunk_embeddings TO staffdeck_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.knowledge_chunk_embeddings TO staffdeck_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.knowledge_chunk_embeddings TO staffdeck_migrator;

INSERT INTO public.staffdeck_schema_migrations (
  migration_id, applied_at, source_kind, source_table_count, source_row_count
)
VALUES ('20260902_knowledge_vector_index_v1', now(), 'postgresql', 1, 0)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
