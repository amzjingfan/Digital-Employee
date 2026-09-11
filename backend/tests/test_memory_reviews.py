from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import (
    AgentProfile,
    MemoryRecord,
    MemoryReviewEvent,
    MemoryReviewRequest,
    Tenant,
    User,
)
from app.memory.reviews import (
    decide_memory_review,
    list_memory_reviews,
    submit_memory_review,
)


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _user(user_id: str, *, role: str = "member") -> User:
    return User(
        id=user_id,
        tenant_id="tenant_demo",
        username=user_id,
        role=role,
        password_hash="disabled",
    )


@pytest.fixture
def review_setup():
    engine = _engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        owner = _user("memory-owner")
        reviewer = _user("agent-owner")
        outsider = _user("outsider")
        db.add(Tenant(id="tenant_demo", name="Demo"))
        db.add_all([owner, reviewer, outsider])
        db.add(
            AgentProfile(
                id="agent-owned",
                tenant_id="tenant_demo",
                name="受管员工",
                status="active",
                metadata_json={"owner_user_id": reviewer.id},
            )
        )
        memory = MemoryRecord(
            id="memory-1",
            tenant_id="tenant_demo",
            user_id=owner.id,
            username=owner.username,
            kind="preference",
            content="客户希望售后回复简洁",
            metadata_json={"agent_id": "agent-owned", "key": "reply_style"},
        )
        db.add(memory)
        db.commit()
        yield engine, owner, reviewer, outsider, memory.id


def test_owner_submits_idempotent_private_memory_review(review_setup) -> None:
    engine, owner, _, outsider, memory_id = review_setup
    with Session(engine) as db:
        first = submit_memory_review(
            db,
            tenant_id="tenant_demo",
            memory_id=memory_id,
            note="请审核这条偏好是否适合长期保留",
            user=owner,
        )
        duplicate = submit_memory_review(
            db,
            tenant_id="tenant_demo",
            memory_id=memory_id,
            note="网络重试不应重复创建",
            user=owner,
        )
        assert duplicate.id == first.id
        assert first.status == "pending"
        assert first.memory_snapshot["content"] == "客户希望售后回复简洁"
        assert len(db.exec(select(MemoryReviewRequest)).all()) == 1

        assert list_memory_reviews(db, tenant_id="tenant_demo", user=outsider) == []
        assert [row.id for row in list_memory_reviews(db, tenant_id="tenant_demo", user=owner)] == [
            first.id
        ]


def test_agent_owner_reviews_snapshot_without_sharing_live_memory(review_setup) -> None:
    engine, owner, reviewer, _, memory_id = review_setup
    with Session(engine) as db:
        submitted = submit_memory_review(
            db,
            tenant_id="tenant_demo",
            memory_id=memory_id,
            note="请求质量审核",
            user=owner,
        )
        with pytest.raises(HTTPException) as own_review:
            decide_memory_review(
                db,
                tenant_id="tenant_demo",
                review_id=submitted.id,
                decision="approved",
                note="自行批准",
                user=owner,
            )
        assert own_review.value.status_code == 403

        queue = list_memory_reviews(
            db,
            tenant_id="tenant_demo",
            user=reviewer,
            agent_id="agent-owned",
            review_queue=True,
        )
        assert [row.id for row in queue] == [submitted.id]
        approved = decide_memory_review(
            db,
            tenant_id="tenant_demo",
            review_id=submitted.id,
            decision="approved",
            note="内容准确，仅用于该用户和员工上下文",
            user=reviewer,
        )
        memory = db.get(MemoryRecord, memory_id)
        assert approved.status == "approved"
        assert approved.decided_by_user_id == reviewer.id
        assert memory is not None
        assert "shared" not in memory.metadata_json
        assert [event.event_type for event in db.exec(select(MemoryReviewEvent)).all()] == [
            "submitted",
            "approved",
        ]


def test_changed_memory_invalidates_submitted_snapshot(review_setup) -> None:
    engine, owner, reviewer, _, memory_id = review_setup
    with Session(engine) as db:
        submitted = submit_memory_review(
            db,
            tenant_id="tenant_demo",
            memory_id=memory_id,
            note="请求审核",
            user=owner,
        )
        memory = db.get(MemoryRecord, memory_id)
        assert memory is not None
        memory.content = "客户现在要求售后回复提供完整步骤"
        db.add(memory)
        db.commit()

        with pytest.raises(HTTPException) as stale:
            decide_memory_review(
                db,
                tenant_id="tenant_demo",
                review_id=submitted.id,
                decision="approved",
                note="批准旧快照",
                user=reviewer,
            )
        assert stale.value.status_code == 409
        review = db.get(MemoryReviewRequest, submitted.id)
        assert review is not None and review.status == "invalidated"


def test_memory_review_rejects_cross_tenant_submission(review_setup) -> None:
    engine, owner, _, _, memory_id = review_setup
    with Session(engine) as db:
        with pytest.raises(HTTPException) as denied:
            submit_memory_review(
                db,
                tenant_id="tenant_other",
                memory_id=memory_id,
                note="跨租户请求",
                user=owner,
            )
        assert denied.value.status_code == 403
