from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlmodel import Session, select

from app.agents.branching import agent_private_metadata, ensure_agent_private_knowledge_branch
from app.agents.releases import (
    AgentReleaseError,
    preflight_agent_release,
    publish_agent_release,
)
from app.config import get_settings
from app.db.models import (
    AgentKnowledgeBranch,
    AgentProfile,
    AgentResourceBinding,
    AgentServiceIdentity,
    BusinessResource,
    BusinessResourceScope,
    ExternalAuthorization,
    GeneralSkill,
    KnowledgeBase,
    KnowledgeBaseVersion,
    OrganizationMembership,
    OrganizationUnit,
    Skill,
    SkillVersion,
    TikTokShadowRun,
    Tool,
    User,
    WorkTask,
    utc_now,
)
from app.security.business_roles import BUSINESS_ROLE_BY_KEY, BusinessRoleDefinition
from app.security.permissions import ensure_tenant_admin, is_admin_user
from app.tiktok.release_gate import verify_tiktok_live_write_disabled
from app.tiktok.schema import (
    OrganizationUnitRead,
    TikTokAgentReleasePreflight,
    TikTokAgentReleasePreflightItem,
    TikTokAgentReleasePublishResult,
    TikTokAssetBootstrapResponse,
    TikTokAuthorizationRead,
    TikTokBootstrapResponse,
    TikTokM2MVerificationResponse,
    TikTokOverview,
    TikTokProductionGateRead,
    TikTokProductionReadiness,
    TikTokResourceRead,
    TikTokRoleRead,
)
from app.work_tasks.m2m import (
    ServiceIdentityError,
    authenticate_service_identity,
    clear_service_token_cache,
)


def _configured_m2m_client_id(settings, credential_ref: str, fallback: str) -> str:
    """Use the client id paired with the configured Secret Store record."""

    if not settings.work_task_m2m_secret_file.strip():
        return fallback
    try:
        payload = json.loads(
            Path(settings.work_task_m2m_secret_file).expanduser().resolve().read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError):
        return fallback
    records = payload.get("credentials") if isinstance(payload, dict) else None
    row = records.get(credential_ref) if isinstance(records, dict) else None
    configured = str(row.get("client_id") or "").strip() if isinstance(row, dict) else ""
    return configured or fallback

TIKTOK_ROLE_KEYS: tuple[str, ...] = (
    "tiktok_bd_specialist",
    "tiktok_content_specialist",
    "tiktok_shop_operator",
    "tiktok_media_buyer",
    "tiktok_tap_manager",
    "tiktok_live_operator",
)

TIKTOK_DEPARTMENTS: tuple[tuple[str, str, str], ...] = (
    ("bd", "BD 部门", "tiktok_bd_specialist"),
    ("content", "短视频部门", "tiktok_content_specialist"),
    ("shop", "小店运营部门", "tiktok_shop_operator"),
    ("media", "投流部门", "tiktok_media_buyer"),
    ("tap", "TAP 机构", "tiktok_tap_manager"),
    ("live", "直播部门", "tiktok_live_operator"),
)

TIKTOK_RESOURCE_TYPES = {
    "store",
    "ad_account",
    "creator_account",
    "partner_account",
    "social_account",
    "live_room",
}
TIKTOK_TASK_STATUSES = ("pending", "in_progress", "review", "completed")

TIKTOK_SKILL_CATALOG: tuple[tuple[str, str, str], ...] = (
    ("joukir-tiktok-account-audit", "账号审计", "验证账号、采样内容、记录证据和数据缺口。"),
    ("joukir-product-truth", "产品事实账本", "建立 SKU 事实、可用声明、禁用声明和证据缺口。"),
    ("joukir-content-angle", "内容角度", "基于目标、受众和事实产生 2-4 个创意角度。"),
    ("joukir-short-video-script", "短视频脚本", "输出 Hook、问题、演示、证据、CTA 和镜头提示。"),
    ("joukir-storyboard", "短视频分镜", "输出稳定镜号、景别、运动、声音和剪辑目的。"),
    ("joukir-creative-qc", "创意质检", "检查声明、版权、品牌、字幕、安全区和移动端可读性。"),
    ("joukir-shop-health", "小店健康巡检", "检查店铺、商品、订单、履约、售后和库存异常。"),
    ("joukir-ad-inspection", "广告账户巡检", "检查数据口径、账户、创意疲劳、归因和预算节奏。"),
    ("joukir-creator-profile", "达人画像", "建立有来源、样本窗和限制的达人画像。"),
    ("joukir-creator-match", "商达匹配", "计算内容、受众、市场、履约、品牌和预算匹配。"),
    ("joukir-live-plan", "直播计划", "生成场次计划、商品顺序、话术、检查和应急预案。"),
    ("joukir-policy-check", "政策检查", "根据市场、主体、生效时间和规则版本做门禁。"),
)

