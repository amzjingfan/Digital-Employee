from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import Tenant, User, WorkTask, WorkTaskEvent, WorkTaskEvidence, utc_now
from app.work_tasks.schema import (
    WorkTaskBatchCreate,
    WorkTaskBatchItem,
    WorkTaskCreate,
    WorkTaskEvidenceReference,
    WorkTaskTransition,
)
from app.work_tasks.service import (
    append_task_evidence,
    create_linked_task,
    create_task,
    create_tasks_batch,
    get_task,
    list_tasks,
    transition_task,
)


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _user(role: str, *, tenant_id: str = "tenant_demo") -> User:
    return User(
        tenant_id=tenant_id,
        username=f"user-{role}-{tenant_id}",
        role="member",
        business_role=role,
        password_hash="unused",
    )


def test_manager_creates_idempotent_role_queue_task() -> None:
    with _session() as db:
        manager = _user("operations_supervisor")
        db.add(Tenant(id="tenant_demo", name="Demo"))
        db.add(manager)
        db.commit()
        request = WorkTaskCreate(
            tenant_id="tenant_demo",
            idempotency_key="report-follow-up-stable",
            title="核对物流异常并补充回执",
            owner_business_role="logistics_exception_specialist",
            priority="high",
            due_at=utc_now() - timedelta(minutes=5),
        )

        first = create_task(db, request=request, user=manager)
        second = create_task(db, request=request, user=manager)
        result = list_tasks(db, tenant_id="tenant_demo", user=manager)

        assert first.id == second.id
        assert len(db.exec(select(WorkTask)).all()) == 1
        logistics_queue = next(
            item
            for item in result.queues
            if item.business_role == "logistics_exception_specialist"
        )
        assert logistics_queue.overdue == 1
        assert db.exec(select(WorkTaskEvent)).one().event_type == "created"


def test_linked_task_evidence_is_append_only_and_idempotent() -> None:
    with _session() as db:
        manager = _user("operations_supervisor")
        db.add(Tenant(id="tenant_demo", name="Demo"))
        db.add(manager)
        db.commit()
        reference = WorkTaskEvidenceReference(
            source_type="logistics_anomaly",
            source_id="anomaly-001",
            severity="high",
            label="物流异常 · stalled",
            summary="脱敏的异常摘要",
            source_route="/enterprise/crossborder-operations?anomaly_id=anomaly-001",
            occurred_at=utc_now(),
        )

        task, created = create_linked_task(
            db,
            tenant_id="tenant_demo",
            idempotency_key="logistics-escalation:anomaly-001:operations",
            source_type="logistics_escalation",
            source_id="anomaly-001",
            title="复核物流异常",
            description="请运营主管统筹处理",
            owner_business_role="operations_supervisor",
            assigned_by_user_id=manager.id,
            assigned_by_business_role=manager.business_role or "operations_supervisor",
            evidence=[reference],
        )
        repeated, repeated_created = create_linked_task(
            db,
            tenant_id="tenant_demo",
            idempotency_key="logistics-escalation:anomaly-001:operations",
            source_type="logistics_escalation",
            source_id="anomaly-001",
            title="复核物流异常",
            description="请运营主管统筹处理",
            owner_business_role="operations_supervisor",
            assigned_by_user_id=manager.id,
            assigned_by_business_role=manager.business_role or "operations_supervisor",
            evidence=[reference],
        )
        appended = append_task_evidence(db, task=task, evidence=[reference])
        db.commit()

        assert created is True
        assert repeated_created is False
        assert repeated.id == task.id
        assert appended == 0
        stored = db.exec(select(WorkTaskEvidence)).one()
        assert stored.task_id == task.id
        assert stored.source_id == "anomaly-001"
        assert [
            event.event_type
            for event in db.exec(
                select(WorkTaskEvent)
                .where(WorkTaskEvent.task_id == task.id)
                .order_by(WorkTaskEvent.created_at)
            ).all()
        ] == ["created_from_logistics_escalation", "evidence_linked"]


