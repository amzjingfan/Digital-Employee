from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlmodel import Session, select

from app.db.models import (
    BusinessActionExecution,
    BusinessResource,
    BusinessResourceScope,
    HighRiskActionRequest,
)


def action_content_digest(action: HighRiskActionRequest) -> str:
    """Return a stable digest for every field covered by an approval decision."""

    return _digest(
        {
            "tenant_id": action.tenant_id,
            "resource_id": action.resource_id,
            "resource_type": action.resource_type,
            "action_type": action.action_type,
            "summary": action.summary,
            "payload": dict(action.payload_json or {}),
            "requester_user_id": action.requester_user_id,
            "requester_business_role": action.requester_business_role,
        }
    )


def resource_context_digest(db: Session, resource: BusinessResource) -> str:
    """Digest the resource context an approver relied on, including role grants."""

    scopes = db.exec(
        select(BusinessResourceScope).where(
            BusinessResourceScope.tenant_id == resource.tenant_id,
            BusinessResourceScope.resource_id == resource.id,
        )
    ).all()
    return _digest(
        {
            "tenant_id": resource.tenant_id,
            "resource_id": resource.id,
            "resource_type": resource.resource_type,
            "code": resource.code,
            "name": resource.name,
            "status": resource.status,
            "metadata": dict(resource.metadata_json or {}),
            "scopes": sorted(
                [
                    {
                        "business_role": scope.business_role,
                        "access_level": scope.access_level,
                    }
                    for scope in scopes
                ],
                key=lambda item: (item["business_role"], item["access_level"]),
            ),
        }
    )


def approval_integrity_error(
    db: Session,
    action: HighRiskActionRequest,
    resource: BusinessResource,
    *,
    execution: BusinessActionExecution | None = None,
) -> str | None:
    expected_content = (
        execution.approval_content_digest if execution else action.content_digest
    )
    expected_resource = (
        execution.resource_snapshot_digest if execution else action.resource_snapshot_digest
    )
    if not expected_content or action_content_digest(action) != expected_content:
        return "approved_action_content_changed"
    if not expected_resource or resource_context_digest(db, resource) != expected_resource:
        return "approved_resource_context_changed"
    if resource.status != "active":
        return "approved_resource_inactive"
    return None


def _digest(value: dict[str, Any]) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