TIKTOK_AGENT_CATALOG: tuple[tuple[str, str, str, str], ...] = (
    ("tiktok-bd-due-diligence", "TikTok 商家入驻尽调专员", "tiktok_bd_specialist", "tiktok-bd"),
    ("tiktok-content-script", "TikTok Hook 与脚本专员", "tiktok_content_specialist", "tiktok-content"),
    ("tiktok-creator-authorization", "TikTok 达人授权与入驻专员", "tiktok_tap_manager", "tiktok-tap"),
    ("tiktok-creator-match", "TikTok 商达匹配专员", "tiktok_tap_manager", "tiktok-tap"),
    ("tiktok-live-planner", "TikTok 直播策划专员", "tiktok_live_operator", "tiktok-live"),
)

# 每个生产岗位只拿到完成岗位 SOP 所必需的能力。这里的白名单同时作为
# 资产种子和后续对账的唯一事实来源，避免新资产被误绑定给所有岗位。
TIKTOK_AGENT_SKILLS: dict[str, frozenset[str]] = {
    "tiktok-bd-due-diligence": frozenset(
        {"joukir-tiktok-account-audit", "joukir-product-truth", "joukir-policy-check"}
    ),
    "tiktok-content-script": frozenset(
        {
            "joukir-product-truth",
            "joukir-content-angle",
            "joukir-short-video-script",
            "joukir-storyboard",
            "joukir-creative-qc",
            "joukir-policy-check",
        }
    ),
    "tiktok-creator-authorization": frozenset(
        {"joukir-creator-profile", "joukir-product-truth", "joukir-policy-check"}
    ),
    "tiktok-creator-match": frozenset(
        {"joukir-creator-profile", "joukir-creator-match", "joukir-policy-check"}
    ),
    "tiktok-live-planner": frozenset(
        {"joukir-product-truth", "joukir-live-plan", "joukir-creative-qc", "joukir-policy-check"}
    ),
}

TIKTOK_AGENT_TOOLS: dict[str, frozenset[str]] = {
    "tiktok-bd-due-diligence": frozenset(
        {"tiktok.mock.seller.read", "tiktok.mock.partner.read"}
    ),
    "tiktok-content-script": frozenset(
        {"tiktok.mock.seller.read", "tiktok.mock.social.read"}
    ),
    "tiktok-creator-authorization": frozenset(
        {"tiktok.mock.creator.read", "tiktok.mock.partner.read"}
    ),
    "tiktok-creator-match": frozenset(
        {"tiktok.mock.creator.read", "tiktok.mock.partner.read"}
    ),
    "tiktok-live-planner": frozenset(
        {"tiktok.mock.seller.read", "tiktok.mock.social.read"}
    ),
}

TIKTOK_CONNECTOR_TOOLS: tuple[tuple[str, str], ...] = (
    ("tiktok.mock.seller.read", "TikTok Seller 只读查询"),
    ("tiktok.mock.creator.read", "TikTok Creator 只读查询"),
    ("tiktok.mock.partner.read", "TikTok Partner 只读查询"),
    ("tiktok.mock.ads.read", "TikTok Ads 只读查询"),
    ("tiktok.mock.social.read", "TikTok 账号只读查询"),
)


def _role_read(role: BusinessRoleDefinition) -> TikTokRoleRead:
    return TikTokRoleRead(
        key=role.key,
        label=role.label,
        casdoor_group=role.casdoor_group,
        description=role.description,
    )


def _unit_read(unit: OrganizationUnit) -> OrganizationUnitRead:
    metadata = unit.metadata_json or {}
    return OrganizationUnitRead(
        id=unit.id,
        parent_id=unit.parent_id,
        unit_type=unit.unit_type,
        code=unit.code,
        name=unit.name,
        status=unit.status,
        revision=unit.revision,
        role_key=str(metadata.get("role_key")) if metadata.get("role_key") else None,
    )


def _tiktok_roles() -> list[TikTokRoleRead]:
    return [_role_read(BUSINESS_ROLE_BY_KEY[key]) for key in TIKTOK_ROLE_KEYS]


def bootstrap_tiktok_organization(db: Session, user: User) -> TikTokBootstrapResponse:
    """Create the approved TikTok business-unit template once per tenant."""

    ensure_tenant_admin(user.tenant_id, user)
    root = db.exec(
        select(OrganizationUnit).where(
            OrganizationUnit.tenant_id == user.tenant_id,
            OrganizationUnit.code == "tiktok",
        )
    ).first()
    created_count = 0
    if root is None:
        root = OrganizationUnit(
            tenant_id=user.tenant_id,
            unit_type="business_unit",
            code="tiktok",
            name="TikTok 事业部",
            created_by_user_id=user.id,
            metadata_json={"provider": "tiktok", "template_version": "v1"},
        )
        db.add(root)
        db.flush()
        created_count += 1
    elif root.unit_type != "business_unit":
        raise HTTPException(status_code=409, detail="TikTok organization code is already in use")

    departments: list[OrganizationUnit] = []
    for code, name, role_key in TIKTOK_DEPARTMENTS:
        department_code = f"tiktok-{code}"
        department = db.exec(
            select(OrganizationUnit).where(
                OrganizationUnit.tenant_id == user.tenant_id,
                OrganizationUnit.code == department_code,
            )
        ).first()
        if department is None:
            department = OrganizationUnit(
                tenant_id=user.tenant_id,
                parent_id=root.id,
                unit_type="department",
                code=department_code,
                name=name,
                created_by_user_id=user.id,
                metadata_json={
                    "provider": "tiktok",
                    "role_key": role_key,
                    "template_version": "v1",
                },
            )
            db.add(department)
            created_count += 1
        elif department.parent_id != root.id:
            raise HTTPException(
                status_code=409,
                detail=f"TikTok department code is already linked elsewhere: {department_code}",
            )
        departments.append(department)
    db.commit()
    db.refresh(root)
    for department in departments:
        db.refresh(department)
    return TikTokBootstrapResponse(
        created_count=created_count,
        root=_unit_read(root),
        departments=[_unit_read(item) for item in departments],
        roles=_tiktok_roles(),
    )