def test_specialist_only_sees_and_transitions_own_queue() -> None:
    with _session() as db:
        manager = _user("operations_supervisor")
        logistics = _user("logistics_exception_specialist")
        listing = _user("listing_compliance_specialist")
        db.add(Tenant(id="tenant_demo", name="Demo"))
        db.add(manager)
        db.add(logistics)
        db.add(listing)
        db.commit()
        created = create_task(
            db,
            request=WorkTaskCreate(
                tenant_id="tenant_demo",
                idempotency_key="logistics-task-001",
                title="检查物流轨迹",
                owner_business_role="logistics_exception_specialist",
            ),
            user=manager,
        )

        own_queue = list_tasks(db, tenant_id="tenant_demo", user=logistics)
        started = transition_task(
            db,
            task_id=created.id,
            request=WorkTaskTransition(
                tenant_id="tenant_demo",
                action="start",
                expected_version=created.version,
            ),
            user=logistics,
        )

        assert [item.id for item in own_queue.items] == [created.id]
        assert started.status == "in_progress"
        assert started.version == 1
        with pytest.raises(HTTPException) as forbidden:
            get_task(db, tenant_id="tenant_demo", task_id=created.id, user=listing)
        assert forbidden.value.status_code == 403


def test_transition_uses_optimistic_version_and_manager_only_cancel() -> None:
    with _session() as db:
        manager = _user("operations_supervisor")
        specialist = _user("after_sales_specialist")
        db.add(Tenant(id="tenant_demo", name="Demo"))
        db.add(manager)
        db.add(specialist)
        db.commit()
        task = create_task(
            db,
            request=WorkTaskCreate(
                tenant_id="tenant_demo",
                idempotency_key="after-sales-task-001",
                title="复核售后工单",
                owner_business_role="after_sales_specialist",
            ),
            user=manager,
        )

        with pytest.raises(HTTPException) as manager_only:
            transition_task(
                db,
                task_id=task.id,
                request=WorkTaskTransition(
                    tenant_id="tenant_demo",
                    action="cancel",
                    expected_version=0,
                ),
                user=specialist,
            )
        assert manager_only.value.status_code == 403
        started = transition_task(
            db,
            task_id=task.id,
            request=WorkTaskTransition(
                tenant_id="tenant_demo", action="start", expected_version=0
            ),
            user=specialist,
        )
        with pytest.raises(HTTPException) as conflict:
            transition_task(
                db,
                task_id=task.id,
                request=WorkTaskTransition(
                    tenant_id="tenant_demo",
                    action="request_review",
                    expected_version=0,
                ),
                user=specialist,
            )
        assert conflict.value.status_code == 409
        assert started.version == 1


def test_read_only_patrol_batch_is_atomic_and_idempotent() -> None:
    with _session() as db:
        manager = _user("operations_supervisor")
        db.add(Tenant(id="tenant_demo", name="Demo"))
        db.add(manager)
        db.commit()
        request = WorkTaskBatchCreate(
            tenant_id="tenant_demo",
            batch_idempotency_key="daily-patrol-2026-09-02",
            read_only_patrol=True,
            items=[
                WorkTaskBatchItem(
                    item_key="listing-us",
                    title="巡检美国站 Listing 合规",
                    owner_business_role="listing_compliance_specialist",
                    scope={"store_id": "STORE-US"},
                ),
                WorkTaskBatchItem(
                    item_key="logistics-us",
                    title="巡检美国站物流异常",
                    owner_business_role="logistics_exception_specialist",
                    scope={"store_id": "STORE-US"},
                ),
            ],
        )

        first = create_tasks_batch(db, request=request, user=manager)
        second = create_tasks_batch(db, request=request, user=manager)

        assert first.created_count == 2
        assert first.existing_count == 0
        assert second.created_count == 0
        assert second.existing_count == 2
        assert {item.source_type for item in first.items} == {"batch_patrol"}
        assert all(item.risk_level == "low" for item in first.items)
        assert len(db.exec(select(WorkTask)).all()) == 2
        assert {
            row.event_type for row in db.exec(select(WorkTaskEvent)).all()
        } == {"batch_patrol_created"}


def test_batch_rejects_duplicate_item_keys_before_writing() -> None:
    with _session() as db:
        manager = _user("operations_supervisor")
        db.add(Tenant(id="tenant_demo", name="Demo"))
        db.add(manager)
        db.commit()
        request = WorkTaskBatchCreate(
            tenant_id="tenant_demo",
            batch_idempotency_key="duplicate-patrol",
            items=[
                WorkTaskBatchItem(
                    item_key="same",
                    title="巡检任务一",
                    owner_business_role="listing_compliance_specialist",
                ),
                WorkTaskBatchItem(
                    item_key="same",
                    title="巡检任务二",
                    owner_business_role="logistics_exception_specialist",
                ),
            ],
        )

        with pytest.raises(HTTPException) as error:
            create_tasks_batch(db, request=request, user=manager)
        assert error.value.status_code == 422
        assert db.exec(select(WorkTask)).all() == []
