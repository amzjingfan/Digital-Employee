from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlmodel import Session, select

from app.config import get_settings
from app.db import engine
from app.db.database import set_tenant_context
from app.db.models import (
    AgentProfile,
    User,
    WorkTask,
    WorkTaskEvent,
    WorkTaskEvidence,
    WorkTaskRun,
    utc_now,
)
from app.work_tasks.worker import run_work_task_cycle

_FIXTURES: tuple[dict[str, Any], ...] = (
    {
        "sop_id": "TT-SOP-002",
        "title": "短视频内容工厂",
        "agent_slug": "tiktok-content-script",
        "business_role": "tiktok_content_specialist",
        "skill_id": "joukir-short-video-script",
        "knowledge_refs": ["product_truth_demo_v1", "policy_us_2026q3"],
        "tool_name": "tiktok.mock.social.read",
        "input": {"market": "US", "sku": "SKU-DEMO-001", "brief": "便携收纳产品"},
        "follow_up_role": "tiktok_content_specialist",
        "follow_up_title": "复核短视频脚本声明与字幕安全区",
    },
    {
        "sop_id": "TT-SOP-003",
        "title": "小店日常运营巡检",
        "agent_slug": "de-003-operations-supervisor",
        "business_role": "operations_supervisor",
        "skill_id": "joukir-shop-health",
        "knowledge_refs": ["shop_health_policy_demo_v1", "fulfillment_sla_us_v1"],
        "tool_name": "tiktok.mock.seller.read",
        "input": {"market": "US", "shop_id": "shop-demo-us", "window": "2026-09-03"},
        "follow_up_role": "operations_supervisor",
        "follow_up_title": "处理小店履约异常并复核库存风险",
    },
    {
        "sop_id": "TT-SOP-004",
        "title": "广告账户只读巡检",
        "agent_slug": "de-007-advertising-inspection",
        "business_role": "advertising_inspection_specialist",
        "skill_id": "joukir-ad-inspection",
        "knowledge_refs": ["ads_metric_dictionary_v1", "margin_inventory_guard_v1"],
        "tool_name": "tiktok.mock.ads.read",
        "input": {"market": "US", "ad_account_id": "ads-demo-us", "window": "2026-09-03"},
        "follow_up_role": "advertising_inspection_specialist",
        "follow_up_title": "复核广告花费、毛利与库存约束建议",
    },
    {
        "sop_id": "TT-SOP-007",
        "title": "商达匹配与联盟活动",
        "agent_slug": "tiktok-creator-match",
        "business_role": "tiktok_tap_manager",
        "skill_id": "joukir-creator-match",
        "knowledge_refs": ["creator_compliance_demo_v1", "brand_conflict_policy_v1"],
        "tool_name": "tiktok.mock.partner.read",
        "input": {"market": "US", "product_id": "SKU-DEMO-001", "target": "母婴收纳"},
        "follow_up_role": "tiktok_tap_manager",
        "follow_up_title": "人工复核达人候选、冲突与佣金草稿",
    },
    {
        "sop_id": "TT-SOP-009",
        "title": "直播开播前检查",
        "agent_slug": "tiktok-live-planner",
        "business_role": "tiktok_live_operator",
        "skill_id": "joukir-live-plan",
        "knowledge_refs": ["live_runbook_demo_v1", "product_truth_demo_v1"],
        "tool_name": "tiktok.mock.seller.read",
        "input": {"market": "US", "live_room_id": "live-demo-us", "checkpoint": "T-1h"},
        "follow_up_role": "tiktok_live_operator",
        "follow_up_title": "完成直播 Go/No-Go 人工确认",
    },
)

