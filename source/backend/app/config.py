import os as _os
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Skill Agent Loop Service"
    database_url: str = "sqlite:///./skill_agent_loop.db"
    database_auto_create: bool = True
    database_seed_demo_data: bool = True
    database_rls_enabled: bool = False
    mock_api_enabled: bool = True
    # Enterprise routes fail secure by default; local demos may explicitly opt out.
    casbin_enabled: bool = True
    casbin_model_path: str = ""
    casbin_policy_path: str = ""
    app_secret: str = "change-me-in-development"
    oidc_enabled: bool = False
    oidc_issuer: str = ""
    oidc_authorization_endpoint: str = ""
    oidc_token_endpoint: str = ""
    oidc_jwks_uri: str = ""
    oidc_end_session_endpoint: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    oidc_scopes: str = "openid profile email"
    oidc_tenant_mapping_json: str = "{}"
    oidc_group_claim: str = "groups"
    oidc_group_role_mapping_json: str = "{}"
    oidc_require_mapped_group: bool = False
    oidc_session_ttl_seconds: int = 60 * 60 * 8
    oidc_cookie_secure: bool = False
    auth_failed_login_limit: int = 5
    auth_failed_login_lock_seconds: int = 15 * 60
    auth_invitation_ttl_seconds: int = 72 * 60 * 60
    casdoor_management_enabled: bool = False
    casdoor_management_endpoint: str = ""
    casdoor_management_client_id: str = ""
    casdoor_management_client_secret: str = ""
    casdoor_management_application_owner: str = "admin"
    casdoor_management_timeout_seconds: float = 10.0
    casdoor_management_sync_interval_seconds: float = 15 * 60
    tiktok_official_enabled: bool = False
    # Connector execution is explicit: mock is the safe local default, live
    # is required for official API calls, and replay remains fail-closed until
    # a connector-backed replay implementation is available.
    tiktok_connector_mode: Literal["mock", "replay", "live"] = "mock"
    tiktok_app_key: str = ""
    tiktok_app_secret: str = ""
    tiktok_service_id: str = ""
    tiktok_redirect_uri: str = ""
    tiktok_market: str = "ROW"
    tiktok_token_store_file: str = ""
    tiktok_token_refresh_skew_seconds: int = 300
    tiktok_http_timeout_seconds: float = 15.0
    tiktok_shadow_enabled: bool = False
    tiktok_shadow_tenant_ids: str = ""
    tiktok_shadow_interval_seconds: float = 15 * 60
    # Release evidence is supplied by a separate trusted controller. The app
    # receives only a public key and target-bound signed bundles.
    tiktok_release_evidence_dir: str = ""
    tiktok_release_evidence_public_key_file: str = ""
    tiktok_release_evidence_key_id: str = ""
    tiktok_release_target_commit: str = ""
    tiktok_release_request_sha256: str = ""
    platform_admin_api_enabled: bool = False
    platform_admin_api_key: str = ""
    platform_database_url: str = ""
    casdoor_platform_endpoint: str = ""
    casdoor_platform_client_id: str = ""
    casdoor_platform_client_secret: str = ""
    demo_model_base_url: str = "http://localhost:52010/v1"
    demo_model_name: str = "qwen3.6-27b"
    demo_model_api_key: str = ""
    model_api_timeout_seconds: float = 600.0
    model_thinking_mode: str = ""
    model_thinking_models: str = ""
    tool_timeout_seconds: float = 8.0
    a2a_task_timeout_seconds: float = 600.0
    a2a_poll_interval_seconds: float = 0.5
    codex_a2a_enabled: bool = False
    codex_a2a_command: str = "codex"
    codex_a2a_workspace_root: str = ""
    codex_a2a_timeout_seconds: float = 1800.0
    codex_a2a_token: str = ""
    tool_base_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    general_skill_runtime_python: str = ""
    general_skill_runtime_venv: str = ""
    general_skill_runtime_packages: str = "requests,httpx"
    # Keep runtime dependency installation enabled so published skills can
    # provision their declared baseline libraries on first use. Deployments
    # can still disable it explicitly for locked-down environments.
    general_skill_runtime_auto_install: bool = True
    general_skill_pip_index_url: str = ""
    general_skill_pip_timeout_seconds: int = 180
    general_skill_network_install: bool = True
    channel_secret: str = ""
    staffdeck_role: str = "all"
    wechat_ilink_base_url: str = "https://ilinkai.weixin.qq.com"
    channel_delivery_poll_seconds: float = 1.0
    channel_delivery_max_attempts: int = 8
    # Approved business actions are staged durably before any external call.
    # Keep sandbox as the safe default; live mode must be enabled explicitly.
    business_execution_enabled: bool = False
    business_execution_mode: str = "sandbox"
    business_execution_tenant_ids: str = ""
    business_execution_poll_seconds: float = 1.0
    business_execution_batch_size: int = 20
    business_execution_attempt_timeout_seconds: float = 15.0
    business_execution_max_attempts: int = 3
    business_execution_lease_seconds: int = 60
    business_execution_allowed_hosts: str = (
        "sellingpartnerapi-na.amazon.com,"
        "sellingpartnerapi-eu.amazon.com,"
        "sellingpartnerapi-fe.amazon.com,"
        "advertising-api.amazon.com,"
        "advertising-api-eu.amazon.com,"
        "advertising-api-fe.amazon.com"
    )
    # Unified work-task execution is opt-in. Sandbox exercises the same durable
    # claim/recovery path without invoking an external model or business tool.
    work_task_execution_enabled: bool = False
    work_task_execution_mode: str = "sandbox"
    work_task_execution_tenant_ids: str = ""
    work_task_execution_poll_seconds: float = 1.0
    work_task_execution_batch_size: int = 6
    work_task_execution_lease_seconds: int = 15 * 60
    work_task_execution_max_attempts: int = 3
    work_task_m2m_secret_file: str = ""
    work_task_m2m_timeout_seconds: float = 10.0
    public_api_enabled: bool = True
    public_api_key_pepper: str = ""
    public_api_idempotency_ttl_seconds: int = 60 * 60 * 24
    public_api_retention_days: int = 30
    public_api_webhook_timeout_seconds: float = 10.0
    public_api_webhook_max_attempts: int = 6
    # Creative uploads are staged locally first; deployments can lower or
    # raise this limit without changing the product lifecycle code.
    creative_upload_max_bytes: int = 12 * 1024 * 1024
    # Local is safe for development. Production uses an S3-compatible bucket
    # only when every endpoint and credential field is explicitly configured.
    creative_object_storage_backend: str = "local"
    creative_object_storage_endpoint: str = ""
    creative_object_storage_bucket: str = ""
    creative_object_storage_region: str = "us-east-1"
    creative_object_storage_access_key: str = ""
    creative_object_storage_secret_key: str = ""
    creative_object_storage_session_token: str = ""
    creative_object_storage_prefix: str = "joukir/creative"
    creative_object_storage_timeout_seconds: float = 30.0
    creative_media_ffprobe_path: str = ""
    creative_evidence_sync_interval_seconds: float = 15 * 60
    creative_generation_enabled: bool = False
    creative_generation_base_url: str = ""
    creative_generation_api_key: str = ""
    creative_generation_timeout_seconds: float = 120.0
    # 钉钉 emotion 接口的表情常量与所需权限尚未真机验证，验证通过前默认关闭：
    # 否则常量失效或权限未开时，每条入站消息都会留下一条失败的 reaction 投递。
    channel_dingtalk_reaction_enabled: bool = False
    # 出站富文本渲染开关：开启时飞书走 post 富文本、钉钉走 markdown 消息；
    # 关闭时两者回退为纯 text 消息，用于快速回退。
    channel_rich_render_enabled: bool = True
    # 飞书渠道实时执行步骤卡片开关：开启后飞书对话在执行过程中创建并实时更新
    # 一张独立卡片展示智能体每一步（SOP/工具/知识检索），与正文回复互不影响。
    # 仅影响飞书渠道；关闭时退化为仅发最终回复。
    channel_feishu_trace_enabled: bool = True
    # 飞书 trace 卡片 SOP 紧凑展示开关：开启后匹配 SOP（判断意图/进入流程）之后的
    # 中间步骤不再逐行展示，仅显示"翻书动画 + 正在推进SOP"，等待用户补充信息时
    # 定格为"📖 流程已暂停"，SOP 结束时定格为"✅ 流程已结束"。设为 False 可整体
    # 回滚为逐行展示的旧样式；binding 的 config_json.compact_trace=false 可对单个
    # 绑定回滚。
    channel_feishu_trace_compact_sop: bool = True

    model_config = SettingsConfigDict(
        env_file=_os.environ.get("ULTRARAG_DOTENV", ".env"),
        env_file_encoding="utf-8", extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def normalized_tool_base_url(self) -> str:
        return self.tool_base_url.rstrip("/")

    @property
    def general_skill_runtime_package_list(self) -> list[str]:
        return [item.strip() for item in self.general_skill_runtime_packages.split(",") if item.strip()]

    @property
    def oidc_scope_list(self) -> list[str]:
        return [item.strip() for item in self.oidc_scopes.split() if item.strip()]

    @property
    def business_execution_tenant_id_list(self) -> list[str]:
        return [item.strip() for item in self.business_execution_tenant_ids.split(",") if item.strip()]

    @property
    def business_execution_allowed_host_set(self) -> set[str]:
        return {item.strip().lower() for item in self.business_execution_allowed_hosts.split(",") if item.strip()}

    @property
    def work_task_execution_tenant_id_list(self) -> list[str]:
        return [item.strip() for item in self.work_task_execution_tenant_ids.split(",") if item.strip()]

    @property
    def tiktok_shadow_tenant_id_list(self) -> list[str]:
        return [item.strip() for item in self.tiktok_shadow_tenant_ids.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
