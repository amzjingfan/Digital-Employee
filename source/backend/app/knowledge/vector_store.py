from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.db.models import KnowledgeChunk, utc_now

VECTOR_DIMENSIONS = 256
VECTOR_MODEL = "staffdeck-hash-ngrams-v1"
_WORD_PATTERN = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]", re.IGNORECASE)


def deterministic_text_embedding(text_value: str) -> list[float]:
    """Return a stable local embedding used when no external embedding model is configured.

    It is intentionally deterministic and credential-free, which makes ingestion,
    replay, and tenant-isolation tests reproducible. Production deployments can
    replace rows with another reviewed model while retaining the same vector schema.
    """

    normalized = text_value.casefold()
    atoms = _WORD_PATTERN.findall(normalized)
    tokens = list(atoms)
    tokens.extend(f"{left}{right}" for left, right in zip(atoms, atoms[1:], strict=False))
    vector = [0.0] * VECTOR_DIMENSIONS
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % VECTOR_DIMENSIONS
        sign = -1.0 if digest[4] & 1 else 1.0
        vector[index] += sign * (1.0 + min(len(token), 12) / 12.0)
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude:
        vector = [value / magnitude for value in vector]
    return vector


def upsert_chunk_embeddings(db: Session, chunks: Iterable[KnowledgeChunk]) -> bool:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return False
    rows = []
    now = utc_now()
    for chunk in chunks:
        content_digest = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
        rows.append(
            {
                "id": f"kembed_{chunk.id}",
                "tenant_id": chunk.tenant_id,
                "knowledge_base_id": chunk.knowledge_base_id,
                "knowledge_base_version_id": chunk.knowledge_base_version_id,
                "document_id": chunk.document_id,
                "bucket_id": chunk.bucket_id,
                "chunk_id": chunk.id,
                "embedding_model": VECTOR_MODEL,
                "embedding_dimensions": VECTOR_DIMENSIONS,
                "content_digest": content_digest,
                "embedding": _vector_literal(deterministic_text_embedding(chunk.content)),
                "created_at": now,
                "updated_at": now,
            }
        )
    if not rows:
        return True
    statement = text(
        """
        INSERT INTO knowledge_chunk_embeddings (
          id, tenant_id, knowledge_base_id, knowledge_base_version_id,
          document_id, bucket_id, chunk_id, embedding_model,
          embedding_dimensions, content_digest, embedding, created_at, updated_at
        ) VALUES (
          :id, :tenant_id, :knowledge_base_id, :knowledge_base_version_id,
          :document_id, :bucket_id, :chunk_id, :embedding_model,
          :embedding_dimensions, :content_digest, CAST(:embedding AS vector),
          :created_at, :updated_at
        )
        ON CONFLICT (tenant_id, chunk_id) DO UPDATE SET
          knowledge_base_id = EXCLUDED.knowledge_base_id,
          knowledge_base_version_id = EXCLUDED.knowledge_base_version_id,
          document_id = EXCLUDED.document_id,
          bucket_id = EXCLUDED.bucket_id,
          embedding_model = EXCLUDED.embedding_model,
          embedding_dimensions = EXCLUDED.embedding_dimensions,
          content_digest = EXCLUDED.content_digest,
          embedding = EXCLUDED.embedding,
          updated_at = EXCLUDED.updated_at
        WHERE knowledge_chunk_embeddings.content_digest IS DISTINCT FROM EXCLUDED.content_digest
           OR knowledge_chunk_embeddings.embedding_model IS DISTINCT FROM EXCLUDED.embedding_model
        """
    )
    try:
        with db.begin_nested():
            db.execute(statement, rows)
    except SQLAlchemyError:
        return False
    return True


def search_chunk_embedding_ids(
    db: Session,
    *,
    tenant_id: str,
    bucket_ids: list[str],
    query: str,
    limit: int,
) -> tuple[list[str], str | None]:
    if db.bind is None or db.bind.dialect.name != "postgresql" or not bucket_ids:
        return [], "vector_backend_unavailable"
    statement = text(
        """
        SELECT chunk_id
        FROM knowledge_chunk_embeddings
        WHERE tenant_id = :tenant_id
          AND bucket_id = ANY(CAST(:bucket_ids AS varchar[]))
          AND embedding_model = :embedding_model
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
        """
    )
    try:
        with db.begin_nested():
            rows = db.execute(
                statement,
                {
                    "tenant_id": tenant_id,
                    "bucket_ids": bucket_ids,
                    "embedding_model": VECTOR_MODEL,
                    "embedding": _vector_literal(deterministic_text_embedding(query)),
                    "limit": max(1, min(limit, 100)),
                },
            ).all()
    except SQLAlchemyError as exc:
        return [], exc.__class__.__name__
    return [str(row[0]) for row in rows], None


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"