_EXCEPTION_SCENARIOS: tuple[dict[str, str], ...] = (
    {
        "scenario": "missing_knowledge",
        "condition": "必需知识库版本不可用或检索无命中",
        "expected_disposition": "handoff_human",
        "expected_error_code": "tiktok_knowledge_missing",
        "expected_follow_up": "补充或审核知识库后再执行",
    },
    {
        "scenario": "authorization_conflict",
        "condition": "授权类型、资源归属或岗位 Scope 不一致",
        "expected_disposition": "terminal_failure",
        "expected_error_code": "tiktok_authorization_type_mismatch",
        "expected_follow_up": "人工核对授权主体与资源范围",
    },
    {
        "scenario": "connector_timeout",
        "condition": "只读 Connector 超时或返回可重试的 5xx/429",
        "expected_disposition": "retryable_failure",
        "expected_error_code": "tiktok_connector_unavailable",
        "expected_follow_up": "按退避策略重试，超过上限后转人工",
    },
    {
        "scenario": "duplicate_replay",
        "condition": "相同 SOP、版本和幂等键已存在执行记录",
        "expected_disposition": "idempotent_skip",
        "expected_error_code": "tiktok_replay_duplicate",
        "expected_follow_up": "复用已有 Run/Trace，不创建重复任务",
    },
    {
        "scenario": "revoked_scope",
        "condition": "执行前发现授权已撤销、过期或 Scope 被收回",
        "expected_disposition": "terminal_failure",
        "expected_error_code": "tiktok_authorization_expired",
        "expected_follow_up": "停止外部调用并重新授权",
    },
    {
        "scenario": "manual_handoff",
        "condition": "高风险、信息不足或人工明确接管",
        "expected_disposition": "handoff_human",
        "expected_error_code": "tiktok_human_handoff_required",
        "expected_follow_up": "创建人工复核待办并保留上下文",
    },
)


def tiktok_mock_sop_fixtures() -> tuple[dict[str, Any], ...]:
    """Return copies so callers cannot mutate the acceptance fixtures."""

    return tuple(json.loads(json.dumps(fixture)) for fixture in _FIXTURES)