def _is_tiktok_resource(resource: BusinessResource) -> bool:
    metadata = resource.metadata_json or {}
    return resource.resource_type in TIKTOK_RESOURCE_TYPES and (
        resource.resource_type != "store" or metadata.get("platform") == "tiktok"
    )


def _visible_resources(db: Session, user: User) -> list[TikTokResourceRead]:
    rows = db.exec(
        select(BusinessResource).where(
            BusinessResource.tenant_id == user.tenant_id,
            BusinessResource.status == "active",
        )
    ).all()
    rows = [row for row in rows if _is_tiktok_resource(row)]
    if not (is_admin_user(user) or user.business_role == "operations_supervisor"):
        allowed_ids = set(
            db.exec(
                select(BusinessResourceScope.resource_id).where(
                    BusinessResourceScope.tenant_id == user.tenant_id,
                    BusinessResourceScope.business_role == user.business_role,
                    BusinessResourceScope.access_level.in_(("viewer", "operator")),
                )
            ).all()
        )
        rows = [row for row in rows if row.id in allowed_ids]
    result: list[TikTokResourceRead] = []
    for row in sorted(rows, key=lambda item: (item.resource_type, item.name)):
        access_level = "operator" if is_admin_user(user) or user.business_role == "operations_supervisor" else "viewer"
        if access_level == "viewer":
            access_level = db.exec(
                select(BusinessResourceScope.access_level).where(
                    BusinessResourceScope.tenant_id == user.tenant_id,
                    BusinessResourceScope.resource_id == row.id,
                    BusinessResourceScope.business_role == user.business_role,
                )
            ).first() or "viewer"
        result.append(
            TikTokResourceRead(
                id=row.id,
                resource_type=row.resource_type,
                code=row.code,
                name=row.name,
                status=row.status,
                market=str((row.metadata_json or {}).get("market"))
                if (row.metadata_json or {}).get("market")
                else None,
                access_level=access_level,
            )
        )
    return result


def _visible_tasks(db: Session, user: User) -> dict[str, int]:
    rows = db.exec(select(WorkTask).where(WorkTask.tenant_id == user.tenant_id)).all()
    if not (is_admin_user(user) or user.business_role == "operations_supervisor"):
        rows = [row for row in rows if row.owner_business_role == user.business_role]
    rows = [
        row
        for row in rows
        if row.source_type.startswith("tiktok")
        or (row.scope_json or {}).get("platform") == "tiktok"
    ]
    return {status: sum(row.status == status for row in rows) for status in TIKTOK_TASK_STATUSES}


def _authorizations(db: Session, user: User) -> list[TikTokAuthorizationRead]:
    rows = db.exec(
        select(ExternalAuthorization).where(
            ExternalAuthorization.tenant_id == user.tenant_id,
            ExternalAuthorization.provider == "tiktok",
        )
    ).all()
    return [
        TikTokAuthorizationRead(
            id=row.id,
            authorization_type=row.authorization_type,
            subject_id=row.subject_id,
            resource_id=row.resource_id,
            scopes=list(row.scopes_json or []),
            status=row.status,
            expires_at=row.expires_at,
        )
        for row in sorted(rows, key=lambda item: (item.authorization_type, item.subject_id))
    ]


def get_tiktok_overview(db: Session, user: User) -> TikTokOverview:
    root = db.exec(
        select(OrganizationUnit).where(
            OrganizationUnit.tenant_id == user.tenant_id,
            OrganizationUnit.code == "tiktok",
            OrganizationUnit.unit_type == "business_unit",
        )
    ).first()
    departments = []
    if root is not None:
        departments = db.exec(
            select(OrganizationUnit).where(
                OrganizationUnit.tenant_id == user.tenant_id,
                OrganizationUnit.parent_id == root.id,
                OrganizationUnit.status == "active",
            ).order_by(OrganizationUnit.code)
        ).all()
    return TikTokOverview(
        root=_unit_read(root) if root else None,
        departments=[_unit_read(item) for item in departments],
        roles=_tiktok_roles(),
        resources=_visible_resources(db, user),
        authorizations=_authorizations(db, user),
        task_counts=_visible_tasks(db, user),
    )


