from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import delete, func
from sqlmodel import Session, select

from app.agents.branching import (
    visible_knowledge_base_versions,
    visible_published_skills,
    visible_tool_rows,
)
from app.core.capability_manifest import tool_snapshot_digest
from app.db.models import (
    AgentModelBinding,
    AgentProfile,
    AgentRelease,
    AgentReleaseEvent,
    AgentResourceBinding,
    AgentServiceIdentity,
    User,
    utc_now,
)

PRODUCTION_ROLES = {
    "operations_supervisor",
    "after_sales_specialist",
    "listing_compliance_specialist",
    "logistics_exception_specialist",
    "advertising_inspection_specialist",
    "designer",
    "procurement_specialist",
    "tiktok_bd_specialist",
    "tiktok_content_specialist",
    "tiktok_shop_operator",
    "tiktok_media_buyer",
    "tiktok_tap_manager",
    "tiktok_live_operator",
}
TIKTOK_PRODUCTION_ROLES = {
    "tiktok_bd_specialist",
    "tiktok_content_specialist",
    "tiktok_shop_operator",
    "tiktok_media_buyer",
    "tiktok_tap_manager",
    "tiktok_live_operator",
}
REQUIRED_PRODUCTION_RESOURCES = {"skill", "knowledge_base", "tool"}


class AgentReleaseError(ValueError):
    pass


def build_agent_release_snapshot(db: Session, agent: AgentProfile) -> dict[str, Any]:
    bindings = db.exec(
        select(AgentResourceBinding)
        .where(
            AgentResourceBinding.tenant_id == agent.tenant_id,
            AgentResourceBinding.agent_id == agent.id,
        )
        .order_by(AgentResourceBinding.resource_type, AgentResourceBinding.resource_id)
    ).all()
    models = db.exec(
        select(AgentModelBinding)
        .where(
            AgentModelBinding.tenant_id == agent.tenant_id,
            AgentModelBinding.agent_id == agent.id,
        )
        .order_by(AgentModelBinding.role)
    ).all()
    skills = visible_published_skills(db, agent.tenant_id, agent.id)
    knowledge = visible_knowledge_base_versions(
        db, agent.tenant_id, agent.id, include_inactive=False
    )
    tools = visible_tool_rows(db, agent.tenant_id, agent.id, include_inactive=False)
    return {
        "schema_version": "agent-release/v1",
        "agent": {
            "name": agent.name,
            "description": agent.description,
            "persona_prompt": agent.persona_prompt,
            "is_overall": agent.is_overall,
            "harness_max_actions": agent.harness_max_actions,
            "metadata": dict(agent.metadata_json or {}),
        },
        "resources": [
            {
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "status": row.status,
                "metadata": dict(row.metadata_json or {}),
            }
            for row in bindings
        ],
        "models": [
            {"role": row.role, "model_config_id": row.model_config_id}
            for row in models
        ],
        "resolved_capabilities": {
            "sops": [
                {
                    "resource_id": skill.id,
                    "skill_id": skill.skill_id,
                    "version": skill.version,
                    "content_digest": _value_digest(skill.content_json or {}),
                }
                for skill in sorted(skills, key=lambda row: (row.skill_id, row.version))
            ],
            "knowledge": [
                {
                    "knowledge_base_id": base_id,
                    "knowledge_base_version_id": version.id,
                    "version": version.version,
                    "metadata_digest": _value_digest(version.metadata_json or {}),
                }
                for base_id, version in sorted(knowledge.items())
            ],
            "tools": [
                {
                    "tool_id": tool.id,
                    "content_digest": tool_snapshot_digest(db, tool),
                }
                for tool in sorted(tools, key=lambda row: row.id)
            ],
        },
    }


