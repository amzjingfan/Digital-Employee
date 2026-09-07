from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import (
    BusinessActionExecution,
    HighRiskActionRequest,
    OperationsReport,
    OperationsReportComment,
    OperationsReportSource,
    ScheduledTaskRun,
    Tenant,
    User,
    WorkTask,
    WorkTaskEvent,
    utc_now,
)
from app.operations_reports.schema import (
    OperationsReportCommentCreate,
    OperationsReportFollowUpCreate,
    OperationsReportGenerate,
    OperationsReportReview,
)
from app.operations_reports.service import (
    add_comment,
    create_follow_up,
    generate_report,
    review_report,
)


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _user(role: str = "operations_supervisor", *, tenant_id: str = "tenant_demo") -> User:
    return User(
        tenant_id=tenant_id,
        username=f"user-{role}-{tenant_id}",
        role="member",
        business_role=role,
        password_hash="not-used",
    )


def _request(*, refresh: bool = False) -> OperationsReportGenerate:
    return OperationsReportGenerate(
        tenant_id="tenant_demo",
        report_type="daily",
        report_date=datetime.now(ZoneInfo("Asia/Shanghai")).date(),
        refresh=refresh,
    )


def test_daily_report_is_evidence_backed_redacted_and_idempotent() -> None:
    with _session() as db:
        supervisor = _user()
        db.add(Tenant(id="tenant_demo", name="Demo"))
        db.add(supervisor)
        approval = HighRiskActionRequest(
            tenant_id="tenant_demo",
            resource_id="store-1",
            resource_type="store",
            resource_name="Amazon US",
            action_type="issue_refund",
            summary="refund customer secret order details",
            payload_json={"order_id": "SECRET-ORDER", "amount": 99},
            requester_user_id="requester-1",
            requester_business_role="after_sales_specialist",
        )
        db.add(approval)
        db.flush()
        db.add(
            BusinessActionExecution(
                tenant_id="tenant_demo",
                request_id=approval.id,
                resource_id="store-1",
                action_type="issue_refund",
                connector_type="sandbox",
                status="manual_resolution_required",
                idempotency_key="stable-key",
                last_error_code="remote_result_unknown",
            )
        )
        db.add(
            ScheduledTaskRun(
                tenant_id="tenant_demo",
                scheduled_task_id="scheduled-1",
                agent_id="agent-logistics",
                user_id=supervisor.id,
                scheduled_for=utc_now(),
                status="failed",
            )
        )
        db.commit()

        first = generate_report(db, request=_request(), user=supervisor)
        second = generate_report(db, request=_request(), user=supervisor)

        assert first.id == second.id
        assert first.metrics["pending_approvals"] == 1
        assert first.metrics["failed_executions"] == 1
        assert first.source_count >= 2
        serialized = first.model_dump_json()
        assert "SECRET-ORDER" not in serialized
        assert "refund customer secret order details" not in serialized
        assert db.exec(select(OperationsReport)).all()
        assert db.exec(select(OperationsReportSource)).all()


def test_refresh_creates_new_immutable_snapshot() -> None:
    with _session() as db:
        supervisor = _user()
        db.add(Tenant(id="tenant_demo", name="Demo"))
        db.add(supervisor)
        db.commit()

        first = generate_report(db, request=_request(), user=supervisor)
        refreshed = generate_report(db, request=_request(refresh=True), user=supervisor)

        assert first.id != refreshed.id
        assert len(db.exec(select(OperationsReport)).all()) == 2


def test_success_only_activity_still_produces_traceable_evidence() -> None:
    with _session() as db:
        supervisor = _user()
        db.add(Tenant(id="tenant_demo", name="Demo"))
        db.add(supervisor)
        approval = HighRiskActionRequest(
            tenant_id="tenant_demo",
            resource_id="store-1",
            resource_type="store",
            resource_name="Amazon US",
            action_type="update_listing",
            summary="safe summary",
            status="approved",
            requester_user_id="requester-1",
            requester_business_role="listing_compliance_specialist",
        )
        db.add(approval)
        db.flush()
        db.add(
            BusinessActionExecution(
                tenant_id="tenant_demo",
                request_id=approval.id,
                resource_id="store-1",
                action_type="update_listing",
                connector_type="sandbox",
                status="succeeded",
                idempotency_key="successful-key",
            )
        )
        db.add(
            ScheduledTaskRun(
                tenant_id="tenant_demo",
                scheduled_task_id="scheduled-success",
                agent_id="agent-listing",
                user_id=supervisor.id,
                scheduled_for=utc_now(),
                status="completed",
            )
        )
        db.commit()

        report = generate_report(db, request=_request(), user=supervisor)

        assert report.data_status == "available"
        assert report.source_count == 3
        assert {item.source_type for item in report.sources} == {
            "approval",
            "execution",
            "scheduled_run",
        }


def test_report_review_comment_and_follow_up_are_append_only_records() -> None:
    with _session() as db:
        supervisor = _user()
        db.add(Tenant(id="tenant_demo", name="Demo"))
        db.add(supervisor)
        db.commit()
        report = generate_report(db, request=_request(), user=supervisor)

        commented = add_comment(
            db,
            report_id=report.id,
            request=OperationsReportCommentCreate(tenant_id="tenant_demo", body="请关注数据缺失"),
            user=supervisor,
        )
        follow_up_request = OperationsReportFollowUpCreate(
            tenant_id="tenant_demo",
            title="补齐物流巡检数据",
            owner_business_role="logistics_exception_specialist",
            priority="high",
        )
        followed = create_follow_up(
            db,
            report_id=report.id,
            request=follow_up_request,
            user=supervisor,
        )
        repeated = create_follow_up(
            db, report_id=report.id, request=follow_up_request, user=supervisor
        )
        confirmed = review_report(
            db,
            report_id=report.id,
            decision="confirmed",
            request=OperationsReportReview(tenant_id="tenant_demo", note="确认作为今日运营基线"),
            user=supervisor,
        )

        assert len(commented.comments) == 1
        assert followed.comments[-1].action_type == "follow_up_created"
        assert len(repeated.comments) == len(followed.comments)
        task = db.exec(select(WorkTask)).one()
        assert followed.comments[-1].detail["task_id"] == task.id
        assert task.owner_business_role == "logistics_exception_specialist"
        assert db.exec(select(WorkTaskEvent)).one().event_type == "created_from_report"
        assert confirmed.status == "confirmed"
        assert [item.action_type for item in db.exec(select(OperationsReportComment)).all()] == [
            "comment",
            "follow_up_created",
            "confirmed",
        ]
        with pytest.raises(HTTPException) as error:
            review_report(
                db,
                report_id=report.id,
                decision="rejected",
                request=OperationsReportReview(tenant_id="tenant_demo", note="不能重复评审"),
                user=supervisor,
            )
        assert error.value.status_code == 409


def test_specialist_and_cross_tenant_user_cannot_read_or_generate_management_report() -> None:
    with _session() as db:
        specialist = _user("after_sales_specialist")
        other_supervisor = _user(tenant_id="tenant_other")
        db.add(Tenant(id="tenant_demo", name="Demo"))
        db.add(Tenant(id="tenant_other", name="Other"))
        db.add(specialist)
        db.add(other_supervisor)
        db.commit()

        with pytest.raises(HTTPException) as role_error:
            generate_report(db, request=_request(), user=specialist)
        assert role_error.value.status_code == 403

        with pytest.raises(HTTPException) as tenant_error:
            generate_report(db, request=_request(), user=other_supervisor)
        assert tenant_error.value.status_code == 403
