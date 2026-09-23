from __future__ import annotations

from unittest.mock import Mock

import pytest
from sqlmodel import Session, create_engine

from app.api.knowledge import (
    _bucket_read_mapping_with_stats,
    _chunk_read_mapping,
    _safe_bucket_chunk_rows,
    _safe_document_bucket_rows,
)
from app.db.models import KnowledgeBucket, KnowledgeChunk


@pytest.mark.parametrize(
    ("reader", "scope_key"),
    [
        (_safe_document_bucket_rows, "document_id"),
        (_safe_bucket_chunk_rows, "bucket_id"),
    ],
)
def test_postgres_knowledge_graph_reads_do_not_use_sqlite_blob_type(reader, scope_key: str) -> None:
    db = Mock()
    db.get_bind.return_value.dialect.name = "postgresql"
    db.execute.return_value.mappings.return_value.all.return_value = []

    assert reader(db, "tenant_test", "item_test") == []

    statement, parameters = db.execute.call_args.args
    assert " AS BLOB" not in str(statement).upper()
    assert "WHERE tenant_id = :tenant_id" in str(statement)
    assert parameters == {"tenant_id": "tenant_test", scope_key: "item_test"}


def test_sqlite_knowledge_graph_reads_keep_legacy_blob_decoding() -> None:
    engine = create_engine("sqlite:///:memory:")
    KnowledgeBucket.__table__.create(engine)
    KnowledgeChunk.__table__.create(engine)
    with Session(engine) as db:
        db.add(
            KnowledgeBucket(
                id="bucket_test",
                tenant_id="tenant_test",
                knowledge_base_id="kb_test",
                document_id="document_test",
                bucket_key="section_test",
                title="配送政策",
                summary="按地址配送",
                metadata_json={"chunk_count": 1},
            )
        )
        db.add(
            KnowledgeChunk(
                id="chunk_test",
                tenant_id="tenant_test",
                knowledge_base_id="kb_test",
                document_id="document_test",
                bucket_id="bucket_test",
                chunk_index=0,
                content="配送说明",
                metadata_json={"section_path": ["配送政策"]},
            )
        )
        db.commit()

        bucket_row = _safe_document_bucket_rows(db, "tenant_test", "document_test")[0]
        chunk_row = _safe_bucket_chunk_rows(db, "tenant_test", "bucket_test")[0]

    assert isinstance(bucket_row["title"], bytes)
    assert isinstance(chunk_row["content"], bytes)
    assert _bucket_read_mapping_with_stats(bucket_row, 1).title == "配送政策"
    assert _chunk_read_mapping(chunk_row).content == "配送说明"
