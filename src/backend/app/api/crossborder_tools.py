from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlmodel import Session, select

from app.db import get_session
from app.db.database import set_tenant_context
from app.db.models import (
    AgentProfile,
    AgentResourceBinding,
    AgentSkillBranch,
    BusinessResource,
    BusinessResourceScope,
    HighRiskActionRequest,
    Skill,
    Tool,
    WorkTask,
)
from app.security.internal_service import (
    INTERNAL_AGENT_HEADER,
    INTERNAL_SKILL_HEADER,
    INTERNAL_TENANT_HEADER,
    INTERNAL_TOOL_HEADER,
    require_internal_production_tool,
)

router = APIRouter(
    prefix="/api/internal/tools/crossborder",
    tags=["internal-crossborder-tools"],
    dependencies=[Depends(require_internal_production_tool)],
)

_OPEN_TASK_STATUSES = ("pending", "in_progress", "waiting_input", "review", "failed")
_MAX_LIMIT = 50


@router.get("/role-context")
def role_context(
    limit: int = Query(default=20, ge=1, le=_MAX_LIMIT),
    resource_type: str | None = Query(default=None),
    tenant_id: str | None = Header(default=None, alias=INTERNAL_TENANT_HEADER),
    agent_id: str | None = Header(default=None, alias=INTERNAL_AGENT_HEADER),
    active_skill_id: str | None = Header(default=None, alias=INTERNAL_SKILL_HEADER),
    tool_name: str | None = Header(default=None, alias=INTERNAL_TOOL_HEADER),
    db: Session = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    """Return a least-privilege, credential-free read model for one role SOP."""

    if not all((tenant_id, agent_id, active_skill_id, tool_name)):
        raise HTTPException(status_code=403, detail="Trusted tool execution context is required")
    set_tenant_context(db, str(tenant_id))

    agent = db.get(AgentProfile, str(agent_id))
    if agent is None or agent.tenant_id != tenant_id or agent.status != "active":
        raise HTTPException(status_code=403, detail="Digital employee is not active in this tenant")
    business_role = str((agent.metadata_json or {}).get("business_role") or "")
    if not business_role:
        raise HTTPException(status_code=403, detail="Digital employee has no business role")

    tool = db.exec(select(Tool).where(Tool.tenant_id == tenant_id, Tool.name == tool_name)).first()
    if tool is None or not tool.enabled:
        raise HTTPException(status_code=403, detail="Production read tool is not enabled")
    production = (tool.config_json or {}).get("production")
    if not isinstance(production, dict) or production.get("risk_class") != "read_only":
        raise HTTPException(status_code=403, detail="Tool is not an approved read-only capability")
    if str(production.get("business_role") or "") != business_role:
        raise HTTPException(
            status_code=403, detail="Tool role does not match digital employee role"
        )
    if active_skill_id not in (tool.allowed_skills_json or []):
        raise HTTPException(status_code=403, detail="Tool is not approved for the active SOP")
    _require_active_binding(db, tenant_id, agent.id, "tool", tool.id)

    skill = db.exec(
        select(Skill).where(
            Skill.tenant_id == tenant_id,
            Skill.skill_id == active_skill_id,
            Skill.status == "published",
        )
    ).first()
    if skill is None:
        raise HTTPException(status_code=403, detail="Active SOP is not published")
    _require_active_binding(db, tenant_id, agent.id, "skill", skill.id)
    branch = db.exec(
        select(AgentSkillBranch).where(
            AgentSkillBranch.tenant_id == tenant_id,
            AgentSkillBranch.agent_id == agent.id,
            AgentSkillBranch.skill_id == active_skill_id,
            AgentSkillBranch.status == "active",
        )
    ).first()
    if branch is None:
        raise HTTPException(status_code=403, detail="Active SOP branch is not available")

    configured_types = tuple(
        str(value) for value in production.get("resource_types", []) if str(value)
    )
    if resource_type and resource_type not in configured_types:
        raise HTTPException(status_code=400, detail="Resource type is outside this role capability")
    requested_types = (resource_type,) if resource_type else configured_types

    resources = _resources_for_role(
        db,
        tenant_id=tenant_id,
        business_role=business_role,
        resource_types=requested_types,
        limit=limit,
    )
    tasks = _tasks_for_role(db, tenant_id=tenant_id, business_role=business_role, limit=limit)
    approvals = _approvals_for_role(
        db, tenant_id=tenant_id, business_role=business_role, limit=limit
    )
    return {
        "schema_version": "1.0",
        "source": "staffdeck_postgresql_read_model",
        "generated_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "agent_id": agent.id,
        "business_role": business_role,
        "active_skill_id": active_skill_id,
        "filters": {
            "resource_types": list(requested_types),
            "task_statuses": list(_OPEN_TASK_STATUSES),
            "limit": limit,
        },
        "resources": resources,
        "open_tasks": tasks,
        "pending_approvals": approvals,
        "data_quality": {
            "is_live_snapshot": True,
            "thresholds_included": False,
            "credentials_included": False,
            "warning": "Business thresholds, SLA and policy freshness must come from approved knowledge or tenant configuration.",
        },
    }


def _require_active_binding(
    db: Session, tenant_id: str, agent_id: str, resource_type: str, resource_id: str
) -> None:
    binding = db.exec(
        select(AgentResourceBinding).where(
            AgentResourceBinding.tenant_id == tenant_id,
            AgentResourceBinding.agent_id == agent_id,
            AgentResourceBinding.resource_type == resource_type,
            AgentResourceBinding.resource_id == resource_id,
            AgentResourceBinding.status == "active",
        )
    ).first()
    if binding is None:
        raise HTTPException(status_code=403, detail=f"Active {resource_type} binding is required")


def _resources_for_role(
    db: Session,
    *,
    tenant_id: str,
    business_role: str,
    resource_types: tuple[str, ...],
    limit: int,
) -> list[dict[str, Any]]:
    if not resource_types:
        return []
    if business_role == "operations_supervisor":
        rows = db.exec(
            select(BusinessResource)
            .where(
                BusinessResource.tenant_id == tenant_id,
                BusinessResource.resource_type.in_(resource_types),
                BusinessResource.status == "active",
            )
            .order_by(BusinessResource.resource_type, BusinessResource.name)
            .limit(limit)
        ).all()
        return [_resource_item(row, "operator") for row in rows]

    rows = db.exec(
        select(BusinessResource, BusinessResourceScope)
        .join(BusinessResourceScope, BusinessResourceScope.resource_id == BusinessResource.id)
        .where(
            BusinessResource.tenant_id == tenant_id,
            BusinessResourceScope.tenant_id == tenant_id,
            BusinessResourceScope.business_role == business_role,
            BusinessResource.resource_type.in_(resource_types),
            BusinessResource.status == "active",
        )
        .order_by(BusinessResource.resource_type, BusinessResource.name)
        .limit(limit)
    ).all()
    return [_resource_item(resource, scope.access_level) for resource, scope in rows]


def _resource_item(row: BusinessResource, access_level: str) -> dict[str, Any]:
    return {
        "resource_id": row.id,
        "resource_type": row.resource_type,
        "code": row.code,
        "name": row.name,
        "status": row.status,
        "access_level": access_level,
        "updated_at": row.updated_at.isoformat(),
    }


def _tasks_for_role(
    db: Session, *, tenant_id: str, business_role: str, limit: int
) -> list[dict[str, Any]]:
    statement = select(WorkTask).where(
        WorkTask.tenant_id == tenant_id,
        WorkTask.status.in_(_OPEN_TASK_STATUSES),
    )
    if business_role != "operations_supervisor":
        statement = statement.where(WorkTask.owner_business_role == business_role)
    rows = db.exec(statement.order_by(WorkTask.updated_at.desc()).limit(limit)).all()
    return [
        {
            "task_id": row.id,
            "title": row.title,
            "owner_business_role": row.owner_business_role,
            "priority": row.priority,
            "risk_level": row.risk_level,
            "status": row.status,
            "source_type": row.source_type,
            "due_at": row.due_at.isoformat() if row.due_at else None,
            "updated_at": row.updated_at.isoformat(),
        }
        for row in rows
    ]


def _approvals_for_role(
    db: Session, *, tenant_id: str, business_role: str, limit: int
) -> list[dict[str, Any]]:
    statement = select(HighRiskActionRequest).where(
        HighRiskActionRequest.tenant_id == tenant_id,
        HighRiskActionRequest.status == "pending",
    )
    if business_role != "operations_supervisor":
        statement = statement.where(HighRiskActionRequest.requester_business_role == business_role)
    rows = db.exec(statement.order_by(HighRiskActionRequest.requested_at.desc()).limit(limit)).all()
    return [
        {
            "request_id": row.id,
            "resource_id": row.resource_id,
            "resource_type": row.resource_type,
            "resource_name": row.resource_name,
            "action_type": row.action_type,
            "status": row.status,
            "requester_business_role": row.requester_business_role,
            "requested_at": row.requested_at.isoformat(),
        }
        for row in rows
    ]
