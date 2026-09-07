from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db import get_session
from app.db.models import User
from app.operations_reports.schema import (
    OperationsReportCommentCreate,
    OperationsReportFollowUpCreate,
    OperationsReportGenerate,
    OperationsReportRead,
    OperationsReportReview,
)
from app.operations_reports.service import (
    add_comment,
    create_follow_up,
    generate_report,
    get_report,
    list_reports,
    review_report,
)
from app.security.auth import get_current_user

router = APIRouter(prefix="/api/enterprise/operations-reports", tags=["enterprise:operations-reports"])


@router.get("", response_model=list[OperationsReportRead])
def get_reports(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
    report_type: Annotated[Literal["daily", "weekly"] | None, Query()] = None,
) -> list[OperationsReportRead]:
    return list_reports(db, tenant_id=tenant_id, user=current_user, report_type=report_type)


@router.post("/generate", response_model=OperationsReportRead)
def post_generate_report(
    request: OperationsReportGenerate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> OperationsReportRead:
    return generate_report(db, request=request, user=current_user)


@router.get("/{report_id}", response_model=OperationsReportRead)
def get_report_detail(
    report_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> OperationsReportRead:
    return get_report(db, tenant_id=tenant_id, report_id=report_id, user=current_user)


@router.post("/{report_id}/comments", response_model=OperationsReportRead)
def post_report_comment(
    report_id: str,
    request: OperationsReportCommentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> OperationsReportRead:
    return add_comment(db, report_id=report_id, request=request, user=current_user)


@router.post("/{report_id}/confirm", response_model=OperationsReportRead)
def post_confirm_report(
    report_id: str,
    request: OperationsReportReview,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> OperationsReportRead:
    return review_report(
        db,
        report_id=report_id,
        decision="confirmed",
        request=request,
        user=current_user,
    )


@router.post("/{report_id}/reject", response_model=OperationsReportRead)
def post_reject_report(
    report_id: str,
    request: OperationsReportReview,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> OperationsReportRead:
    return review_report(
        db,
        report_id=report_id,
        decision="rejected",
        request=request,
        user=current_user,
    )


@router.post("/{report_id}/follow-ups", response_model=OperationsReportRead)
def post_report_follow_up(
    report_id: str,
    request: OperationsReportFollowUpCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> OperationsReportRead:
    return create_follow_up(db, report_id=report_id, request=request, user=current_user)