def get_tiktok_production_readiness(
    db: Session,
    user: User,
) -> TikTokProductionReadiness:
    """Evaluate local production gates without treating Mock data as Live."""

    ensure_tenant_admin(user.tenant_id, user)
    settings = get_settings()
    gates: list[TikTokProductionGateRead] = []

    management_configured = bool(
        settings.casdoor_management_endpoint.strip()
        and settings.casdoor_management_client_id.strip()
        and settings.casdoor_management_client_secret
    )
    gates.append(
        TikTokProductionGateRead(
            key="casdoor_management",
            label="Casdoor 管理同步",
            status="passed" if settings.casdoor_management_enabled and management_configured else "blocked",
            detail=(
                "已启用独立 Management Client 和周期对账"
                if settings.casdoor_management_enabled and management_configured
                else "需要启用独立 Casdoor Management Client 并补齐配置"
            ),
        )
    )

    connector_mode_ready = settings.tiktok_connector_mode == "live"
    gates.append(
        TikTokProductionGateRead(
            key="tiktok_connector_mode",
            label="TikTok 连接器执行模式",
            status="passed" if connector_mode_ready else "blocked",
            detail=(
                "官方只读连接器已显式启用 live 模式"
                if connector_mode_ready
                else "生产就绪要求 tiktok_connector_mode=live；mock/replay 仅可用于本地或回放验证"
            ),
        )
    )

    official_configured = bool(
        settings.tiktok_official_enabled
        and settings.tiktok_app_key.strip()
        and settings.tiktok_app_secret
        and settings.tiktok_service_id.strip()
        and settings.tiktok_redirect_uri.strip()
        and settings.tiktok_token_store_file.strip()
    )
    official_authorization_count = sum(
        (row.metadata_json or {}).get("authorization_flow") == "official"
        for row in db.exec(
            select(ExternalAuthorization).where(
                ExternalAuthorization.tenant_id == user.tenant_id,
                ExternalAuthorization.provider == "tiktok",
                ExternalAuthorization.status == "active",
            )
        ).all()
    )
    if not official_configured:
        official_status = "blocked"
        official_detail = "TikTok 官方 App（含 App Key/Secret）或独立 Service ID、回调、Token Store 尚未配置"
    elif official_authorization_count == 0:
        official_status = "waiting"
        official_detail = "配置已就绪，等待至少一个真实 TikTok 官方授权"
    else:
        official_status = "passed"
        official_detail = f"已有 {official_authorization_count} 条有效官方授权"
    gates.append(
        TikTokProductionGateRead(
            key="tiktok_official_authorization",
            label="TikTok 官方授权",
            status=official_status,
            detail=official_detail,
        )
    )

    agent_names = [name for _, name, _, _ in TIKTOK_AGENT_CATALOG]
    published_count = len(
        db.exec(
            select(AgentProfile).where(
                AgentProfile.tenant_id == user.tenant_id,
                AgentProfile.name.in_(agent_names),
                AgentProfile.release_state == "published",
                AgentProfile.published_release_id.is_not(None),
            )
        ).all()
    )
    gates.append(
        TikTokProductionGateRead(
            key="agent_releases",
            label="TikTok AgentRelease",
            status="passed" if published_count == len(agent_names) else "waiting",
            detail=(
                "五个生产 AgentRelease 均已发布"
                if published_count == len(agent_names)
                else f"已发布 {published_count}/{len(agent_names)}，等待业务负责人审核发布"
            ),
        )
    )

    shadow_run = db.exec(
        select(TikTokShadowRun)
        .where(TikTokShadowRun.tenant_id == user.tenant_id)
        .order_by(TikTokShadowRun.started_at.desc())
    ).first()
    if shadow_run is None:
        shadow_status = "waiting"
        shadow_detail = "尚未启动 14 天只读影子运行"
    elif shadow_run.status == "completed" and shadow_run.ends_at - shadow_run.started_at >= timedelta(days=14):
        shadow_status = "passed"
        shadow_detail = "14 天只读影子运行已完成"
    elif shadow_run.status == "running":
        remaining_days = max(0, (shadow_run.ends_at - utc_now()).total_seconds() / 86400)
        shadow_status = "waiting"
        shadow_detail = f"影子运行进行中，预计还需 {remaining_days:.1f} 天"
    else:
        shadow_status = "blocked"
        shadow_detail = f"影子运行状态为 {shadow_run.status}，需要重新检查"
    gates.append(
        TikTokProductionGateRead(
            key="shadow_run",
            label="14 天影子运行",
            status=shadow_status,
            detail=shadow_detail,
        )
    )

    live_write_audit = verify_tiktok_live_write_disabled()
    live_write_issues = list(live_write_audit["issues"])
    gates.append(
        TikTokProductionGateRead(
            key="external_writes",
            label="外部写入安全门禁",
            status="passed" if live_write_audit["ok"] else "blocked",
            detail=(
                "P3-A Live 写入表面审计通过："
                f"{live_write_audit['route_count']} 条冻结路由、"
                f"{live_write_audit['skill_count']} 个只读 Skill"
                if live_write_audit["ok"]
                else "P3-A Live 写入表面审计阻断：" + "; ".join(live_write_issues[:3])
            ),
        )
    )
    return TikTokProductionReadiness(
        ready=all(gate.status == "passed" for gate in gates),
        evaluated_at=utc_now(),
        gates=gates,
    )


