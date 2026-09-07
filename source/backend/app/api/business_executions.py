from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.business_execution.service import (
    list_executions,
    reconcile_execution,
    request_compensation,
    retry_execution,
)
from app.business_resources.schema import (
    BusinessActionExecutionRead,
    ExecutionOperatorCommand,
    ExecutionReconciliationReport,
)
from app.db import get_session
from app.db.models import User
from app.security.auth import get_current_user

router = APIRouter(
    prefix="/api/enterprise/business-executions",
    tags=["enterprise:business-executions"],
)

ExecutionStatus = Literal[
    "queued",
    "running",
    "retry_wait",
    "succeeded",
    "failed",
    "compensation_requested",
    "compensating",
    "compensated",
    "compensation_failed",
    "manual_resolution_required",
]


@router.get("", response_model=list[BusinessActionExecutionRead])
def get_executions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
    status: Annotated[ExecutionStatus | None, Query()] = None,
) -> list[BusinessActionExecutionRead]:
    return list_executions(db, tenant_id=tenant_id, user=current_user, status=status)


@router.post("/{execution_id}/retry", response_model=BusinessActionExecutionRead)
def retry_business_execution(
    execution_id: str,
    command: ExecutionOperatorCommand,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> BusinessActionExecutionRead:
    return retry_execution(
        db,
        tenant_id=command.tenant_id,
        execution_id=execution_id,
        reason=command.reason,
        user=current_user,
    )


@router.post("/{execution_id}/compensate", response_model=BusinessActionExecutionRead)
def compensate_business_execution(
    execution_id: str,
    command: ExecutionOperatorCommand,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> BusinessActionExecutionRead:
    return request_compensation(
        db,
        tenant_id=command.tenant_id,
        execution_id=execution_id,
        reason=command.reason,
        user=current_user,
    )


@router.post("/{execution_id}/reconcile", response_model=BusinessActionExecutionRead)
def reconcile_business_execution(
    execution_id: str,
    report: ExecutionReconciliationReport,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> BusinessActionExecutionRead:
    return reconcile_execution(
        db,
        execution_id=execution_id,
        report=report,
        user=current_user,
    )
