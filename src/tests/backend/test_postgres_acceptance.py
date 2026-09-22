from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session

from app.db.database import engine, set_tenant_context
from app.db.models import KnowledgeChunk
from app.knowledge.vector_store import search_chunk_embedding_ids, upsert_chunk_embeddings

pytestmark = pytest.mark.skipif(
    os.getenv("STAFFDECK_RUN_POSTGRES_ACCEPTANCE") != "1",
    reason="set STAFFDECK_RUN_POSTGRES_ACCEPTANCE=1 against the isolated acceptance database",
)


def test_runtime_role_has_no_ddl_bypass_or_unscoped_reads() -> None:
    assert engine.dialect.name == "postgresql"
    with engine.connect() as connection:
        role = connection.execute(text("SELECT current_user")).scalar_one()
        privileges = connection.execute(
            text(
                """
                SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb,
                       has_schema_privilege(current_user, 'public', 'CREATE'),
                       has_table_privilege(current_user, 'tenants', 'UPDATE'),
                       has_table_privilege(current_user, 'staffdeck_schema_migrations', 'SELECT')
                FROM pg_roles WHERE rolname = current_user
                """
            )
        ).one()
        assert role == "staffdeck_runtime"
        assert tuple(privileges) == (False, False, False, False, False, False, False)
        assert connection.execute(text("SELECT count(*) FROM business_resources")).scalar_one() == 0


def test_connection_pool_never_reuses_previous_tenant_context() -> None:
    with Session(engine) as scoped:
        set_tenant_context(scoped, "tenant_demo")
        assert scoped.execute(text("SELECT count(*) FROM business_resources")).scalar_one() > 0
        scoped.commit()

    # A fresh transaction on a pooled connection starts without app.tenant_id.
    with Session(engine) as unscoped:
        assert unscoped.execute(text("SELECT count(*) FROM business_resources")).scalar_one() == 0
        set_tenant_context(unscoped, "tenant_does_not_exist")
        assert unscoped.execute(text("SELECT count(*) FROM business_resources")).scalar_one() == 0


def test_agent_releases_are_rls_scoped_and_database_immutable() -> None:
    with Session(engine) as db:
        assert db.execute(text("SELECT count(*) FROM agent_releases")).scalar_one() == 0
        set_tenant_context(db, "tenant_demo")
        release = db.execute(
            text(
                "SELECT id, snapshot_digest FROM agent_releases "
                "WHERE status='published' ORDER BY published_at LIMIT 1"
            )
        ).one()
        with pytest.raises(DBAPIError, match="immutable"):
            db.execute(
                text("UPDATE agent_releases SET snapshot_digest='sha256:tampered' WHERE id=:id"),
                {"id": release.id},
            )
        db.rollback()

    with Session(engine) as verify:
        set_tenant_context(verify, "tenant_demo")
        assert verify.execute(
            text("SELECT snapshot_digest FROM agent_releases WHERE id=:id"),
            {"id": release.id},
        ).scalar_one() == release.snapshot_digest
        privileges = verify.execute(
            text(
                "SELECT has_table_privilege(current_user, 'agent_release_events', 'UPDATE'), "
                "has_table_privilege(current_user, 'agent_release_events', 'DELETE')"
            )
        ).one()
        assert tuple(privileges) == (False, False)