class TikTokAgentReleaseGateError(AgentReleaseError):
    def __init__(self, checks: list[TikTokAgentReleasePreflightItem]) -> None:
        self.checks = checks
        super().__init__("TikTok AgentRelease 预检未通过")


def get_tiktok_agent_release_preflight(
    db: Session,
    user: User,
) -> TikTokAgentReleasePreflight:
    """Evaluate all five TikTok production releases without publishing anything."""

    ensure_tenant_admin(user.tenant_id, user)
    names = {name: (slug, role) for slug, name, role, _department in TIKTOK_AGENT_CATALOG}
    agents = {
        row.name: row
        for row in db.exec(
            select(AgentProfile).where(
                AgentProfile.tenant_id == user.tenant_id,
                AgentProfile.name.in_(tuple(names)),
            )
        ).all()
    }
    items: list[TikTokAgentReleasePreflightItem] = []
    for name, (slug, business_role) in names.items():
        agent = agents.get(name)
        if agent is None:
            items.append(
                TikTokAgentReleasePreflightItem(
                    slug=slug,
                    name=name,
                    business_role=business_role,
                    ready=False,
                    error="数字员工尚未初始化",
                )
            )
            continue
        result = preflight_agent_release(db, agent)
        items.append(
            TikTokAgentReleasePreflightItem(
                slug=slug,
                name=name,
                business_role=business_role,
                agent_id=agent.id,
                release_state=result["release_state"],
                ready=bool(result["ready"]),
                error=result["error"],
                snapshot_digest=result["snapshot_digest"],
            )
        )
    return TikTokAgentReleasePreflight(
        tenant_id=user.tenant_id,
        ready=all(item.ready for item in items) and len(items) == len(TIKTOK_AGENT_CATALOG),
        evaluated_at=utc_now(),
        items=items,
    )


