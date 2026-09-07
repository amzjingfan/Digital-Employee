from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db import get_session
from app.db.models import User
from app.security.auth import get_current_user
from app.work_tasks.schema import (
    WorkTaskBatchCreate,
    WorkTaskBatchResponse,
    WorkTaskCreate,
    WorkTaskListResponse,
    WorkTaskRead,
    WorkTaskTransition,
)
from app.work_tasks.service import (
    create_task,
    create_tasks_batch,
    get_task,
    list_tasks,
    transition_task,
)

router = APIRouter(prefix="/api/enterprise/work-tasks", tags=["enterprise:work-tasks"])


@router.get("", response_model=WorkTaskListResponse)
def get_work_tasks(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
    owner_business_role: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> WorkTaskListResponse:
    return list_tasks(
        db,
        tenant_id=tenant_id,
        user=current_user,
        owner_business_role=owner_business_role,
        status=status,
    )


@router.post("", response_model=WorkTaskRead)
def post_work_task(
    request: WorkTaskCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> WorkTaskRead:
    return create_task(db, request=request, user=current_user)


@router.post("/batch", response_model=WorkTaskBatchResponse)
def post_work_task_batch(
    request: WorkTaskBatchCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> WorkTaskBatchResponse:
    return create_tasks_batch(db, request=request, user=current_user)


@router.get("/{task_id}", response_model=WorkTaskRead)
def get_work_task(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> WorkTaskRead:
    return get_task(db, tenant_id=tenant_id, task_id=task_id, user=current_user)


@router.post("/{task_id}/transitions", response_model=WorkTaskRead)
def post_work_task_transition(
    task_id: str,
    request: WorkTaskTransition,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> WorkTaskRead:
    return transition_task(db, task_id=task_id, request=request, user=current_user)