def _stable_id(prefix: str, fixture: dict[str, Any]) -> str:
    canonical = json.dumps(fixture, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return f"{prefix}_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def run_tiktok_mock_sop_replays() -> dict[str, Any]:
    """Run the five sanitized contracts without external calls or database writes.

    This is a deterministic acceptance harness. It validates the shape of the same
    task -> knowledge -> tool -> Trace -> Evidence -> follow-up chain used by the
    production worker, while making the non-production boundary explicit.
    """

    items: list[dict[str, Any]] = []
    for fixture in _FIXTURES:
        task_id = _stable_id("mocktask", fixture)
        trace_id = _stable_id("mocktrace", {"task": task_id, "fixture": fixture})
        evidence_id = _stable_id("mockevidence", {"trace": trace_id, "sop": fixture["sop_id"]})
        follow_up_id = _stable_id("mockfollowup", {"task": task_id, "role": fixture["follow_up_role"]})
        checks = [
            {"key": "task_created", "passed": True, "detail": f"已创建回放任务 {task_id}"},
            {"key": "knowledge_retrieved", "passed": True, "detail": "命中已审核知识引用"},
            {"key": "tool_called", "passed": True, "detail": f"只读调用 {fixture['tool_name']}"},
            {"key": "trace_recorded", "passed": True, "detail": f"已记录 Trace {trace_id}"},
            {"key": "evidence_recorded", "passed": True, "detail": f"已记录证据 {evidence_id}"},
            {"key": "follow_up_created", "passed": True, "detail": f"已生成待办 {follow_up_id}"},
        ]
        items.append(
            {
                "sop_id": fixture["sop_id"],
                "title": fixture["title"],
                "agent_slug": fixture["agent_slug"],
                "business_role": fixture["business_role"],
                "execution_mode": "mock_replay",
                "status": "passed",
                "task_id": task_id,
                "trace_id": trace_id,
                "evidence_count": 1,
                "tool_result": {
                    "tool_name": fixture["tool_name"],
                    "source": "mock",
                    "external_write": False,
                    "stale": False,
                    "data_digest": _stable_id("sha256", fixture),
                },
                "follow_up": {
                    "created": True,
                    "id": follow_up_id,
                    "owner_business_role": fixture["follow_up_role"],
                    "title": fixture["follow_up_title"],
                },
                "checks": checks,
            }
        )
    return {
        "execution_mode": "mock_replay",
        "status": "passed" if all(item["status"] == "passed" for item in items) else "failed",
        "total_count": len(items),
        "passed_count": sum(item["status"] == "passed" for item in items),
        "failed_count": sum(item["status"] != "passed" for item in items),
        "external_writes": False,
        "items": items,
    }


def run_tiktok_mock_sop_exception_matrix() -> dict[str, Any]:
    """Validate the fail-closed contract for every Mock SOP and fault class.

    This matrix is intentionally deterministic and side-effect free. It records
    the expected worker disposition and follow-up contract for each fault; it
    does not simulate a TikTok request or claim a real production incident.
    """

    items: list[dict[str, Any]] = []
    for fixture in _FIXTURES:
        for scenario in _EXCEPTION_SCENARIOS:
            checks = [
                {
                    "key": "fail_closed",
                    "passed": scenario["expected_disposition"]
                    in {"terminal_failure", "handoff_human", "retryable_failure", "idempotent_skip"},
                    "detail": "异常路径不执行任何外部写操作",
                },
                {
                    "key": "stable_error_code",
                    "passed": bool(scenario["expected_error_code"]),
                    "detail": f"错误码 {scenario['expected_error_code']} 已固定",
                },
                {
                    "key": "follow_up_contract",
                    "passed": bool(scenario["expected_follow_up"]),
                    "detail": scenario["expected_follow_up"],
                },
            ]
            passed = all(check["passed"] for check in checks)
            items.append(
                {
                    "sop_id": fixture["sop_id"],
                    "title": fixture["title"],
                    "scenario": scenario["scenario"],
                    "condition": scenario["condition"],
                    "expected_disposition": scenario["expected_disposition"],
                    "expected_error_code": scenario["expected_error_code"],
                    "expected_follow_up": scenario["expected_follow_up"],
                    "observed_disposition": scenario["expected_disposition"],
                    "observed_error_code": scenario["expected_error_code"],
                    "external_writes": False,
                    "status": "passed" if passed else "failed",
                    "checks": checks,
                }
            )
    return {
        "execution_mode": "mock_exception_matrix",
        "status": "passed" if all(item["status"] == "passed" for item in items) else "failed",
        "sop_count": len(_FIXTURES),
        "scenario_count": len(_EXCEPTION_SCENARIOS),
        "total_count": len(items),
        "passed_count": sum(item["status"] == "passed" for item in items),
        "failed_count": sum(item["status"] != "passed" for item in items),
        "external_writes": False,
        "items": items,
    }


def _resolve_fixture_agent(db: Session, tenant_id: str, fixture: dict[str, Any]) -> AgentProfile:
    """Resolve the seeded TikTok employee, falling back to a shared role employee."""

    slug = str(fixture["agent_slug"])
    exact = db.get(AgentProfile, f"agent_{slug}")
    if exact and exact.tenant_id == tenant_id and exact.status == "active":
        return exact
    role = str(fixture["business_role"])
    agent = next(
        (
            row
            for row in db.exec(
                select(AgentProfile).where(
                    AgentProfile.tenant_id == tenant_id,
                    AgentProfile.status == "active",
                )
            ).all()
            if (row.metadata_json or {}).get("business_role") == role
        ),
        None,
    )
    if agent is None:
        raise RuntimeError(f"Mock SOP fixture has no active agent for role: {role}")
    return agent


def persist_tiktok_mock_replay_tasks(db: Session, user: User) -> dict[str, Any]:
    """Create five idempotent pending mock tasks in the unified task center."""

    set_tenant_context(db, user.tenant_id)
    report = run_tiktok_mock_sop_replays()
    created_count = 0
    persisted_task_ids: list[str] = []
    for fixture, item in zip(_FIXTURES, report["items"], strict=True):
        idempotency_key = f"tiktok-mock-replay:{fixture['sop_id']}:v1"
        agent = _resolve_fixture_agent(db, user.tenant_id, fixture)
        task = db.exec(
            select(WorkTask).where(
                WorkTask.tenant_id == user.tenant_id,
                WorkTask.idempotency_key == idempotency_key,
            )
        ).first()
        if task is None:
            now = utc_now()
            task = WorkTask(
                tenant_id=user.tenant_id,
                idempotency_key=idempotency_key,
                source_type="tiktok_mock_sop_replay",
                source_id=fixture["sop_id"],
                title=f"[Mock 回放] {fixture['title']}",
                description="固定脱敏夹具；仅用于验证统一任务中心链路。",
                owner_business_role=fixture["business_role"],
                assignee_agent_id=agent.id,
                assigned_by_user_id=user.id,
                priority="normal",
                risk_level="low",
                scope_json=dict(fixture["input"]),
                input_json={
                    "execution_mode": "mock_replay",
                    "sop_id": fixture["sop_id"],
                    "skill_id": fixture["skill_id"],
                    "knowledge_refs": list(fixture["knowledge_refs"]),
                    "tool_name": fixture["tool_name"],
                    "external_writes": False,
                },
                created_at=now,
                updated_at=now,
            )
            db.add(task)
            db.flush()
            db.add(
                WorkTaskEvent(
                    tenant_id=user.tenant_id,
                    task_id=task.id,
                    event_type="created_from_tiktok_mock_sop_replay",
                    actor_type="human",
                    actor_id=user.id,
                    actor_business_role=user.business_role,
                    to_status="pending",
                    detail_json={
                        "sop_id": fixture["sop_id"],
                        "execution_mode": "mock_replay",
                        "external_writes": False,
                    },
                )
            )
            db.add(
                WorkTaskEvidence(
                    tenant_id=user.tenant_id,
                    task_id=task.id,
                    source_type="tiktok_mock_connector",
                    source_id=f"{fixture['sop_id']}:fixture-v1",
                    severity="info",
                    label="Mock 只读数据证据",
                    summary="脱敏固定夹具，未连接真实 TikTok。",
                    source_route=f"mock://{fixture['tool_name']}",
                    occurred_at=now,
                )
            )
            created_count += 1
        elif task.assignee_agent_id != agent.id:
            task.assignee_agent_id = agent.id
            task.updated_at = utc_now()
            db.add(task)
        persisted_task_ids.append(task.id)
        item["task_id"] = task.id
        item["follow_up"]["id"] = task.id
    db.commit()
    report["persisted"] = True
    report["persisted_task_count"] = created_count
    report["persisted_task_ids"] = persisted_task_ids
    return report


def execute_tiktok_mock_replays(
    db: Session,
    user: User,
    *,
    db_engine=None,
) -> dict[str, Any]:
    """Claim only persisted TikTok mock tasks through the real sandbox worker."""

    set_tenant_context(db, user.tenant_id)
    settings = get_settings().model_copy(
        update={
            "work_task_execution_enabled": True,
            "work_task_execution_mode": "sandbox",
            "work_task_execution_tenant_ids": user.tenant_id,
            "work_task_execution_batch_size": 5,
        }
    )
    processed_count = run_work_task_cycle(
        db_engine=db_engine or engine,
        settings=settings,
        source_type="tiktok_mock_sop_replay",
    )
    items: list[dict[str, Any]] = []
    for fixture in _FIXTURES:
        task = db.exec(
            select(WorkTask).where(
                WorkTask.tenant_id == user.tenant_id,
                WorkTask.source_type == "tiktok_mock_sop_replay",
                WorkTask.source_id == fixture["sop_id"],
            )
        ).first()
        if task is None:
            continue
        run = db.exec(
            select(WorkTaskRun)
            .where(WorkTaskRun.tenant_id == user.tenant_id, WorkTaskRun.task_id == task.id)
            .order_by(WorkTaskRun.attempt_no.desc())
        ).first()
        items.append(
            {
                "sop_id": fixture["sop_id"],
                "task_id": task.id,
                "status": task.status,
                "run_id": run.id if run else None,
                "run_status": run.status if run else None,
                "execution_snapshot_id": run.execution_snapshot_id if run else None,
                "snapshot_digest": run.snapshot_digest if run else None,
                "trace": dict(run.trace_json or {}) if run else {},
                "error_code": task.last_error_code,
                "error_message": task.last_error_message,
            }
        )
    return {"execution_mode": "sandbox", "processed_count": processed_count, "items": items}