def publish_tiktok_agent_releases(
    db: Session,
    user: User,
    approval_reference: str,
) -> TikTokAgentReleasePublishResult:
    """Publish the five releases atomically after a fresh, complete preflight."""

    ensure_tenant_admin(user.tenant_id, user)
    reference = approval_reference.strip()
    if len(reference) < 3:
        raise AgentReleaseError("审批编号至少需要 3 个字符")
    preflight = get_tiktok_agent_release_preflight(db, user)
    if not preflight.ready:
        raise TikTokAgentReleaseGateError(preflight.items)
    reason = f"业务负责人审批 {reference}: TikTok 生产基线发布"
    releases: list[dict[str, object]] = []
    try:
        for item in preflight.items:
            release = publish_agent_release(
                db,
                tenant_id=user.tenant_id,
                agent_id=str(item.agent_id),
                actor=user,
                reason=reason,
                commit=False,
            )
            releases.append(
                {
                    "agent_id": release.agent_id,
                    "release_id": release.id,
                    "version": release.version,
                    "snapshot_digest": release.snapshot_digest,
                }
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return TikTokAgentReleasePublishResult(
        tenant_id=user.tenant_id,
        approval_reference=reference,
        published_count=len(releases),
        releases=releases,
    )


def verify_tiktok_m2m_identities(
    db: Session,
    user: User,
) -> TikTokM2MVerificationResponse:
    """Exchange and validate each TikTok production M2M token without side effects."""

    ensure_tenant_admin(user.tenant_id, user)
    agent_ids = {f"agent_{slug}" for slug, _name, _role, _department in TIKTOK_AGENT_CATALOG}
    identities = {
        identity.agent_id: identity
        for identity in db.exec(
            select(AgentServiceIdentity).where(
                AgentServiceIdentity.tenant_id == user.tenant_id,
                AgentServiceIdentity.agent_id.in_(tuple(agent_ids)),
            )
        ).all()
    }
    settings = get_settings()
    items: list[dict[str, object]] = []
    for agent_id in sorted(agent_ids):
        identity = identities.get(agent_id)
        if identity is None:
            items.append(
                {
                    "agent_id": agent_id,
                    "status": "failed",
                    "error_code": "service_identity_unavailable",
                }
            )
            continue
        clear_service_token_cache(identity.id)
        try:
            receipt = authenticate_service_identity(identity, settings)
        except ServiceIdentityError as exc:
            identity.last_error_code = exc.code
            identity.updated_at = utc_now()
            db.add(identity)
            items.append(
                {
                    "agent_id": agent_id,
                    "application": f"{identity.application_owner}/{identity.application_name}",
                    "status": "failed",
                    "error_code": exc.code,
                }
            )
            continue
        identity.last_verified_at = utc_now()
        identity.last_verified_subject = receipt.subject[:255]
        identity.last_error_code = None
        identity.updated_at = utc_now()
        db.add(identity)
        items.append(
            {
                "agent_id": agent_id,
                "application": f"{identity.application_owner}/{identity.application_name}",
                "status": "verified",
                "subject": receipt.subject,
                "expires_at": receipt.expires_at,
            }
        )
    db.commit()
    verified_count = sum(item["status"] == "verified" for item in items)
    return TikTokM2MVerificationResponse(
        tenant_id=user.tenant_id,
        verified_count=verified_count,
        failed_count=len(items) - verified_count,
        items=items,
    )


def reconcile_casdoor_membership(
    db: Session, user: User, *, source: str = "casdoor"
) -> OrganizationMembership | None:
    """Reconcile one OIDC user to at most one active TikTok primary department."""

    if user.business_role not in TIKTOK_ROLE_KEYS:
        return None
    units = db.exec(
        select(OrganizationUnit).where(
            OrganizationUnit.tenant_id == user.tenant_id,
            OrganizationUnit.unit_type == "department",
            OrganizationUnit.status == "active",
        )
    ).all()
    target = next(
        (
            unit
            for unit in units
            if (unit.metadata_json or {}).get("role_key") == user.business_role
        ),
        None,
    )
    if target is None:
        return None
    memberships = db.exec(
        select(OrganizationMembership).where(
            OrganizationMembership.tenant_id == user.tenant_id,
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.membership_type == "primary",
        )
    ).all()
    current = memberships[0] if memberships else None
    if current is None:
        current = OrganizationMembership(
            tenant_id=user.tenant_id,
            unit_id=target.id,
            user_id=user.id,
            business_role=user.business_role,
            membership_type="primary",
            source=source,
        )
    else:
        current.unit_id = target.id
        current.business_role = user.business_role
        current.source = source
        current.status = "active"
        current.synced_at = utc_now()
        current.updated_at = utc_now()
    db.add(current)
    db.flush()
    return current


def reconcile_casdoor_memberships(db: Session, admin: User, *, source: str = "casdoor") -> int:
    """Reconcile all TikTok-role users in one tenant for existing accounts."""

    ensure_tenant_admin(admin.tenant_id, admin)
    users = db.exec(select(User).where(User.tenant_id == admin.tenant_id)).all()
    reconciled_count = 0
    for user in users:
        if reconcile_casdoor_membership(db, user, source=source) is not None:
            reconciled_count += 1
    db.commit()
    return reconciled_count


def _content_digest(value: dict[str, object]) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _skill_content(skill_id: str, name: str, description: str) -> dict[str, object]:
    return {
        "skill_id": skill_id,
        "name": name,
        "version": "1.0.0",
        "business_domain": "tiktok",
        "description": description,
        "capability_scope": "sop_specific",
        "trigger_intents": [name],
        "goal": [description],
        "required_info": ["tenant_id", "task_scope"],
        "response_rules": ["缺数据必须标记 degraded=true，不得把推断写成事实。", "只读阶段不得执行外部写操作。"],
        "nodes": [
            {
                "node_id": "collect_input",
                "type": "collect_info",
                "name": "收集受控输入",
                "instruction": description,
                "expected_user_info": ["tenant_id", "task_scope"],
                "allowed_actions": ["continue_flow", "answer_user", "handoff_human"],
            }
        ],
        "edges": [],
        "start_node_id": "collect_input",
        "terminal_node_ids": ["collect_input"],
        "interruption_policy": {"unrelated_business": "保存任务状态后转入对应岗位队列。"},
    }


def _ensure_binding(
    db: Session,
    *,
    tenant_id: str,
    agent_id: str,
    resource_type: str,
    resource_id: str,
    digest: str,
) -> bool:
    row = db.exec(
        select(AgentResourceBinding).where(
            AgentResourceBinding.tenant_id == tenant_id,
            AgentResourceBinding.agent_id == agent_id,
            AgentResourceBinding.resource_type == resource_type,
            AgentResourceBinding.resource_id == resource_id,
        )
    ).first()
    if row is not None:
        if (row.metadata_json or {}).get("content_digest") != digest:
            raise HTTPException(status_code=409, detail=f"TikTok binding drift detected: {resource_id}")
        if row.status != "active":
            row.status = "active"
            row.updated_at = utc_now()
            db.add(row)
            return True
        return False
    db.add(
        AgentResourceBinding(
            tenant_id=tenant_id,
            agent_id=agent_id,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json={
                "review_status": "approved",
                "content_digest": digest,
                "version": "1.0.0",
                "seed_origin": "joukir-tiktok-p3a",
                **agent_private_metadata(agent_id, {}),
            },
        )
    )
    return True


def bootstrap_tiktok_assets(db: Session, user: User) -> TikTokAssetBootstrapResponse:
    """Idempotently install the reviewed P3-A skills, tools, knowledge and agents."""

    ensure_tenant_admin(user.tenant_id, user)
    tenant_id = user.tenant_id
    created_count = 0
    skill_rows: list[Skill] = []
    general_skill_rows: list[GeneralSkill] = []
    for skill_id, name, description in TIKTOK_SKILL_CATALOG:
        content = _skill_content(skill_id, name, description)
        digest = _content_digest(content)
        skill = db.exec(
            select(Skill).where(Skill.tenant_id == tenant_id, Skill.skill_id == skill_id)
        ).first()
        if skill is None:
            skill = Skill(
                id=f"skill_{skill_id.removeprefix('joukir-')}",
                tenant_id=tenant_id,
                skill_id=skill_id,
                version="1.0.0",
                name=name,
                business_domain="tiktok",
                description=description,
                content_json=content,
                status="published",
            )
            db.add(skill)
            created_count += 1
        elif (skill.content_json or {}).get("skill_id") != skill_id:
            raise HTTPException(status_code=409, detail=f"TikTok Skill content drift detected: {skill_id}")
        version = db.exec(
            select(SkillVersion).where(
                SkillVersion.tenant_id == tenant_id,
                SkillVersion.skill_id == skill_id,
                SkillVersion.version == "1.0.0",
            )
        ).first()
        if version is None:
            db.add(
                SkillVersion(
                    id=f"skillver_{skill_id.removeprefix('joukir-')}_v1",
                    tenant_id=tenant_id,
                    skill_id=skill_id,
                    version="1.0.0",
                    name=name,
                    business_domain="tiktok",
                    description=description,
                    content_json=content,
                    status="published",
                )
            )
            created_count += 1
        general = db.exec(
            select(GeneralSkill).where(GeneralSkill.tenant_id == tenant_id, GeneralSkill.slug == skill_id)
        ).first()
        if general is None:
            general = GeneralSkill(
                id=f"genskill_{skill_id.removeprefix('joukir-')}",
                tenant_id=tenant_id,
                slug=skill_id,
                name=name,
                description=description,
                homepage="internal://skills/joukir-tiktok-pack",
                skill_markdown=f"# {name}\n\n{description}\n\n只读执行；缺少证据时输出 degraded=true。",
                metadata_json={"source": "joukir-tiktok-pack", "license": "MIT-methods-only", "review_status": "approved", "content_digest": digest},
                status="published",
                capability_scope="sop_specific",
            )
            db.add(general)
            created_count += 1
        elif (general.metadata_json or {}).get("content_digest") != digest:
            raise HTTPException(status_code=409, detail=f"TikTok GeneralSkill drift detected: {skill_id}")
        skill_rows.append(skill)
        general_skill_rows.append(general)

    knowledge = db.exec(
        select(KnowledgeBase).where(KnowledgeBase.tenant_id == tenant_id, KnowledgeBase.name == "TikTok 生产知识库")
    ).first()
    if knowledge is None:
        knowledge = KnowledgeBase(
            id="kb_tiktok_production",
            tenant_id=tenant_id,
            name="TikTok 生产知识库",
            description="官方授权规则、企业产品事实、内容与经营审核口径。",
            capability_scope="sop_specific",
            metadata_json={"provider": "tiktok", "review_status": "approved", "source_policy": "official_or_internal"},
        )
        db.add(knowledge)
        created_count += 1
    knowledge_version = db.exec(
        select(KnowledgeBaseVersion).where(
            KnowledgeBaseVersion.tenant_id == tenant_id,
            KnowledgeBaseVersion.knowledge_base_id == knowledge.id,
            KnowledgeBaseVersion.version == "1.0.0",
        )
    ).first()
    if knowledge_version is None:
        db.add(
            KnowledgeBaseVersion(
                id="kbver_tiktok_production_v1",
                tenant_id=tenant_id,
                knowledge_base_id=knowledge.id,
                version="1.0.0",
                name="TikTok 生产知识库 v1",
                description="只读生产试点知识版本。",
                status="active",
                capability_scope="sop_specific",
                metadata_json={"review_status": "approved", "content_digest": "sha256:tiktok-production-v1"},
            )
        )
        created_count += 1

    tool_rows: list[Tool] = []
    for tool_name, display_name in TIKTOK_CONNECTOR_TOOLS:
        tool = db.exec(select(Tool).where(Tool.tenant_id == tenant_id, Tool.name == tool_name)).first()
        if tool is None:
            tool = Tool(
                id=f"tool_{tool_name.replace('.', '_')}",
                tenant_id=tenant_id,
                name=tool_name,
                display_name=display_name,
                description="本地 Mock/回放只读连接器；P3-A 禁止外部写操作。",
                bucket="TikTok 只读连接器",
                tool_type="builtin",
                method="GET",
                url=f"mock://{tool_name}",
                input_schema={"type": "object", "required": ["resource_id"]},
                output_schema={"type": "object", "required": ["fetched_at", "stale", "data"]},
                capability_scope="sop_specific",
                config_json={"review_status": "approved", "external_writes": False},
            )
            db.add(tool)
            created_count += 1
        tool_rows.append(tool)

    agent_rows: list[AgentProfile] = []
    settings = get_settings()
    issuer = settings.oidc_issuer or settings.casdoor_platform_endpoint or "http://casdoor.local"
    application_owner = settings.casdoor_management_application_owner.strip() or "admin"
    jwks_uri = settings.oidc_jwks_uri or f"{issuer.rstrip('/')}/.well-known/jwks"
    for slug, name, business_role, department_code in TIKTOK_AGENT_CATALOG:
        agent = db.exec(
            select(AgentProfile).where(AgentProfile.tenant_id == tenant_id, AgentProfile.name == name)
        ).first()
        if agent is None:
            agent = AgentProfile(
                id=f"agent_{slug}",
                tenant_id=tenant_id,
                name=name,
                description=f"{name}，仅处理 TikTok {department_code} 岗位范围内的受控只读与草稿任务。",
                persona_prompt="只引用已审核知识和授权数据；不执行 TikTok 外部写操作；缺少证据时转人工。",
                metadata_json={"business_role": business_role, "department_code": department_code, "provider": "tiktok", "review_status": "approved"},
                release_state="draft",
            )
            db.add(agent)
            created_count += 1
        elif (agent.metadata_json or {}).get("business_role") != business_role:
            raise HTTPException(status_code=409, detail=f"TikTok Agent role drift detected: {slug}")
        db.flush()
        identity = db.exec(
            select(AgentServiceIdentity).where(
                AgentServiceIdentity.tenant_id == tenant_id,
                AgentServiceIdentity.agent_id == agent.id,
            )
        ).first()
        if identity is None:
            application_name = f"app-joukir-{slug}"
            credential_ref = f"casdoor:{application_owner}/{application_name}"
            db.add(
                AgentServiceIdentity(
                    id=f"agent_identity_{slug}",
                    tenant_id=tenant_id,
                    agent_id=agent.id,
                    business_role=business_role,
                    provider="casdoor",
                    issuer=issuer,
                    token_endpoint=settings.oidc_token_endpoint
                    or f"{issuer.rstrip('/')}/api/login/oauth/access_token",
                    jwks_uri=jwks_uri,
                    application_owner=application_owner,
                    application_name=application_name,
                    client_id=_configured_m2m_client_id(settings, credential_ref, f"m2m_{slug}"),
                    client_id_fingerprint="sha256:"
                    + hashlib.sha256(
                        _configured_m2m_client_id(settings, credential_ref, f"m2m_{slug}").encode()
                    ).hexdigest(),
                    credential_ref=credential_ref,
                    metadata_json={"review_status": "approved", "external_writes": False},
                )
            )
            created_count += 1
        desired_skill_ids = TIKTOK_AGENT_SKILLS[slug]
        desired_tool_names = TIKTOK_AGENT_TOOLS[slug]
        managed_resource_ids = {
            *(skill.id for skill in skill_rows),
            *(general.id for general in general_skill_rows),
            *(tool.id for tool in tool_rows),
        }
        desired_resource_ids = {
            *(skill.id for skill in skill_rows if skill.skill_id in desired_skill_ids),
            *(general.id for general in general_skill_rows if general.slug in desired_skill_ids),
            *(tool.id for tool in tool_rows if tool.name in desired_tool_names),
        }
        for binding in db.exec(
            select(AgentResourceBinding).where(
                AgentResourceBinding.tenant_id == tenant_id,
                AgentResourceBinding.agent_id == agent.id,
                AgentResourceBinding.resource_type.in_(("skill", "general_skill", "tool")),
            )
        ).all():
            if (
                binding.status == "active"
                and binding.resource_id in managed_resource_ids
                and binding.resource_id not in desired_resource_ids
            ):
                binding.status = "inactive"
                binding.updated_at = utc_now()
                metadata = dict(binding.metadata_json or {})
                metadata["deactivated_reason"] = "outside_tiktok_agent_minimum_scope"
                binding.metadata_json = metadata
                db.add(binding)
                created_count += 1
        for skill in skill_rows:
            if skill.skill_id not in desired_skill_ids:
                continue
            if _ensure_binding(db, tenant_id=tenant_id, agent_id=agent.id, resource_type="skill", resource_id=skill.id, digest=_content_digest(skill.content_json)):
                created_count += 1
        for general in general_skill_rows:
            if general.slug not in desired_skill_ids:
                continue
            if _ensure_binding(db, tenant_id=tenant_id, agent_id=agent.id, resource_type="general_skill", resource_id=general.id, digest=str((general.metadata_json or {}).get("content_digest"))):
                created_count += 1
        branch_before = db.exec(
            select(AgentKnowledgeBranch).where(
                AgentKnowledgeBranch.tenant_id == tenant_id,
                AgentKnowledgeBranch.agent_id == agent.id,
                AgentKnowledgeBranch.knowledge_base_id == knowledge.id,
            )
        ).first()
        ensure_agent_private_knowledge_branch(
            db,
            tenant_id,
            agent.id,
            knowledge,
            metadata_json={
                "review_status": "approved",
                "content_digest": "sha256:tiktok-production-v1",
                "version": "1.0.0",
                "seed_origin": "joukir-tiktok-p3a",
            },
        )
        if branch_before is None:
            created_count += 1
        for tool in tool_rows:
            if tool.name not in desired_tool_names:
                continue
            if _ensure_binding(db, tenant_id=tenant_id, agent_id=agent.id, resource_type="tool", resource_id=tool.id, digest=_content_digest(tool.config_json)):
                created_count += 1
        agent_rows.append(agent)
    db.commit()
    return TikTokAssetBootstrapResponse(
        created_count=created_count,
        skill_ids=[row.id for row in skill_rows],
        agent_ids=[row.id for row in agent_rows],
        knowledge_base_ids=[knowledge.id],
        tool_ids=[row.id for row in tool_rows],
    )