def test_vector_upsert_retrieval_and_composite_tenant_fk() -> None:
    suffix = uuid4().hex[:12]
    chunk_refund = KnowledgeChunk(
        id=f"kchunk_accept_refund_{suffix}",
        tenant_id="tenant_demo",
        knowledge_base_id=f"kb_accept_{suffix}",
        knowledge_base_version_id=f"kbver_accept_{suffix}",
        document_id=f"kdoc_accept_{suffix}",
        bucket_id=f"kbucket_accept_{suffix}",
        chunk_index=0,
        content="refund damaged order customer return reimbursement policy",
    )
    chunk_ads = KnowledgeChunk(
        id=f"kchunk_accept_ads_{suffix}",
        tenant_id="tenant_demo",
        knowledge_base_id=f"kb_accept_{suffix}",
        knowledge_base_version_id=f"kbver_accept_{suffix}",
        document_id=f"kdoc_accept_{suffix}",
        bucket_id=f"kbucket_accept_{suffix}",
        chunk_index=1,
        content="advertising campaign budget impressions click through rate",
    )
    with Session(engine) as db:
        set_tenant_context(db, "tenant_demo")
        db.add(chunk_refund)
        db.add(chunk_ads)
        db.commit()
        try:
            assert upsert_chunk_embeddings(db, [chunk_refund, chunk_ads])
            db.commit()
            ids, error = search_chunk_embedding_ids(
                db,
                tenant_id="tenant_demo",
                bucket_ids=[chunk_refund.bucket_id],
                query="damaged order refund reimbursement",
                limit=2,
            )
            assert error is None
            assert ids[0] == chunk_refund.id

            original_digest = db.execute(
                text(
                    "SELECT content_digest FROM knowledge_chunk_embeddings "
                    "WHERE tenant_id=:tenant_id AND chunk_id=:chunk_id"
                ),
                {"tenant_id": "tenant_demo", "chunk_id": chunk_refund.id},
            ).scalar_one()
            chunk_refund.content += " approved evidence"
            db.add(chunk_refund)
            db.commit()
            assert upsert_chunk_embeddings(db, [chunk_refund])
            db.commit()
            updated = db.execute(
                text(
                    "SELECT count(*), min(content_digest) FROM knowledge_chunk_embeddings "
                    "WHERE tenant_id=:tenant_id AND chunk_id=:chunk_id"
                ),
                {"tenant_id": "tenant_demo", "chunk_id": chunk_refund.id},
            ).one()
            assert updated[0] == 1
            assert updated[1] != original_digest

            constraint = db.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname='knowledge_chunk_embeddings_chunk_fk'"
                )
            ).scalar_one()
            assert "FOREIGN KEY (tenant_id, chunk_id)" in constraint
        finally:
            db.execute(
                delete(KnowledgeChunk).where(
                    KnowledgeChunk.tenant_id == "tenant_demo",
                    KnowledgeChunk.id.in_([chunk_refund.id, chunk_ads.id]),
                )
            )
            db.commit()


