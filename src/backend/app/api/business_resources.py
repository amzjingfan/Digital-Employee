from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.business_resources.schema import (
    ApprovalDecision,
    BusinessResourceCreate,
    BusinessResourceRead,
    BusinessResourceUpdate,
    HighRiskActionCreate,
    HighRiskActionRead,
    ResourceType,
)
from app.business_resources.service import (
    cancel_action_request,
    create_action_request,
    create_resource,
    decide_action_request,
    list_action_requests,
    list_resources,
    update_resource,
)
from app.db import get_session
from app.db.models import User
from app.security.auth import get_current_user

resource_router = APIRouter(prefix="/api/enterprise/business-resources", tags=["enterprise:business-resources"])
request_router = APIRouter(prefix="/api/enterprise/business-action-requests", tags=["enterprise:business-approvals"])
approval_router = APIRouter(prefix="/api/enterprise/business-approvals", tags=["enterprise:business-approvals"])


@resource_router.get("", response_model=list[BusinessResourceRead])
def get_resources(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
    resource_type: Annotated[ResourceType | None, Query()] = None,
) -> list[BusinessResourceRead]:
    return list_resources(
        db,
        tenant_id=tenant_id,
        user=current_user,
        resource_type=resource_type,
    )


@resource_router.post("", response_model=BusinessResourceRead)
def post_resource(
    request: BusinessResourceCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> BusinessResourceRead:
    return create_resource(db, request=request, user=current_user)


@resource_router.patch("/{resource_id}", response_model=BusinessResourceRead)
def patch_resource(
    resource_id: str,
    request: BusinessResourceUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> BusinessResourceRead:
    return update_resource(db, resource_id=resource_id, request=request, user=current_user)


@request_router.get("", response_model=list[HighRiskActionRead])
def get_my_action_requests(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
    status: Annotated[
        Literal["pending", "approved", "rejected", "cancelled", "invalidated"] | None,
        Query(),
    ] = None,
) -> list[HighRiskActionRead]:
    return list_action_requests(db, tenant_id=tenant_id, user=current_user, status=status)


@request_router.post("", response_model=HighRiskActionRead)
def post_action_request(
    request: HighRiskActionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> HighRiskActionRead:
    return create_action_request(db, request=request, user=current_user)


@request_router.post("/{request_id}/cancel", response_model=HighRiskActionRead)
def cancel_request(
    request_id: str,
    request: ApprovalDecision,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> HighRiskActionRead:
    return cancel_action_request(
        db,
        tenant_id=request.tenant_id,
        request_id=request_id,
        user=current_user,
    )


@approval_router.get("", response_model=list[HighRiskActionRead])
def get_approval_queue(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
    status: Annotated[
        Literal["pending", "approved", "rejected", "cancelled", "invalidated"] | None,
        Query(),
    ] = None,
) -> list[HighRiskActionRead]:
    return list_action_requests(
        db,
        tenant_id=tenant_id,
        user=current_user,
        status=status,
        approval_queue=True,
    )


@approval_router.post("/{request_id}/approve", response_model=HighRiskActionRead)
def approve_request(
    request_id: str,
    request: ApprovalDecision,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> HighRiskActionRead:
    return decide_action_request(
        db,
        tenant_id=request.tenant_id,
        request_id=request_id,
        decision="approved",
        reason=request.reason,
        user=current_user,
    )


@approval_router.post("/{request_id}/reject", response_model=HighRiskActionRead)
def reject_request(
    request_id: str,
    request: ApprovalDecision,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> HighRiskActionRead:
    return decide_action_request(
        db,
        tenant_id=request.tenant_id,
        request_id=request_id,
        decision="rejected",
        reason=request.reason,
        user=current_user,
    )