def agent_snapshot_digest(snapshot: dict[str, Any]) -> str:
    canonical = json.dumps(snapshot, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def publish_agent_release(
    db: Session,
    *,
    tenant_id: str,
    agent_id: str,
    actor: User,
    reason: str,
    commit: bool = True,
) -> AgentRelease:
    _require_actor_tenant(actor, tenant_id)
    reason = _reason(reason, "Publish")
    agent = _agent(db, tenant_id, agent_id, for_update=True)
    snapshot = build_agent_release_snapshot(db, agent)
    _validate_production_readiness(db, agent, snapshot)
    digest = agent_snapshot_digest(snapshot)
    current = _active_release(db, tenant_id, agent_id)
    if current and current.snapshot_digest == digest and agent.release_state == "published":
        return current
    if current:
        current.status = "superseded"
        db.add(current)
    release = AgentRelease(
        tenant_id=tenant_id,
        agent_id=agent_id,
        version=_next_version(db, tenant_id, agent_id),
        snapshot_json=snapshot,
        snapshot_digest=digest,
        source_release_id=current.id if current else None,
        created_by_user_id=actor.id,
        release_reason=reason,
    )
    db.add(release)
    db.flush()
    agent.release_state = "published"
    agent.published_release_id = release.id
    agent.published_release_version = release.version
    agent.updated_at = utc_now()
    db.add(agent)
    _event(db, release, "published", actor, {"reason": reason, "snapshot_digest": digest})
    if commit:
        db.commit()
        db.refresh(release)
    return release


def preflight_agent_release(db: Session, agent: AgentProfile) -> dict[str, Any]:
    """Return a machine-readable release gate result without changing state."""

    snapshot = build_agent_release_snapshot(db, agent)
    result: dict[str, Any] = {
        "agent_id": agent.id,
        "release_state": agent.release_state,
        "snapshot_digest": agent_snapshot_digest(snapshot),
        "ready": False,
        "error": None,
    }
    try:
        _validate_production_readiness(db, agent, snapshot)
    except AgentReleaseError as exc:
        result["error"] = str(exc)
    else:
        result["ready"] = True
    return result


def rollback_agent_release(
    db: Session,
    *,
    tenant_id: str,
    agent_id: str,
    target_release_id: str,
    actor: User,
    reason: str,
) -> AgentRelease:
    _require_actor_tenant(actor, tenant_id)
    reason = _reason(reason, "Rollback")
    agent = _agent(db, tenant_id, agent_id, for_update=True)
    target = db.exec(
        select(AgentRelease).where(
            AgentRelease.tenant_id == tenant_id,
            AgentRelease.agent_id == agent_id,
            AgentRelease.id == target_release_id,
        )
    ).first()
    if not target:
        raise AgentReleaseError("Agent release not found")
    snapshot = dict(target.snapshot_json or {})
    if agent_snapshot_digest(snapshot) != target.snapshot_digest:
        raise AgentReleaseError("Target release digest is invalid")
    _restore_snapshot(db, agent, snapshot)
    db.flush()
    restored_snapshot = build_agent_release_snapshot(db, agent)
    _validate_production_readiness(db, agent, restored_snapshot)
    restored_digest = agent_snapshot_digest(restored_snapshot)
    if restored_digest != target.snapshot_digest:
        raise AgentReleaseError("Restored agent does not match the target release")
    current = _active_release(db, tenant_id, agent_id)
    if current:
        current.status = "superseded"
        db.add(current)
    release = AgentRelease(
        tenant_id=tenant_id,
        agent_id=agent_id,
        version=_next_version(db, tenant_id, agent_id),
        snapshot_json=restored_snapshot,
        snapshot_digest=restored_digest,
        source_release_id=target.id,
        created_by_user_id=actor.id,
        release_reason=reason,
    )
    db.add(release)
    db.flush()
    agent.release_state = "published"
    agent.published_release_id = release.id
    agent.published_release_version = release.version
    agent.updated_at = utc_now()
    db.add(agent)
    _event(
        db,
        release,
        "rolled_back",
        actor,
        {"reason": reason, "target_release_id": target.id},
    )
    db.commit()
    db.refresh(release)
    return release


def mark_agent_draft(
    db: Session,
    agent: AgentProfile,
    *,
    actor: User,
    reason: str,
) -> None:
    if agent.release_state == "draft":
        return
    agent.release_state = "draft"
    agent.updated_at = utc_now()
    db.add(agent)
    db.add(
        AgentReleaseEvent(
            tenant_id=agent.tenant_id,
            agent_id=agent.id,
            release_id=agent.published_release_id,
            event_type="draft_changed",
            actor_user_id=actor.id,
            detail_json={"reason": reason[:500]},
        )
    )


def mark_agent_draft_if_changed(
    db: Session,
    agent: AgentProfile,
    *,
    actor: User,
    reason: str,
) -> bool:
    """Move a published employee to draft only when its runtime snapshot changed."""

    if agent.release_state != "published" or not agent.published_release_id:
        return False
    release = db.exec(
        select(AgentRelease).where(
            AgentRelease.tenant_id == agent.tenant_id,
            AgentRelease.agent_id == agent.id,
            AgentRelease.id == agent.published_release_id,
            AgentRelease.status == "published",
        )
    ).first()
    if (
        release
        and agent_snapshot_digest(build_agent_release_snapshot(db, agent))
        == release.snapshot_digest
    ):
        return False
    mark_agent_draft(db, agent, actor=actor, reason=reason)
    return True


def record_agent_deactivation(db: Session, agent: AgentProfile, *, actor: User) -> None:
    db.add(
        AgentReleaseEvent(
            tenant_id=agent.tenant_id,
            agent_id=agent.id,
            release_id=agent.published_release_id,
            event_type="deactivated",
            actor_user_id=actor.id,
            detail_json={"published_release_version": agent.published_release_version},
        )
    )


def list_agent_releases(db: Session, *, tenant_id: str, agent_id: str) -> list[AgentRelease]:
    return list(
        db.exec(
            select(AgentRelease)
            .where(AgentRelease.tenant_id == tenant_id, AgentRelease.agent_id == agent_id)
            .order_by(AgentRelease.version.desc())
        ).all()
    )


def diff_agent_releases(left: AgentRelease, right: AgentRelease) -> list[dict[str, Any]]:
    left_flat = _flatten(left.snapshot_json or {})
    right_flat = _flatten(right.snapshot_json or {})
    changes: list[dict[str, Any]] = []
    for path in sorted(set(left_flat) | set(right_flat)):
        if left_flat.get(path) != right_flat.get(path):
            changes.append(
                {"path": path, "before": left_flat.get(path), "after": right_flat.get(path)}
            )
    return changes


def verify_agent_release_for_execution(db: Session, agent: AgentProfile) -> AgentRelease:
    if agent.release_state != "published" or not agent.published_release_id:
        raise AgentReleaseError("Digital employee has unpublished changes")
    release = db.exec(
        select(AgentRelease).where(
            AgentRelease.tenant_id == agent.tenant_id,
            AgentRelease.agent_id == agent.id,
            AgentRelease.id == agent.published_release_id,
            AgentRelease.status == "published",
        )
    ).first()
    if not release:
        raise AgentReleaseError("Digital employee has no active production release")
    snapshot = build_agent_release_snapshot(db, agent)
    if agent_snapshot_digest(snapshot) != release.snapshot_digest:
        raise AgentReleaseError("Digital employee configuration drifted from its release")
    _validate_production_readiness(db, agent, snapshot)
    return release


def _validate_production_readiness(
    db: Session,
    agent: AgentProfile,
    snapshot: dict[str, Any],
) -> None:
    if agent.is_overall:
        raise AgentReleaseError(
            "Open gallery aggregate cannot be published as a production employee"
        )
    if agent.status != "active":
        raise AgentReleaseError("Only an active digital employee can be published")
    role = str((agent.metadata_json or {}).get("business_role") or "")
    if role not in PRODUCTION_ROLES:
        return
    identity = db.exec(
        select(AgentServiceIdentity).where(
            AgentServiceIdentity.tenant_id == agent.tenant_id,
            AgentServiceIdentity.agent_id == agent.id,
            AgentServiceIdentity.business_role == role,
            AgentServiceIdentity.status == "active",
        )
    ).first()
    if not identity:
        raise AgentReleaseError("Production employee requires an active dedicated service identity")
    approved_types = {
        str(item.get("resource_type"))
        for item in snapshot.get("resources", [])
        if item.get("status") == "active"
        and isinstance(item.get("metadata"), dict)
        and item["metadata"].get("review_status") == "approved"
    }
    missing = sorted(REQUIRED_PRODUCTION_RESOURCES - approved_types)
    if missing:
        raise AgentReleaseError(
            f"Production employee lacks reviewed resources: {', '.join(missing)}"
        )
    if not visible_published_skills(db, agent.tenant_id, agent.id):
        raise AgentReleaseError("Production employee has no published SOP")
    if not visible_knowledge_base_versions(db, agent.tenant_id, agent.id, include_inactive=False):
        raise AgentReleaseError("Production employee has no active knowledge version")
    if not visible_tool_rows(db, agent.tenant_id, agent.id, include_inactive=False):
        raise AgentReleaseError("Production employee has no active tool")


def _restore_snapshot(db: Session, agent: AgentProfile, snapshot: dict[str, Any]) -> None:
    profile = snapshot.get("agent")
    if not isinstance(profile, dict):
        raise AgentReleaseError("Target release profile is invalid")
    name = str(profile.get("name") or "").strip()
    conflict = db.exec(
        select(AgentProfile).where(
            AgentProfile.tenant_id == agent.tenant_id,
            AgentProfile.name == name,
            AgentProfile.id != agent.id,
        )
    ).first()
    if not name or conflict:
        raise AgentReleaseError("Target release agent name is unavailable")
    agent.name = name
    agent.description = profile.get("description")
    agent.persona_prompt = profile.get("persona_prompt")
    agent.harness_max_actions = max(1, min(int(profile.get("harness_max_actions") or 32), 100))
    agent.metadata_json = dict(profile.get("metadata") or {})
    db.add(agent)
    db.exec(
        delete(AgentResourceBinding).where(
            AgentResourceBinding.tenant_id == agent.tenant_id,
            AgentResourceBinding.agent_id == agent.id,
        )
    )
    for item in snapshot.get("resources", []):
        db.add(
            AgentResourceBinding(
                tenant_id=agent.tenant_id,
                agent_id=agent.id,
                resource_type=str(item["resource_type"]),
                resource_id=str(item["resource_id"]),
                status=str(item.get("status") or "inactive"),
                metadata_json=dict(item.get("metadata") or {}),
            )
        )
    db.exec(
        delete(AgentModelBinding).where(
            AgentModelBinding.tenant_id == agent.tenant_id,
            AgentModelBinding.agent_id == agent.id,
        )
    )
    for item in snapshot.get("models", []):
        db.add(
            AgentModelBinding(
                tenant_id=agent.tenant_id,
                agent_id=agent.id,
                role=str(item["role"]),
                model_config_id=str(item["model_config_id"]),
            )
        )


def _agent(db: Session, tenant_id: str, agent_id: str, *, for_update: bool) -> AgentProfile:
    statement = select(AgentProfile).where(
        AgentProfile.tenant_id == tenant_id,
        AgentProfile.id == agent_id,
    )
    if for_update and db.bind is not None and db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    row = db.exec(statement).first()
    if not row:
        raise AgentReleaseError("Digital employee not found")
    return row


def _active_release(db: Session, tenant_id: str, agent_id: str) -> AgentRelease | None:
    return db.exec(
        select(AgentRelease).where(
            AgentRelease.tenant_id == tenant_id,
            AgentRelease.agent_id == agent_id,
            AgentRelease.status == "published",
        )
    ).first()


def _next_version(db: Session, tenant_id: str, agent_id: str) -> int:
    current = db.exec(
        select(func.max(AgentRelease.version)).where(
            AgentRelease.tenant_id == tenant_id,
            AgentRelease.agent_id == agent_id,
        )
    ).one()
    return int(current or 0) + 1


def _event(
    db: Session,
    release: AgentRelease,
    event_type: str,
    actor: User,
    detail: dict[str, Any],
) -> None:
    db.add(
        AgentReleaseEvent(
            tenant_id=release.tenant_id,
            agent_id=release.agent_id,
            release_id=release.id,
            event_type=event_type,
            actor_user_id=actor.id,
            detail_json=detail,
        )
    )


def _require_actor_tenant(actor: User, tenant_id: str) -> None:
    if actor.tenant_id != tenant_id:
        raise AgentReleaseError("Tenant mismatch")


def _reason(value: str, label: str) -> str:
    normalized = value.strip()
    if len(normalized) < 3:
        raise AgentReleaseError(f"{label} reason must contain at least 3 characters")
    return normalized[:1000]


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key in sorted(value):
            result.update(_flatten(value[key], f"{prefix}.{key}" if prefix else str(key)))
        return result
    if isinstance(value, list):
        result = {}
        for index, item in enumerate(value):
            result.update(_flatten(item, f"{prefix}[{index}]"))
        return result
    return {prefix: value}


def _value_digest(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
