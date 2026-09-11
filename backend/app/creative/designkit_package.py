"""Import the DesignKit detail-page package into the creative employee scope.

The migration ZIP is treated as source data.  It is parsed and stored for
audit, but its CLI instructions are never executed by the backend.  This is
important because the package describes a third-party CLI login/install flow,
not a StaffDeck API or MCP server.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from app.agents.branching import (
    ensure_agent_skill_branch,
    ensure_open_gallery_binding,
    ensure_private_resource_binding,
    mark_resource_open_gallery,
)
from app.agents.releases import mark_agent_draft_if_changed
from app.config import get_settings
from app.db.models import (
    AgentProfile,
    AgentResourceBinding,
    GeneralSkill,
    Skill,
    SkillVersion,
    Tool,
    User,
    utc_now,
)
from app.skills.skill_schema import (
    SkillCapabilityRefs,
    SkillCard,
    SkillGraphEdge,
    SkillGraphNode,
)

PACKAGE_ID = "joukir.creative.designkit-detail-page"
SKILL_ID = "designkit_detail_page_v1"
GENERAL_SKILL_SLUG = "designkit-detail-page"
API_TOOL_NAME = "designkit.detail_page.context_read"
API_TOOL_ID = "tool_designkit_detail_page_context"
PACKAGE_ROOT = "designkit-detail-page"
REQUIRED_FILES = (
    "README.md",
    "MIGRATION.md",
    "agents/designkit-detail-page.md",
    "skills/detail-page/SKILL.md",
    "skills/detail-page/references/form.json",
    "skills-as-standard/SKILL.md",
    "skills-as-standard/references/form.json",
)


class DesignKitPackageError(ValueError):
    """Raised when the supplied package is unsafe or has drifted."""


@dataclass(frozen=True)
class DesignKitPackage:
    archive_sha256: str
    package_version: str
    skill_version: str
    display_name: str
    description: str
    skill_markdown: str
    skill_files: list[dict[str, Any]]
    form: dict[str, Any]


@dataclass(frozen=True)
class DesignKitProvisionResult:
    tenant_id: str
    agent_id: str
    skill_id: str
    skill_row_id: str
    general_skill_id: str
    tool_id: str
    package_version: str
    skill_version: str
    archive_sha256: str
    mcp_status: str
    agent_release_state: str


def _safe_member_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    path = Path(normalized)
    if not normalized or normalized.startswith("/") or path.drive:
        raise DesignKitPackageError(f"unsafe ZIP member path: {name!r}")
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise DesignKitPackageError(f"unsafe ZIP member path: {name!r}")
    return normalized


def _frontmatter(markdown: str) -> dict[str, str]:
    if not markdown.startswith("---"):
        return {}
    match = re.match(r"^---\s*\n(?P<body>.*?)\n---\s*\n", markdown, flags=re.DOTALL)
    if not match:
        return {}
    result: dict[str, str] = {}
    for line in match.group("body").splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        value = value.strip().strip('"').strip("'")
        if key.strip() and value:
            result[key.strip()] = value
    return result


def _required_form_fields(form: dict[str, Any]) -> list[str]:
    fields = form.get("form", {}).get("fields", [])
    if not isinstance(fields, list):
        return []
    return [
        str(field["key"])
        for field in fields
        if isinstance(field, dict) and field.get("required") is True and field.get("key")
    ]


def _package_version(migration: str) -> str:
    match = re.search(
        r"(?:当前|current)[^0-9]*(\d+\.\d+\.\d+)", migration, flags=re.IGNORECASE
    )
    return match.group(1) if match else "1.0.6"


def _safe_skill_markdown(display_name: str, description: str, skill_version: str) -> str:
    # Keep the executable CLI instructions in the audit files, not in the
    # runtime prompt.  StaffDeck must never install, authenticate, or invoke a
    # third-party CLI merely because a package was imported.
    return (
        f"# {display_name}\n\n"
        f"{description}\n\n"
        f"来源包 Skill 版本：{skill_version}。\n\n"
        "## Joukir 执行边界\n"
        "- 只收集商品图片、目标平台、尺寸比例、语言和地区等输入。\n"
        "- 只读取已授权的商品上下文；不读取或输出凭据、Cookie、Token 或本地绝对路径。\n"
        "- 迁移包只提供第三方 CLI 说明，不代表已配置 DesignKit API 或 MCP。\n"
        "- 未配置并审核真实连接器时，只生成待执行请求清单并转人工，不安装、登录或调用外部服务。\n"
        "- 外部生成结果必须重新上传、质检并由人工批准，不能自动发布。\n"
    )


def load_designkit_package(zip_path: str | Path) -> DesignKitPackage:
    """Validate and read the ZIP without extracting or running any entry."""

    path = Path(zip_path)
    if not path.is_file():
        raise DesignKitPackageError(f"package file does not exist: {path}")
    archive_bytes = path.read_bytes()
    archive_sha256 = "sha256:" + hashlib.sha256(archive_bytes).hexdigest()
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise DesignKitPackageError("package is not a valid ZIP archive") from exc
    with archive:
        entries: dict[str, bytes] = {}
        for info in archive.infolist():
            member = _safe_member_name(info.filename)
            if member.endswith("/"):
                continue
            if not member.startswith(f"{PACKAGE_ROOT}/"):
                raise DesignKitPackageError(f"ZIP member is outside package root: {member}")
            entries[member.removeprefix(f"{PACKAGE_ROOT}/")] = archive.read(info)
        missing = [name for name in REQUIRED_FILES if name not in entries]
        if missing:
            raise DesignKitPackageError("package is missing required files: " + ", ".join(missing))
        standard_skill = entries["skills-as-standard/SKILL.md"]
        original_skill = entries["skills/detail-page/SKILL.md"]
        if standard_skill != original_skill:
            raise DesignKitPackageError("the two packaged SKILL.md files differ")
        try:
            form = json.loads(entries["skills/detail-page/references/form.json"].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DesignKitPackageError("form.json is not valid UTF-8 JSON") from exc
        if not isinstance(form, dict) or not _required_form_fields(form):
            raise DesignKitPackageError("form.json has no required input fields")
        try:
            skill_text = original_skill.decode("utf-8")
            migration_text = entries["MIGRATION.md"].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DesignKitPackageError("text files must be UTF-8") from exc
        metadata = _frontmatter(skill_text)
        display_name = metadata.get("display_name") or "详情模块图"
        description = metadata.get("description") or "电商详情页模块图设计 Skill"
        skill_version = metadata.get("version") or "1.0.0"
        package_version = _package_version(migration_text)
        files = []
        for name, content in sorted(entries.items()):
            if name.endswith((".md", ".json")):
                files.append(
                    {
                        "path": name,
                        "content": content.decode("utf-8"),
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "source_only": True,
                    }
                )
        return DesignKitPackage(
            archive_sha256=archive_sha256,
            package_version=package_version,
            skill_version=skill_version,
            display_name=display_name,
            description=description,
            skill_markdown=_safe_skill_markdown(display_name, description, skill_version),
            skill_files=files,
            form=form,
        )


def _skill_content(package: DesignKitPackage, tool_id: str) -> dict[str, Any]:
    required_info = _required_form_fields(package.form)
    nodes = [
        SkillGraphNode(
            node_id="collect_detail_brief",
            type="collect_info",
            name="收集详情页设计需求",
            instruction="收集商品素材、目标平台、模块比例、语言、地区和卖点；缺少必填项时只追问缺失项。",
            expected_user_info=required_info + ["language", "region", "selling_points"],
            allowed_actions=["ask_for_missing_fields"],
        ),
        SkillGraphNode(
            node_id="read_product_context",
            type="tool_call",
            name="读取商品上下文",
            instruction="通过只读 API 获取当前员工可见的店铺、商品和待办上下文，不读取凭据。",
            allowed_actions=["call_read_only_api"],
            capability_refs=SkillCapabilityRefs(
                tool_ids=[tool_id], required_tool_ids=[tool_id]
            ),
            metadata={"external_writes": False, "risk_class": "read_only"},
        ),
        SkillGraphNode(
            node_id="prepare_designkit_request",
            type="transform",
            name="生成 DesignKit 请求清单",
            instruction="按照迁移包表单契约整理可复制的设计请求和素材引用；不得执行第三方 CLI。",
            allowed_actions=["render_request_manifest"],
            metadata={"connector_status": "not_configured"},
        ),
        SkillGraphNode(
            node_id="human_review_handoff",
            type="handoff_human",
            name="人工确认后执行",
            instruction="提示业务人员确认设计请求；未配置审核通过的 API/MCP 时转人工，不自动安装、登录或提交外部任务。",
            allowed_actions=["handoff_to_human"],
            metadata={"requires_business_approval": True, "live_write_approval": "not_granted"},
        ),
    ]
    edges = [
        SkillGraphEdge(source_node_id="collect_detail_brief", next_node_id="read_product_context"),
        SkillGraphEdge(source_node_id="read_product_context", next_node_id="prepare_designkit_request"),
        SkillGraphEdge(source_node_id="prepare_designkit_request", next_node_id="human_review_handoff"),
    ]
    return SkillCard(
        skill_id=SKILL_ID,
        name=package.display_name,
        version=package.skill_version,
        business_domain="creative_design",
        description=package.description,
        capability_scope="sop_specific",
        trigger_intents=["详情模块图", "A+ 模块图", "电商详情页设计", "商品详情图"],
        user_utterance_examples=["帮我做 Amazon A+ 模块图", "生成 TikTok Shop 商品详情模块设计清单"],
        goal=["把商品素材和平台规格整理为可审计的详情页模块设计请求", "在外部执行前保留人工审核边界"],
        required_info=required_info + ["language", "region", "selling_points"],
        slot_filling_policy={"source": "designkit.form.json", "ask_only_missing": True},
        response_rules=[
            "不得虚构已生成的图片、任务号或外部平台提交结果。",
            "不得自动执行迁移包中的 npm install、auth login 或第三方 CLI 命令。",
            "不得输出 Token、Cookie、API Key、session_id 或本地绝对路径。",
            "外部连接器未配置时，输出待人工执行的请求清单并创建跟进任务。",
        ],
        nodes=nodes,
        edges=edges,
        start_node_id="collect_detail_brief",
        terminal_node_ids=["human_review_handoff"],
        interruption_policy={"unrelated_business": "保存详情页需求快照后转入美工待办队列。"},
    ).model_dump()


def _package_metadata(
    package: DesignKitPackage,
    *,
    review_status: str,
    approval_scope: str,
) -> dict[str, Any]:
    return {
        "managed_package": PACKAGE_ID,
        "package_version": package.package_version,
        "skill_version": package.skill_version,
        "source_zip_sha256": package.archive_sha256,
        "review_status": review_status,
        "approval_scope": approval_scope,
        "live_write_approval": "not_granted",
        "external_writes": False,
        "mcp_status": "pending_external_connector",
        "mcp_reason": "迁移包只提供 designkit CLI，不包含真实 MCP transport 或服务端地址。",
    }


def _assert_same_package(metadata: dict[str, Any], package: DesignKitPackage, label: str) -> None:
    if metadata.get("source_zip_sha256") != package.archive_sha256:
        raise DesignKitPackageError(f"{label} already exists with a different package digest")


def _upsert_skill(
    db: Session,
    tenant_id: str,
    package: DesignKitPackage,
    content: dict[str, Any],
) -> Skill:
    row = db.exec(select(Skill).where(Skill.tenant_id == tenant_id, Skill.skill_id == SKILL_ID)).first()
    if row is None:
        row = Skill(
            id="skill_designkit_detail_page_v1",
            tenant_id=tenant_id,
            skill_id=SKILL_ID,
            version=package.skill_version,
            name=package.display_name,
            business_domain="creative_design",
            description=package.description,
            content_json=content,
            status="published",
        )
        db.add(row)
        db.flush()
    # Skill has no metadata column.  The source digest is kept on the binding
    # and the companion GeneralSkill, while the immutable version stores the
    # exact validated SkillCard content.
    row.version = package.skill_version
    row.name = package.display_name
    row.description = package.description
    row.content_json = content
    row.status = "published"
    row.updated_at = utc_now()
    db.add(row)
    version = db.exec(
        select(SkillVersion).where(
            SkillVersion.tenant_id == tenant_id,
            SkillVersion.skill_id == SKILL_ID,
            SkillVersion.version == package.skill_version,
        )
    ).first()
    if version is None:
        db.add(
            SkillVersion(
                tenant_id=tenant_id,
                skill_id=SKILL_ID,
                version=package.skill_version,
                name=package.display_name,
                business_domain="creative_design",
                description=package.description,
                content_json=content,
                status="published",
            )
        )
    else:
        version.content_json = content
        version.status = "published"
        version.updated_at = utc_now()
        db.add(version)
    return row


def provision_designkit_package(
    db: Session,
    *,
    tenant_id: str,
    agent_id: str,
    zip_path: str | Path,
    actor: User | None = None,
    tool_base_url: str | None = None,
) -> DesignKitProvisionResult:
    """Idempotently install the package and bind it to the designer employee."""

    package = load_designkit_package(zip_path)
    agent = db.exec(
        select(AgentProfile).where(
            AgentProfile.tenant_id == tenant_id,
            AgentProfile.id == agent_id,
            AgentProfile.status == "active",
        )
    ).first()
    if not agent:
        raise DesignKitPackageError("target digital employee is not active in this tenant")
    if str((agent.metadata_json or {}).get("business_role") or "") != "designer":
        raise DesignKitPackageError("target digital employee is not the designer role")

    settings = get_settings()
    api_url = (tool_base_url or settings.normalized_tool_base_url).rstrip("/")
    metadata = _package_metadata(
        package,
        review_status="pending_business_review",
        approval_scope="sandbox_only",
    )
    tool_metadata = _package_metadata(
        package,
        review_status="approved",
        approval_scope="sandbox_read_only",
    )

    tool = db.exec(
        select(Tool).where(Tool.tenant_id == tenant_id, Tool.name == API_TOOL_NAME)
    ).first()
    if tool:
        _assert_same_package(dict((tool.config_json or {}).get("package") or {}), package, "API tool")
    else:
        tool = Tool(
            id=API_TOOL_ID,
            tenant_id=tenant_id,
            name=API_TOOL_NAME,
            display_name="DesignKit 商品上下文只读 API",
            description="为详情页设计 Skill 提供店铺、商品和待办上下文；不执行外部写操作。",
            bucket="美工设计 API",
            tool_type="http",
            method="GET",
            url=f"{api_url}/api/internal/tools/crossborder/role-context",
            input_schema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}},
            },
            output_schema={"type": "object", "required": ["schema_version", "resources", "tasks"]},
            allowed_skills_json=[SKILL_ID],
            capability_scope="sop_specific",
            config_json={
                "package": metadata,
                "production": {
                    "business_role": "designer",
                    "resource_types": ["store", "ad_account"],
                    "risk_class": "read_only",
                    "side_effect": "none",
                    "external_writes": False,
                    "review_status": "approved",
                    "approval_scope": "sandbox_read_only",
                },
                "mcp_configuration": {
                    "status": "pending_external_connector",
                    "transport_options": ["stdio", "streamable_http"],
                    "server_name": "designkit-detail-page",
                    "enabled": False,
                },
            },
            enabled=True,
        )
        db.add(tool)
        db.flush()
    tool.url = f"{api_url}/api/internal/tools/crossborder/role-context"
    tool.allowed_skills_json = [SKILL_ID]
    tool.enabled = True
    db.add(tool)

    existing_skill = db.exec(
        select(Skill).where(Skill.tenant_id == tenant_id, Skill.skill_id == SKILL_ID)
    ).first()
    if existing_skill:
        existing_binding = db.exec(
            select(AgentResourceBinding).where(
                AgentResourceBinding.tenant_id == tenant_id,
                AgentResourceBinding.agent_id == agent_id,
                AgentResourceBinding.resource_type == "skill",
                AgentResourceBinding.resource_id == existing_skill.id,
            )
        ).first()
        if existing_binding:
            _assert_same_package(
                dict(existing_binding.metadata_json or {}), package, "Skill binding"
            )
    content = _skill_content(package, tool.id)
    skill = _upsert_skill(db, tenant_id, package, content)
    mark_resource_open_gallery(skill)
    ensure_open_gallery_binding(
        db,
        tenant_id,
        "skill",
        skill.id,
        "active",
        metadata_json={**metadata, "review_status": "approved_seed"},
        revive=True,
    )
    ensure_private_resource_binding(
        db,
        tenant_id,
        agent_id,
        "skill",
        skill.id,
        "active",
        metadata_json=metadata,
        revive=True,
    )
    branch = ensure_agent_skill_branch(db, tenant_id, agent_id, skill, metadata_json=metadata)
    branch.content_json = content
    branch.base_version = package.skill_version
    branch.head_version = package.skill_version
    branch.status = "active"
    branch.sync_state = "synced"
    branch.updated_at = utc_now()
    db.add(branch)

    general = db.exec(
        select(GeneralSkill).where(
            GeneralSkill.tenant_id == tenant_id, GeneralSkill.slug == GENERAL_SKILL_SLUG
        )
    ).first()
    if general:
        _assert_same_package(general.metadata_json or {}, package, "GeneralSkill")
    else:
        general = GeneralSkill(
            id="genskill_designkit_detail_page",
            tenant_id=tenant_id,
            slug=GENERAL_SKILL_SLUG,
            name=package.display_name,
            description=package.description,
            homepage="internal://joukir/creative/designkit-detail-page",
            skill_markdown=package.skill_markdown,
            skill_files_json=package.skill_files,
            metadata_json=metadata,
            status="published",
            capability_scope="sop_specific",
            permissions_json={"network": False, "python": False, "external_writes": False},
            runtime_config_json={"runtime": "document_only", "timeout_seconds": 12},
        )
        db.add(general)
    general.skill_markdown = package.skill_markdown
    general.skill_files_json = package.skill_files
    general.metadata_json = metadata
    general.status = "published"
    general.capability_scope = "sop_specific"
    general.updated_at = utc_now()
    mark_resource_open_gallery(general, {"review_status": "approved_seed"})
    db.add(general)
    ensure_open_gallery_binding(
        db,
        tenant_id,
        "general_skill",
        general.id,
        "active",
        metadata_json={**metadata, "review_status": "approved_seed"},
        revive=True,
    )
    ensure_private_resource_binding(
        db,
        tenant_id,
        agent_id,
        "general_skill",
        general.id,
        "active",
        metadata_json=metadata,
        revive=True,
    )
    ensure_private_resource_binding(
        db,
        tenant_id,
        agent_id,
        "tool",
        tool.id,
        "active",
        metadata_json=tool_metadata,
        revive=True,
    )
    ensure_open_gallery_binding(
        db,
        tenant_id,
        "tool",
        tool.id,
        "active",
        metadata_json=tool_metadata,
        revive=True,
    )
    db.flush()
    if actor:
        mark_agent_draft_if_changed(
            db,
            agent,
            actor=actor,
            reason="DesignKit 详情模块图 Skill/API 绑定发生变更，等待业务负责人发布新的 AgentRelease",
        )
    db.commit()
    db.refresh(agent)
    return DesignKitProvisionResult(
        tenant_id=tenant_id,
        agent_id=agent_id,
        skill_id=SKILL_ID,
        skill_row_id=skill.id,
        general_skill_id=general.id,
        tool_id=tool.id,
        package_version=package.package_version,
        skill_version=package.skill_version,
        archive_sha256=package.archive_sha256,
        mcp_status="pending_external_connector",
        agent_release_state=agent.release_state,
    )
