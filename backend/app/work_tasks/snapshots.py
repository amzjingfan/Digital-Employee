from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlmodel import Session

from app.agents.branching import (
    visible_knowledge_base_versions,
    visible_published_skills,
    visible_tool_rows,
)
from app.core.agent_identity_prompt import AgentIdentityPrompt
from app.core.capability_manifest import tool_snapshot_digest
from app.db.models import (
    AgentProfile,
    AgentRelease,
    AgentServiceIdentity,
    WorkTask,
    WorkTaskExecutionSnapshot,
    WorkTaskRun,
)
from app.skills.nesting import SopNestingError, expand_sop_for_execution


class WorkTaskSnapshotError(RuntimeError):
    pass


def build_execution_snapshot(
    db: Session,
    *,
    task: WorkTask,
    run: WorkTaskRun,
    agent: AgentProfile,
    agent_release: AgentRelease,
    service_identity: AgentServiceIdentity,
) -> WorkTaskExecutionSnapshot:
    if (
        agent_release.tenant_id != task.tenant_id
        or agent_release.agent_id != agent.id
        or agent_release.status != "published"
        or agent.published_release_id != agent_release.id
    ):
        raise WorkTaskSnapshotError("岗位数字员工发布版本与任务不匹配")
    if service_identity.status != "active":
        raise WorkTaskSnapshotError("岗位数字员工的服务身份未启用")
    if service_identity.agent_id != agent.id or service_identity.tenant_id != task.tenant_id:
        raise WorkTaskSnapshotError("服务身份与任务数字员工不匹配")
    if service_identity.business_role != task.owner_business_role:
        raise WorkTaskSnapshotError("服务身份岗位与任务岗位不匹配")

    skills = visible_published_skills(db, task.tenant_id, agent.id)
    sop_snapshots: list[dict[str, Any]] = []
    for skill in sorted(skills, key=lambda item: (item.skill_id, item.version)):
        try:
            expanded = expand_sop_for_execution(skill, skills)
        except SopNestingError as exc:
            raise WorkTaskSnapshotError(
                f"SOP {skill.skill_id} 无法生成启动快照: {exc}"
            ) from exc
        sop_snapshots.append(
            {
                "skill_id": skill.skill_id,
                "version": skill.version,
                "name": skill.name,
                "business_domain": skill.business_domain,
                "description": skill.description,
                "content_json": expanded.content_json,
                "content_digest": _digest(expanded.content_json),
            }
        )

    knowledge_snapshots: list[dict[str, Any]] = []
    visible_knowledge = visible_knowledge_base_versions(
        db, task.tenant_id, agent.id, include_inactive=False
    )
    for base_id, version in sorted(visible_knowledge.items()):
        knowledge_snapshots.append(
            {
                "knowledge_base_id": base_id,
                "knowledge_base_version_id": version.id,
                "version": version.version,
                "name": version.name,
                "status": version.status,
                "metadata_digest": _digest(version.metadata_json or {}),
            }
        )

    tool_snapshots: list[dict[str, Any]] = []
    for tool in sorted(
        visible_tool_rows(db, task.tenant_id, agent.id, include_inactive=False),
        key=lambda item: item.id,
    ):
        tool_snapshots.append(
            {
                "tool_id": tool.id,
                "name": tool.name,
                "display_name": tool.display_name or tool.name,
                "tool_type": tool.tool_type,
                "method": tool.method,
                "capability_scope": tool.capability_scope,
                "endpoint_fingerprint": _digest(str(tool.url or "")),
                "content_digest": tool_snapshot_digest(db, tool),
            }
        )

    safe_agent = {
        "agent_id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "persona_prompt": agent.persona_prompt,
        "rendered_persona": AgentIdentityPrompt.render(agent),
        "business_role": str((agent.metadata_json or {}).get("business_role") or ""),
        "harness_max_actions": agent.harness_max_actions,
        "profile_updated_at": agent.updated_at.isoformat(),
        "release_id": agent_release.id,
        "release_version": agent_release.version,
        "release_digest": agent_release.snapshot_digest,
        "release_published_at": agent_release.published_at.isoformat(),
    }
    safe_agent["profile_digest"] = _digest(safe_agent)

    safe_identity = {
        "service_identity_id": service_identity.id,
        "provider": service_identity.provider,
        "issuer": service_identity.issuer,
        "application_owner": service_identity.application_owner,
        "application_name": service_identity.application_name,
        "client_id_fingerprint": service_identity.client_id_fingerprint,
        "business_role": service_identity.business_role,
        "status": service_identity.status,
        "token_ttl_seconds": service_identity.token_ttl_seconds,
    }
    capability_snapshot = {
        "tool_digests": {
            str(item["tool_id"]): str(item["content_digest"])
            for item in tool_snapshots
        },
        "knowledge_version_by_base_id": {
            str(item["knowledge_base_id"]): str(item["knowledge_base_version_id"])
            for item in knowledge_snapshots
        },
        "sop_digests": {
            str(item["skill_id"]): str(item["content_digest"])
            for item in sop_snapshots
        },
    }
    payload = {
        "tenant_id": task.tenant_id,
        "task_id": task.id,
        "run_id": run.id,
        "agent": safe_agent,
        "sops": sop_snapshots,
        "knowledge": knowledge_snapshots,
        "tools": tool_snapshots,
        "capabilities": capability_snapshot,
        "service_identity": safe_identity,
    }
    return WorkTaskExecutionSnapshot(
        tenant_id=task.tenant_id,
        task_id=task.id,
        run_id=run.id,
        service_identity_id=service_identity.id,
        agent_id=agent.id,
        agent_snapshot_json=safe_agent,
        sop_snapshots_json=sop_snapshots,
        knowledge_snapshots_json=knowledge_snapshots,
        tool_snapshots_json=tool_snapshots,
        capability_snapshot_json=capability_snapshot,
        service_identity_snapshot_json=safe_identity,
        snapshot_digest=_digest(payload),
    )


def execution_snapshot_digest(snapshot: WorkTaskExecutionSnapshot) -> str:
    """Recompute the canonical digest without trusting stored digest columns."""

    return _digest(
        {
            "tenant_id": snapshot.tenant_id,
            "task_id": snapshot.task_id,
            "run_id": snapshot.run_id,
            "agent": snapshot.agent_snapshot_json,
            "sops": snapshot.sop_snapshots_json,
            "knowledge": snapshot.knowledge_snapshots_json,
            "tools": snapshot.tool_snapshots_json,
            "capabilities": snapshot.capability_snapshot_json,
            "service_identity": snapshot.service_identity_snapshot_json,
        }
    )


def _digest(value: Any) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