def test_crossborder_aggregates_have_rls_foreign_keys_and_append_only_trace() -> None:
    suffix = uuid4().hex[:12]
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SELECT set_config('app.tenant_id', 'tenant_demo', true)"))
            store_id = connection.execute(
                text(
                    "SELECT id FROM business_resources "
                    "WHERE resource_type='store' ORDER BY created_at LIMIT 1"
                )
            ).scalar_one()
            task_id = connection.execute(
                text("SELECT id FROM work_tasks ORDER BY created_at LIMIT 1")
            ).scalar_one()
            case_id = f"aftersales_accept_{suffix}"
            event_id = f"aftersales_event_accept_{suffix}"
            connection.execute(
                text(
                    """
                    INSERT INTO after_sales_cases (
                      id, tenant_id, case_key, store_resource_id, store_code,
                      platform, marketplace_country, language,
                      order_reference_digest, order_reference_masked, status,
                      risk_level, needs_human, task_id, order_snapshot_json,
                      citations_json, recommendation_json, follow_up_task_ids_json,
                      created_by_user_id, version, created_at, updated_at
                    ) VALUES (
                      :id, 'tenant_demo', :case_key, :store_id, 'ACCEPT',
                      'Amazon', 'US', 'en', :digest, 'AM***0001', 'intake',
                      'medium', false, :task_id, '{}'::json, '[]'::json,
                      '{}'::json, '[]'::json, 'acceptance', 0, now(), now()
                    )
                    """
                ),
                {
                    "id": case_id,
                    "case_key": f"CASE-ACCEPT-{suffix}",
                    "store_id": store_id,
                    "task_id": task_id,
                    "digest": f"sha256:{suffix}",
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO after_sales_case_events (
                      id, tenant_id, case_id, event_type, actor_type,
                      to_status, detail_json, occurred_at
                    ) VALUES (
                      :id, 'tenant_demo', :case_id, 'acceptance_created',
                      'system', 'intake', '{}'::json, now()
                    )
                    """
                ),
                {"id": event_id, "case_id": case_id},
            )
            savepoint = connection.begin_nested()
            with pytest.raises(DBAPIError, match="permission denied|append-only"):
                connection.execute(
                    text(
                        "UPDATE after_sales_case_events "
                        "SET event_type='tampered' WHERE id=:id"
                    ),
                    {"id": event_id},
                )
            savepoint.rollback()
            assert connection.execute(
                text("SELECT event_type FROM after_sales_case_events WHERE id=:id"),
                {"id": event_id},
            ).scalar_one() == "acceptance_created"
            privileges = connection.execute(
                text(
                    "SELECT has_table_privilege(current_user, "
                    "'after_sales_case_events', 'UPDATE'), "
                    "has_table_privilege(current_user, 'after_sales_case_events', 'DELETE')"
                )
            ).one()
            assert tuple(privileges) == (False, False)
            foreign_keys = connection.execute(
                text(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE contype='f' AND conrelid IN "
                    "('after_sales_cases'::regclass, 'logistics_anomalies'::regclass)"
                )
            ).scalar_one()
            assert foreign_keys >= 6
        finally:
            transaction.rollback()

    with engine.connect() as unscoped:
        assert unscoped.execute(text("SELECT count(*) FROM after_sales_cases")).scalar_one() == 0
        assert unscoped.execute(text("SELECT count(*) FROM logistics_anomalies")).scalar_one() == 0


def test_product_lifecycle_has_rls_foreign_keys_and_immutable_review_evidence() -> None:
    suffix = uuid4().hex[:12]
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SELECT set_config('app.tenant_id', 'tenant_demo', true)"))
            user_id = connection.execute(
                text("SELECT id FROM users ORDER BY created_at LIMIT 1")
            ).scalar_one()
            rule_id = f"listing_rules_accept_{suffix}"
            connection.execute(
                text(
                    """
                    INSERT INTO listing_rule_sets (
                      id, tenant_id, platform, marketplace, category, version,
                      status, rules_json, content_digest, source_references_json,
                      effective_at, created_by_user_id, created_at
                    ) VALUES (
                      :id, 'tenant_demo', 'Amazon', 'US', 'Acceptance', :version,
                      'draft', '{}'::json, :digest, '[]'::json,
                      now(), :user_id, now()
                    )
                    """
                ),
                {
                    "id": rule_id,
                    "version": f"accept-{suffix}",
                    "digest": f"sha256:{suffix}",
                    "user_id": user_id,
                },
            )
            connection.execute(
                text(
                    "UPDATE listing_rule_sets SET status='published', "
                    "reviewed_by_user_id=:user_id, reviewed_at=now() WHERE id=:id"
                ),
                {"id": rule_id, "user_id": user_id},
            )
            savepoint = connection.begin_nested()
            with pytest.raises(DBAPIError, match="immutable"):
                connection.execute(
                    text("UPDATE listing_rule_sets SET content_digest='tampered' WHERE id=:id"),
                    {"id": rule_id},
                )
            savepoint.rollback()
            assert connection.execute(
                text("SELECT content_digest FROM listing_rule_sets WHERE id=:id"),
                {"id": rule_id},
            ).scalar_one() == f"sha256:{suffix}"
            privileges = connection.execute(
                text(
                    "SELECT has_table_privilege(current_user, "
                    "'listing_compliance_checks', 'UPDATE'), "
                    "has_table_privilege(current_user, "
                    "'commerce_governance_events', 'DELETE')"
                )
            ).one()
            assert tuple(privileges) == (False, False)
            foreign_keys = connection.execute(
                text(
                    "SELECT count(*) FROM pg_constraint WHERE contype='f' AND conrelid IN ("
                    "'listing_compliance_checks'::regclass, "
                    "'creative_asset_versions'::regclass, "
                    "'procurement_recommendations'::regclass, "
                    "'product_launch_gates'::regclass, "
                    "'product_quality_issues'::regclass)"
                )
            ).scalar_one()
            assert foreign_keys >= 18
        finally:
            transaction.rollback()

    with engine.connect() as unscoped:
        for table in (
            "listing_rule_sets",
            "listing_compliance_checks",
            "creative_asset_versions",
            "procurement_recommendations",
            "product_launch_gates",
            "product_quality_issues",
        ):
            assert unscoped.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0


def test_advertising_governance_has_rls_and_immutable_decision_evidence() -> None:
    suffix = uuid4().hex[:12]
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SELECT set_config('app.tenant_id', 'tenant_demo', true)"))
            account_id = connection.execute(
                text(
                    "SELECT id FROM business_resources WHERE resource_type='ad_account' "
                    "ORDER BY created_at LIMIT 1"
                )
            ).scalar_one()
            task_id = connection.execute(
                text("SELECT id FROM work_tasks ORDER BY created_at LIMIT 1")
            ).scalar_one()
            user_id = connection.execute(
                text("SELECT id FROM users ORDER BY created_at LIMIT 1")
            ).scalar_one()
            recommendation_id = f"ad_recommendation_accept_{suffix}"
            connection.execute(
                text(
                    """
                    INSERT INTO advertising_recommendations (
                      id, tenant_id, recommendation_key, ad_account_resource_id,
                      campaign_id, product_key, metric_snapshot_json,
                      constraint_snapshot_json, findings_json, recommendation_json,
                      proposed_action_payload_json, risk_level, status, input_digest,
                      task_id, linked_task_ids_json, created_by_user_id, version,
                      created_at, updated_at
                    ) VALUES (
                      :id, 'tenant_demo', :recommendation_key, :account_id,
                      'CAMPAIGN-ACCEPT', 'PRODUCT-ACCEPT', '{"acos": 0.2}'::json,
                      '{}'::json, '[]'::json, '{}'::json, '{}'::json,
                      'low', 'ready', :digest, :task_id, '[]'::json,
                      :user_id, 0, now(), now()
                    )
                    """
                ),
                {
                    "id": recommendation_id,
                    "recommendation_key": f"AD-ACCEPT-{suffix}",
                    "account_id": account_id,
                    "digest": f"sha256:{suffix}",
                    "task_id": task_id,
                    "user_id": user_id,
                },
            )
            savepoint = connection.begin_nested()
            with pytest.raises(DBAPIError, match="immutable"):
                connection.execute(
                    text(
                        "UPDATE advertising_recommendations "
                        "SET metric_snapshot_json='{\"acos\": 0.9}'::json WHERE id=:id"
                    ),
                    {"id": recommendation_id},
                )
            savepoint.rollback()
            privileges = connection.execute(
                text(
                    "SELECT has_table_privilege(current_user, "
                    "'automation_usage_ledger', 'UPDATE'), "
                    "has_table_privilege(current_user, "
                    "'automation_usage_ledger', 'DELETE')"
                )
            ).one()
            assert tuple(privileges) == (False, False)
            foreign_keys = connection.execute(
                text(
                    "SELECT count(*) FROM pg_constraint WHERE contype='f' AND conrelid IN ("
                    "'advertising_recommendations'::regclass, "
                    "'advertising_effect_follow_ups'::regclass, "
                    "'execution_automation_policies'::regclass, "
                    "'automation_usage_ledger'::regclass)"
                )
            ).scalar_one()
            assert foreign_keys >= 13
        finally:
            transaction.rollback()

    with engine.connect() as unscoped:
        for table in (
            "advertising_recommendations",
            "advertising_effect_follow_ups",
            "execution_automation_policies",
            "automation_usage_ledger",
        ):
            assert unscoped.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0


def test_bi_pipeline_has_composite_tenant_fks_rls_and_append_only_quality() -> None:
    suffix = uuid4().hex[:12]
    batch_id = f"bibatch_accept_{suffix}"
    quality_id = f"biquality_accept_{suffix}"
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SELECT set_config('app.tenant_id', 'tenant_demo', true)"))
            user_id = connection.execute(
                text("SELECT id FROM users ORDER BY created_at LIMIT 1")
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO bi_ingestion_batches (
                      id, tenant_id, source_key, window_start, window_end,
                      business_timezone, input_digest, status, quality_status,
                      row_count, accepted_count, created_by_user_id, created_at, completed_at
                    ) VALUES (
                      :id, 'tenant_demo', 'acceptance.manual', now() - interval '1 day', now(),
                      'UTC', :digest, 'succeeded', 'passed', 0, 0, :user_id, now(), now()
                    )
                    """
                ),
                {"id": batch_id, "digest": f"sha256:{suffix}", "user_id": user_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO bi_data_quality_checks (
                      id, tenant_id, batch_id, check_code, status, severity,
                      observed_json, expected_json, detail, created_at
                    ) VALUES (
                      :id, 'tenant_demo', :batch_id, 'acceptance_check', 'passed', 'info',
                      '{}'::jsonb, '{}'::jsonb, 'acceptance evidence', now()
                    )
                    """
                ),
                {"id": quality_id, "batch_id": batch_id},
            )
            savepoint = connection.begin_nested()
            with pytest.raises(DBAPIError, match="append-only"):
                connection.execute(
                    text(
                        "UPDATE bi_data_quality_checks SET detail='tampered' WHERE id=:id"
                    ),
                    {"id": quality_id},
                )
            savepoint.rollback()

            constraint_definitions = connection.execute(
                text(
                    """
                    SELECT pg_get_constraintdef(oid)
                    FROM pg_constraint
                    WHERE conname IN (
                      'bi_quality_checks_batch_fk',
                      'bi_daily_facts_batch_fk',
                      'bi_daily_facts_replaces_fk',
                      'bi_daily_metrics_batch_fk',
                      'bi_daily_metrics_definition_fk'
                    )
                    ORDER BY conname
                    """
                )
            ).scalars().all()
            assert len(constraint_definitions) == 5
            assert all("tenant_id" in definition for definition in constraint_definitions)
            assert connection.execute(
                text(
                    "SELECT count(*) FROM pg_indexes WHERE indexname IN ("
                    "'uq_bi_ingestion_batches_succeeded_window', "
                    "'uq_bi_daily_facts_current_external', "
                    "'uq_bi_daily_metrics_current_grain') AND indexdef LIKE '%WHERE%'"
                )
            ).scalar_one() == 3
        finally:
            transaction.rollback()

    with engine.connect() as unscoped:
        for table in (
            "bi_ingestion_batches",
            "bi_data_quality_checks",
            "bi_daily_commerce_facts",
            "bi_metric_definitions",
            "bi_daily_metrics",
        ):
            assert unscoped.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0


def test_tiktok_data_validation_tables_enforce_rls_and_append_only_runs() -> None:
    tables = (
        "tiktok_data_validation_scopes",
        "tiktok_field_contracts",
        "tiktok_capability_evidence",
        "tiktok_data_validation_runs",
    )
    with engine.connect() as unscoped:
        for table in tables:
            assert unscoped.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0

    suffix = uuid4().hex[:12]
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SELECT set_config('app.tenant_id', 'tenant_demo', true)"))
            user_id = connection.execute(
                text("SELECT id FROM users ORDER BY created_at LIMIT 1")
            ).scalar_one()
            run_id = f"tiktok_dv_accept_{suffix}"
            connection.execute(
                text(
                    "INSERT INTO tiktok_data_validation_runs "
                    "(id, tenant_id, mode, catalog_version, dataset_digest, record_count, "
                    "status, workbench_ready_snapshot, real_data_ready_snapshot, checks_json, "
                    "issues_json, started_by_user_id, created_at) VALUES "
                    "(:id, 'tenant_demo', 'mock', 'p3-b0.v1', :digest, 1, 'passed', "
                    "false, false, '[]'::jsonb, '[]'::jsonb, :user_id, now())"
                ),
                {"id": run_id, "digest": f"sha256:{suffix}", "user_id": user_id},
            )
            savepoint = connection.begin_nested()
            with pytest.raises(DBAPIError, match="append-only"):
                connection.execute(
                    text(
                        "UPDATE tiktok_data_validation_runs SET status='failed' WHERE id=:id"
                    ),
                    {"id": run_id},
                )
            savepoint.rollback()
        finally:
            transaction.rollback()
