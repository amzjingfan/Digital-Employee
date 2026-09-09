from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def utc_now_aware() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


class Tenant(SQLModel, table=True):
    __tablename__ = "tenants"

    id: str = Field(primary_key=True)
    name: str
    status: str = Field(default="active", index=True)
    casdoor_organization: Optional[str] = Field(default=None, index=True)
    identity_sync_status: str = Field(default="not_configured", index=True)
    default_locale: str = Field(default="en")
    default_timezone: str = Field(default="UTC")
    default_currency: str = Field(default="USD")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class OIDCLoginState(SQLModel, table=True):
    """Short-lived server-side PKCE and nonce state; never tenant business data."""

    __tablename__ = "oidc_login_states"

    state_hash: str = Field(primary_key=True)
    code_verifier: str
    nonce: str
    return_to: str
    expires_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="uq_user_tenant_username"),
        UniqueConstraint("tenant_id", "id", name="uq_users_tenant_id_id"),
        Index("ix_users_tenant_id_display_name", "tenant_id", "display_name"),
    )

    id: str = Field(default_factory=lambda: new_id("user"), primary_key=True)
    tenant_id: str = Field(index=True)
    username: str = Field(index=True)
    display_name: Optional[str] = None
    role: str = Field(default="member", index=True)
    business_role: str = Field(default="member", index=True)
    authorization_source: str = Field(default="local", index=True)
    identity_groups_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    role_synced_at: Optional[datetime] = Field(default=None, index=True)
    # 账号来源:web=网页端创建;wechat 等=渠道懒建(用户管理列表默认隐藏)
    source: str = Field(default="web", index=True)
    password_hash: str
    status: str = Field(default="active", index=True)
    session_version: int = Field(default=1)
    failed_login_attempts: int = Field(default=0)
    locked_until: Optional[datetime] = Field(default=None, index=True)
    identity_sync_status: str = Field(default="not_configured", index=True)
    preferred_locale: Optional[str] = Field(default=None)
    preferred_timezone: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Brand(SQLModel, table=True):
    """Tenant-owned brand boundary shared by every commerce module."""

    __tablename__ = "brands"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_brands_tenant_code"),
        UniqueConstraint("tenant_id", "id", name="uq_brands_tenant_id_id"),
        CheckConstraint(
            "status IN ('active', 'inactive', 'archived')",
            name="brands_status_check",
        ),
        Index("ix_brands_tenant_status_name", "tenant_id", "status", "name"),
    )

    id: str = Field(default_factory=lambda: new_id("brand"), primary_key=True)
    tenant_id: str = Field(index=True)
    code: str = Field(index=True)
    name: str
    timezone: str = Field(default="UTC")
    status: str = Field(default="active", index=True)
    revision: int = Field(default=1)
    created_by_user_id: str = Field(index=True)
    created_at: datetime = Field(
        default_factory=utc_now_aware,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=utc_now_aware,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class BrandMembership(SQLModel, table=True):
    """Explicit human access to a brand inside an already trusted tenant."""

    __tablename__ = "brand_memberships"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "brand_id",
            "user_id",
            name="uq_brand_memberships_tenant_brand_user",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "brand_id"],
            ["brands.tenant_id", "brands.id"],
            name="fk_brand_memberships_tenant_brand",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_brand_memberships_tenant_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "access_level IN ('viewer', 'operator')",
            name="brand_memberships_access_check",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="brand_memberships_status_check",
        ),
        Index("ix_brand_memberships_tenant_user_status", "tenant_id", "user_id", "status"),
    )

    id: str = Field(default_factory=lambda: new_id("brandmember"), primary_key=True)
    tenant_id: str = Field(index=True)
    brand_id: str = Field(index=True)
    user_id: str = Field(index=True)
    access_level: str = Field(default="viewer", index=True)
    status: str = Field(default="active", index=True)
    created_by_user_id: str = Field(index=True)
    created_at: datetime = Field(
        default_factory=utc_now_aware,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=utc_now_aware,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class StoreAccess(SQLModel, table=True):
    """Assign one tenant store resource to exactly one explicit brand scope."""

    __tablename__ = "store_accesses"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "resource_id",
            name="uq_store_accesses_tenant_resource",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "brand_id"],
            ["brands.tenant_id", "brands.id"],
            name="fk_store_accesses_tenant_brand",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "resource_id"],
            ["business_resources.tenant_id", "business_resources.id"],
            name="fk_store_accesses_tenant_resource",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="store_accesses_status_check",
        ),
        Index("ix_store_accesses_tenant_brand_status", "tenant_id", "brand_id", "status"),
    )

    id: str = Field(default_factory=lambda: new_id("storeaccess"), primary_key=True)
    tenant_id: str = Field(index=True)
    brand_id: str = Field(index=True)
    resource_id: str = Field(index=True)
    status: str = Field(default="active", index=True)
    created_by_user_id: str = Field(index=True)
    created_at: datetime = Field(
        default_factory=utc_now_aware,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=utc_now_aware,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class BrandAccessEvent(SQLModel, table=True):
    """Append-only evidence for brand, membership, and store-scope changes."""

    __tablename__ = "brand_access_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "brand_id"],
            ["brands.tenant_id", "brands.id"],
            name="fk_brand_access_events_tenant_brand",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "event_type IN ('brand_created', 'membership_changed', 'store_access_changed')",
            name="brand_access_events_type_check",
        ),
        Index("ix_brand_access_events_tenant_brand_time", "tenant_id", "brand_id", "occurred_at"),
    )

    id: str = Field(default_factory=lambda: new_id("brand_event"), primary_key=True)
    tenant_id: str = Field(index=True)
    brand_id: str = Field(index=True)
    event_type: str = Field(index=True)
    actor_user_id: str = Field(index=True)
    subject_user_id: str | None = Field(default=None, index=True)
    resource_id: str | None = Field(default=None, index=True)
    detail_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    occurred_at: datetime = Field(
        default_factory=utc_now_aware,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )


class UserInvitation(SQLModel, table=True):
    """One-time, tenant-scoped invitation. Only the token digest is persisted."""

    __tablename__ = "user_invitations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "token_digest", name="uq_user_invitation_token_digest"),
        Index("ix_user_invitations_tenant_status_expires", "tenant_id", "status", "expires_at"),
    )

    id: str = Field(default_factory=lambda: new_id("invite"), primary_key=True)
    tenant_id: str = Field(index=True)
    username: str = Field(index=True)
    display_name: Optional[str] = None
    role: str = Field(default="member", index=True)
    business_role: str = Field(default="member", index=True)
    auth_source: str = Field(default="local", index=True)
    token_digest: str = Field(index=True)
    status: str = Field(default="pending", index=True)
    invited_by_user_id: str = Field(index=True)
    accepted_by_user_id: Optional[str] = Field(default=None, index=True)
    expires_at: datetime = Field(index=True)
    accepted_at: Optional[datetime] = Field(default=None, index=True)
    cancelled_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class AccountLifecycleEvent(SQLModel, table=True):
    """Append-only authentication and account administration audit event."""

    __tablename__ = "account_lifecycle_events"
    __table_args__ = (
        Index("ix_account_lifecycle_tenant_subject_time", "tenant_id", "subject_user_id", "occurred_at"),
    )

    id: str = Field(default_factory=lambda: new_id("account_event"), primary_key=True)
    tenant_id: str = Field(index=True)
    event_type: str = Field(index=True)
    actor_user_id: Optional[str] = Field(default=None, index=True)
    subject_user_id: Optional[str] = Field(default=None, index=True)
    subject_ref: str = Field(default="", index=True)
    outcome: str = Field(default="allowed", index=True)
    reason: str = Field(default="")
    detail_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    occurred_at: datetime = Field(default_factory=utc_now, index=True)


class TenantLifecycleEvent(SQLModel, table=True):
    """Append-only platform control-plane audit without tenant business payloads."""

    __tablename__ = "tenant_lifecycle_events"
    __table_args__ = (
        Index("ix_tenant_lifecycle_tenant_time", "tenant_id", "occurred_at"),
    )

    id: str = Field(default_factory=lambda: new_id("tenant_event"), primary_key=True)
    tenant_id: str = Field(index=True)
    event_type: str = Field(index=True)
    actor_ref: str = Field(index=True)
    outcome: str = Field(default="allowed", index=True)
    reason: str = Field(default="")
    detail_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    occurred_at: datetime = Field(default_factory=utc_now, index=True)


class UserIdentity(SQLModel, table=True):
    """Verified external subject linked to exactly one tenant-local StaffDeck user."""

    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("provider", "issuer", "subject", name="uq_user_identity_subject"),
        UniqueConstraint(
            "tenant_id", "user_id", "provider", "issuer", name="uq_user_identity_user_issuer"
        ),
    )

    id: str = Field(default_factory=lambda: new_id("identity"), primary_key=True)
    tenant_id: str = Field(index=True)
    user_id: str = Field(index=True)
    provider: str = Field(default="oidc", index=True)
    issuer: str = Field(index=True)
    subject: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class UserAvatar(SQLModel, table=True):
    """用户头像:小图以 data_url 直接存库(与聊天附件内联方式一致),

    独立小表避免 users 热表膨胀;create_all 建表,无需 ALTER。
    """

    __tablename__ = "user_avatars"

    user_id: str = Field(primary_key=True)
    data_url: str
    updated_at: datetime = Field(default_factory=utc_now)


class APIClient(SQLModel, table=True):
    """Server-to-server identity for the versioned public API."""

    __tablename__ = "api_clients"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_api_client_tenant_name"),
    )

    id: str = Field(default_factory=lambda: new_id("apiclient"), primary_key=True)
    tenant_id: str = Field(index=True)
    name: str
    description: Optional[str] = None
    scopes_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = Field(default="active", index=True)
    created_by_user_id: Optional[str] = Field(default=None, index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class APICredential(SQLModel, table=True):
    """Hashed tenant or agent credential. Plaintext is returned exactly once."""

    __tablename__ = "api_credentials"
    __table_args__ = (
        UniqueConstraint("key_prefix", name="uq_api_credential_prefix"),
    )

    id: str = Field(default_factory=lambda: new_id("apicred"), primary_key=True)
    tenant_id: str = Field(index=True)
    client_id: str = Field(index=True)
    agent_id: Optional[str] = Field(default=None, index=True)
    name: str
    key_prefix: str = Field(index=True)
    key_digest: str
    scopes_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = Field(default="active", index=True)
    expires_at: Optional[datetime] = Field(default=None, index=True)
    last_used_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    revoked_at: Optional[datetime] = None


class APIIdempotencyRecord(SQLModel, table=True):
    __tablename__ = "api_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "credential_id", "method", "path", "idempotency_key",
            name="uq_api_idempotency_request",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("apiidem"), primary_key=True)
    tenant_id: str = Field(index=True)
    credential_id: str = Field(index=True)
    method: str
    path: str
    idempotency_key: str = Field(index=True)
    request_hash: str
    status_code: int = 200
    response_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    resource_id: Optional[str] = Field(default=None, index=True)
    expires_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class APIJob(SQLModel, table=True):
    __tablename__ = "api_jobs"

    id: str = Field(default_factory=lambda: new_id("apijob"), primary_key=True)
    tenant_id: str = Field(index=True)
    credential_id: str = Field(index=True)
    agent_id: Optional[str] = Field(default=None, index=True)
    kind: str = Field(index=True)
    status: str = Field(default="queued", index=True)
    stage: str = Field(default="queued", index=True)
    progress: float = 0.0
    request_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    result_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    error_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    cancel_requested: bool = False
    retryable: bool = False
    execution_owner: Optional[str] = Field(default=None, index=True)
    execution_generation: int = 0
    lease_expires_at: Optional[datetime] = Field(default=None, index=True)
    session_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=utc_now)


class APIJobEvent(SQLModel, table=True):
    __tablename__ = "api_job_events"
    __table_args__ = (
        UniqueConstraint("job_id", "sequence", name="uq_api_job_event_sequence"),
    )

    id: str = Field(default_factory=lambda: new_id("apievent"), primary_key=True)
    tenant_id: str = Field(index=True)
    job_id: str = Field(index=True)
    sequence: int = Field(index=True)
    event_type: str = Field(index=True)
    data_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    public: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class A2ATaskRun(SQLModel, table=True):
    """Durable state for outbound A2A calls and locally served A2A tasks."""

    __tablename__ = "a2a_task_runs"

    id: str = Field(default_factory=lambda: new_id("a2arun"), primary_key=True)
    direction: str = Field(default="client", index=True)
    tenant_id: str = Field(index=True)
    tool_id: Optional[str] = Field(default=None, index=True)
    agent_id: Optional[str] = Field(default=None, index=True)
    session_id: Optional[str] = Field(default=None, index=True)
    invocation_id: Optional[str] = Field(default=None, index=True)
    endpoint_url: str
    agent_card_url: Optional[str] = None
    protocol_binding: str = "JSONRPC"
    protocol_version: str = "1.0"
    remote_task_id: Optional[str] = Field(default=None, index=True)
    context_id: Optional[str] = Field(default=None, index=True)
    codex_session_id: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="submitted", index=True)
    request_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    result_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    error_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    artifacts_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    agent_card_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    last_event_id: Optional[str] = Field(default=None, index=True)
    cancel_requested: bool = False
    recovery_attempts: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=utc_now)


class A2ATaskEvent(SQLModel, table=True):
    __tablename__ = "a2a_task_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_a2a_task_event_sequence"),
    )

    id: str = Field(default_factory=lambda: new_id("a2aevt"), primary_key=True)
    tenant_id: str = Field(index=True)
    run_id: str = Field(index=True)
    sequence: int = Field(index=True)
    external_event_id: Optional[str] = Field(default=None, index=True)
    event_type: str = Field(index=True)
    data_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)


class WebhookEndpoint(SQLModel, table=True):
    __tablename__ = "webhook_endpoints"

    id: str = Field(default_factory=lambda: new_id("webhook"), primary_key=True)
    tenant_id: str = Field(index=True)
    client_id: str = Field(index=True)
    name: str
    url: str
    secret_encrypted: str
    events_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = Field(default="active", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WebhookDelivery(SQLModel, table=True):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        UniqueConstraint("endpoint_id", "event_id", name="uq_webhook_delivery_event"),
    )

    id: str = Field(default_factory=lambda: new_id("whdelivery"), primary_key=True)
    tenant_id: str = Field(index=True)
    endpoint_id: str = Field(index=True)
    event_id: str = Field(index=True)
    event_type: str = Field(index=True)
    payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = Field(default="queued", index=True)
    delivery_owner: Optional[str] = Field(default=None, index=True)
    lease_expires_at: Optional[datetime] = Field(default=None, index=True)
    attempt_count: int = 0
    next_attempt_at: Optional[datetime] = Field(default=None, index=True)
    last_status_code: Optional[int] = None
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    delivered_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=utc_now)


class ExternalSessionBinding(SQLModel, table=True):
    __tablename__ = "external_session_bindings"
    __table_args__ = (
        UniqueConstraint(
            "credential_id", "external_session_id",
            name="uq_external_session_credential_id",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("extsession"), primary_key=True)
    tenant_id: str = Field(index=True)
    credential_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    external_session_id: str = Field(index=True)
    external_user_id: Optional[str] = Field(default=None, index=True)
    session_id: str = Field(index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class APISOPDraft(SQLModel, table=True):
    __tablename__ = "api_sop_drafts"

    id: str = Field(default_factory=lambda: new_id("sopdraft"), primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    skill_id: str = Field(index=True)
    base_version: Optional[str] = Field(default=None, index=True)
    draft_version: str = Field(index=True)
    content_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    status: str = Field(default="draft", index=True)
    source: str = Field(default="structured", index=True)
    warnings_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    validation_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    etag: str = Field(index=True)
    created_by_credential_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    published_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=utc_now)


class APIAuditLog(SQLModel, table=True):
    __tablename__ = "api_audit_logs"

    id: str = Field(default_factory=lambda: new_id("apiaudit"), primary_key=True)
    tenant_id: Optional[str] = Field(default=None, index=True)
    credential_id: Optional[str] = Field(default=None, index=True)
    request_id: str = Field(index=True)
    method: str
    path: str
    resource_type: Optional[str] = Field(default=None, index=True)
    resource_id: Optional[str] = Field(default=None, index=True)
    status_code: int = Field(index=True)
    duration_ms: float
    created_at: datetime = Field(default_factory=utc_now)


class AuthorizationDecision(SQLModel, table=True):
    """A tenant-scoped record of one human API authorization decision."""

    __tablename__ = "authorization_decisions"

    id: str = Field(default_factory=lambda: new_id("authz"), primary_key=True)
    tenant_id: str = Field(index=True)
    subject_id: str = Field(index=True)
    subject_type: str = Field(default="human", index=True)
    role: str = Field(index=True)
    department_id: str = Field(default="", index=True)
    store_id: str = Field(default="", index=True)
    resource_type: str = Field(default="api", index=True)
    object: str = Field(index=True)
    action: str = Field(index=True)
    effect: str = Field(index=True)
    reason: str
    policy_version: str = Field(index=True)
    request_id: str = Field(index=True)
    occurred_at: datetime = Field(default_factory=utc_now, index=True)


class AuthorizationPolicyRelease(SQLModel, table=True):
    """Tenant policy release; published policy content is immutable."""

    __tablename__ = "authorization_policy_releases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "version", name="uq_authorization_policy_release_version"),
        CheckConstraint(
            "status IN ('draft', 'published', 'superseded')",
            name="authorization_policy_releases_status_check",
        ),
        Index(
            "ix_authorization_policy_releases_tenant_status",
            "tenant_id",
            "status",
            "version",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("authz_policy"), primary_key=True)
    tenant_id: str = Field(index=True)
    version: int = Field(index=True)
    status: str = Field(default="draft", index=True)
    policy_text: str
    policy_digest: str = Field(index=True)
    description: str = ""
    source_release_id: Optional[str] = Field(default=None, index=True)
    created_by_user_id: str = Field(index=True)
    published_by_user_id: Optional[str] = Field(default=None, index=True)
    publish_reason: str = ""
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)
    published_at: Optional[datetime] = Field(default=None, index=True)


class AuthorizationPolicyEvent(SQLModel, table=True):
    """Append-only lifecycle evidence for authorization policy releases."""

    __tablename__ = "authorization_policy_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('draft_created', 'draft_updated', 'published', 'rolled_back')",
            name="authorization_policy_events_type_check",
        ),
        Index(
            "ix_authorization_policy_events_tenant_time",
            "tenant_id",
            "occurred_at",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("authz_policy_event"), primary_key=True)
    tenant_id: str = Field(index=True)
    release_id: str = Field(index=True)
    event_type: str = Field(index=True)
    actor_user_id: str = Field(index=True)
    detail_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    occurred_at: datetime = Field(default_factory=utc_now, index=True)


class BusinessResource(SQLModel, table=True):
    """Tenant business master data governed by role-scoped grants."""

    __tablename__ = "business_resources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "resource_type", "code", name="uq_business_resource_code"),
        UniqueConstraint("tenant_id", "id", name="uq_business_resources_tenant_id_id"),
        CheckConstraint(
            "resource_type IN ('store', 'carrier', 'ad_account', 'supplier', "
            "'creator_account', 'partner_account', 'social_account', 'live_room')",
            name="business_resources_type_check",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive', 'archived')",
            name="business_resources_status_check",
        ),
        Index("ix_business_resources_tenant_type_status", "tenant_id", "resource_type", "status"),
    )

    id: str = Field(default_factory=lambda: new_id("bizres"), primary_key=True)
    tenant_id: str = Field(index=True)
    resource_type: str = Field(index=True)
    code: str = Field(index=True)
    name: str
    status: str = Field(default="active", index=True)
    revision: int = Field(default=1)
    created_by_user_id: str = Field(index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class OrganizationUnit(SQLModel, table=True):
    """Tenant-scoped business unit or department used by role-based work queues."""

    __tablename__ = "organization_units"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_organization_unit_tenant_code"),
        CheckConstraint(
            "unit_type IN ('business_unit', 'department')",
            name="organization_units_type_check",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive', 'archived')",
            name="organization_units_status_check",
        ),
        Index("ix_organization_units_tenant_parent", "tenant_id", "parent_id"),
    )

    id: str = Field(default_factory=lambda: new_id("orgunit"), primary_key=True)
    tenant_id: str = Field(index=True)
    parent_id: Optional[str] = Field(default=None, index=True)
    unit_type: str = Field(default="department", index=True)
    code: str = Field(index=True)
    name: str
    status: str = Field(default="active", index=True)
    revision: int = Field(default=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_by_user_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class OrganizationMembership(SQLModel, table=True):
    """A user's tenant-local primary department membership."""

    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "membership_type",
            name="uq_organization_membership_user_type",
        ),
        CheckConstraint(
            "membership_type IN ('primary', 'manager')",
            name="organization_memberships_type_check",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="organization_memberships_status_check",
        ),
        Index("ix_organization_memberships_tenant_unit", "tenant_id", "unit_id"),
    )

    id: str = Field(default_factory=lambda: new_id("orgmember"), primary_key=True)
    tenant_id: str = Field(index=True)
    unit_id: str = Field(index=True)
    user_id: str = Field(index=True)
    business_role: str = Field(index=True)
    membership_type: str = Field(default="primary", index=True)
    source: str = Field(default="casdoor", index=True)
    status: str = Field(default="active", index=True)
    synced_at: datetime = Field(default_factory=utc_now, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ExternalAuthorization(SQLModel, table=True):
    """Secret-free record of a TikTok authorization and its approved scope."""

    __tablename__ = "external_authorizations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "authorization_type",
            "subject_id",
            "resource_id",
            name="uq_external_authorization_subject_resource",
        ),
        CheckConstraint("provider IN ('tiktok')", name="external_authorizations_provider_check"),
        CheckConstraint(
            "authorization_type IN ('seller', 'creator', 'partner', 'ads', 'social')",
            name="external_authorizations_type_check",
        ),
        CheckConstraint(
            "status IN ('active', 'expired', 'revoked', 'error')",
            name="external_authorizations_status_check",
        ),
        Index("ix_external_authorizations_tenant_status", "tenant_id", "status"),
    )

    id: str = Field(default_factory=lambda: new_id("extauth"), primary_key=True)
    tenant_id: str = Field(index=True)
    provider: str = Field(default="tiktok", index=True)
    authorization_type: str = Field(index=True)
    subject_id: str = Field(index=True)
    resource_id: Optional[str] = Field(default=None, index=True)
    scopes_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    credential_ref: Optional[str] = Field(default=None, index=True)
    token_fingerprint: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="active", index=True)
    expires_at: Optional[datetime] = Field(default=None, index=True)
    revision: int = Field(default=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class TikTokOAuthState(SQLModel, table=True):
    """Short-lived state for local or official TikTok authorization."""

    __tablename__ = "tiktok_oauth_states"
    __table_args__ = (
        Index("ix_tiktok_oauth_states_tenant_expires", "tenant_id", "expires_at"),
    )

    state_hash: str = Field(primary_key=True)
    tenant_id: str = Field(index=True)
    user_id: str = Field(index=True)
    authorization_type: str = Field(index=True)
    subject_id: str = Field(index=True)
    resource_id: Optional[str] = Field(default=None, index=True)
    scopes_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    code_challenge: str
    flow: str = Field(default="mock", index=True)
    return_to: str = "/enterprise/tiktok"
    code_hash: Optional[str] = Field(default=None, index=True)
    code_expires_at: Optional[datetime] = Field(default=None, index=True)
    approved_at: Optional[datetime] = Field(default=None, index=True)
    expires_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class TikTokShadowRun(SQLModel, table=True):
    """A fourteen-day read-only observation window before production cutover."""

    __tablename__ = "tiktok_shadow_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'running', 'completed', 'expired', 'cancelled')",
            name="tiktok_shadow_runs_status_check",
        ),
        Index("ix_tiktok_shadow_runs_tenant_status", "tenant_id", "status"),
    )

    id: str = Field(default_factory=lambda: new_id("tiktok_shadow"), primary_key=True)
    tenant_id: str = Field(index=True)
    status: str = Field(default="running", index=True)
    started_at: datetime = Field(default_factory=utc_now, index=True)
    ends_at: datetime = Field(index=True)
    last_heartbeat_at: datetime = Field(default_factory=utc_now, index=True)
    observation_count: int = Field(default=0)
    error_count: int = Field(default=0)
    started_by_user_id: str = Field(index=True)
    baseline_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class ConnectorSyncState(SQLModel, table=True):
    """Durable, tenant-scoped cursor state for read-only connector syncs."""

    __tablename__ = "connector_sync_states"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "connector_type", "resource_id", name="uq_connector_sync_scope"
        ),
        CheckConstraint(
            "status IN ('idle', 'running', 'succeeded', 'failed')",
            name="connector_sync_states_status_check",
        ),
        Index("ix_connector_sync_states_tenant_status", "tenant_id", "status"),
    )

    id: str = Field(default_factory=lambda: new_id("sync"), primary_key=True)
    tenant_id: str = Field(index=True)
    connector_type: str = Field(index=True)
    resource_id: Optional[str] = Field(default=None, index=True)
    cursor_ref: Optional[str] = None
    watermark_at: Optional[datetime] = Field(default=None, index=True)
    status: str = Field(default="idle", index=True)
    last_error_code: Optional[str] = Field(default=None, index=True)
    revision: int = Field(default=1)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class SocialCreator(SQLModel, table=True):
    """Tenant-owned canonical creator profile without private contact details."""

    __tablename__ = "social_creators"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_social_creator_tenant_id"),
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_social_creator_idempotency"
        ),
        CheckConstraint(
            "status IN ('active', 'needs_review', 'archived')",
            name="social_creators_status_check",
        ),
        Index("ix_social_creators_tenant_status", "tenant_id", "status", "updated_at"),
    )

    id: str = Field(default_factory=lambda: new_id("social_creator"), primary_key=True)
    tenant_id: str = Field(index=True)
    canonical_name: str
    status: str = Field(default="active", index=True)
    idempotency_key: str = Field(index=True)
    request_digest: str = Field(index=True)
    created_by_user_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SocialPlatformIdentity(SQLModel, table=True):
    """Public platform identity separated from the tenant-local creator profile."""

    __tablename__ = "social_platform_identities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_social_identity_tenant_id"),
        UniqueConstraint(
            "tenant_id", "id", "creator_id", name="uq_social_identity_creator"
        ),
        UniqueConstraint(
            "tenant_id",
            "platform",
            "provider_identity_id",
            name="uq_social_identity_provider",
        ),
        CheckConstraint(
            "status IN ('active', 'needs_review', 'archived')",
            name="social_platform_identities_status_check",
        ),
        Index(
            "ix_social_identities_tenant_creator",
            "tenant_id",
            "creator_id",
            "platform",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("social_identity"), primary_key=True)
    tenant_id: str = Field(index=True)
    creator_id: str = Field(index=True)
    platform: str = Field(index=True)
    provider_identity_id: str = Field(index=True)
    public_handle: str
    profile_url: Optional[str] = None
    verified: bool = False
    status: str = Field(default="active", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SocialCreatorEvidence(SQLModel, table=True):
    """Versioned, rights-aware evidence used for creator filtering decisions."""

    __tablename__ = "social_creator_evidence"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_social_evidence_idempotency"
        ),
        CheckConstraint("followers_count >= 0", name="social_evidence_followers_check"),
        CheckConstraint(
            "engagement_rate_bps >= 0 AND engagement_rate_bps <= 10000",
            name="social_evidence_engagement_check",
        ),
        CheckConstraint(
            "estimated_cost_minor IS NULL OR estimated_cost_minor >= 0",
            name="social_evidence_cost_check",
        ),
        CheckConstraint(
            "quality_score >= 0 AND quality_score <= 100",
            name="social_evidence_quality_check",
        ),
        CheckConstraint(
            "data_rights_basis IN ('contract_authorized', 'public_business', 'user_provided')",
            name="social_evidence_rights_check",
        ),
        CheckConstraint(
            "contact_basis IN ('none', 'contract_authorized', 'public_business')",
            name="social_evidence_contact_basis_check",
        ),
        CheckConstraint("expires_at > observed_at", name="social_evidence_time_check"),
        CheckConstraint(
            "(estimated_cost_minor IS NULL AND currency IS NULL) OR "
            "(estimated_cost_minor IS NOT NULL AND currency IS NOT NULL)",
            name="social_evidence_cost_currency_check",
        ),
        Index(
            "ix_social_evidence_tenant_identity_observed",
            "tenant_id",
            "identity_id",
            "observed_at",
        ),
        Index("ix_social_evidence_tenant_expiry", "tenant_id", "expires_at"),
    )

    id: str = Field(default_factory=lambda: new_id("social_evidence"), primary_key=True)
    tenant_id: str = Field(index=True)
    creator_id: str = Field(index=True)
    identity_id: str = Field(index=True)
    country_code: Optional[str] = Field(default=None, index=True)
    language_code: Optional[str] = Field(default=None, index=True)
    category: Optional[str] = Field(default=None, index=True)
    followers_count: int = Field(default=0, index=True)
    engagement_rate_bps: int = Field(default=0, index=True)
    audience_country_code: Optional[str] = Field(default=None, index=True)
    estimated_cost_minor: Optional[int] = Field(default=None, index=True)
    currency: Optional[str] = Field(default=None, index=True)
    quality_score: int = Field(default=0, index=True)
    source_ref: str
    data_rights_basis: str = Field(index=True)
    contact_basis: str = Field(default="none", index=True)
    observed_at: datetime = Field(index=True)
    expires_at: datetime = Field(index=True)
    idempotency_key: str = Field(index=True)
    request_digest: str = Field(index=True)
    created_by_user_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)


class SocialAudienceSnapshot(SQLModel, table=True):
    """Immutable brand-scoped result set; freezing it never authorizes outreach."""

    __tablename__ = "social_audience_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "brand_id",
            "idempotency_key",
            name="uq_social_audience_idempotency",
        ),
        CheckConstraint("status = 'frozen'", name="social_audience_status_check"),
        CheckConstraint("creator_count >= 0", name="social_audience_count_check"),
        Index(
            "ix_social_audiences_tenant_brand_created",
            "tenant_id",
            "brand_id",
            "created_at",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("social_audience"), primary_key=True)
    tenant_id: str = Field(index=True)
    brand_id: str = Field(index=True)
    status: str = Field(default="frozen", index=True)
    filters_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    creator_ids_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    identity_ids_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    evidence_ids_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    creator_count: int = Field(default=0)
    audience_hash: str = Field(index=True)
    idempotency_key: str = Field(index=True)
    request_digest: str = Field(index=True)
    created_by_user_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)


class SocialDomainEvent(SQLModel, table=True):
    """Append-only, secret-free audit evidence for social creator decisions."""

    __tablename__ = "social_domain_events"
    __table_args__ = (
        CheckConstraint(
            "aggregate_type IN ('creator', 'creator_evidence', 'audience_snapshot')",
            name="social_domain_events_aggregate_check",
        ),
        Index(
            "ix_social_events_tenant_aggregate_time",
            "tenant_id",
            "aggregate_type",
            "aggregate_id",
            "occurred_at",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("social_event"), primary_key=True)
    tenant_id: str = Field(index=True)
    brand_id: Optional[str] = Field(default=None, index=True)
    aggregate_type: str = Field(index=True)
    aggregate_id: str = Field(index=True)
    event_type: str = Field(index=True)
    actor_user_id: str = Field(index=True)
    request_id: str = Field(index=True)
    detail_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)


class BusinessResourceScope(SQLModel, table=True):
    """A role grant to one business resource; tenant RLS remains the outer boundary."""

    __tablename__ = "business_resource_scopes"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "resource_id", "business_role", name="uq_business_resource_role_scope"
        ),
        CheckConstraint(
            "access_level IN ('viewer', 'operator')",
            name="business_resource_scopes_access_check",
        ),
        Index(
            "ix_business_resource_scopes_tenant_role",
            "tenant_id",
            "business_role",
            "access_level",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("bizscope"), primary_key=True)
    tenant_id: str = Field(index=True)
    resource_id: str = Field(index=True)
    business_role: str = Field(index=True)
    access_level: str = Field(default="operator", index=True)
    created_at: datetime = Field(default_factory=utc_now)


class HighRiskActionRequest(SQLModel, table=True):
    """Approval aggregate for a proposed external side effect."""

    __tablename__ = "high_risk_action_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled', 'invalidated')",
            name="high_risk_action_requests_status_check",
        ),
        Index(
            "ix_high_risk_actions_tenant_status_requested",
            "tenant_id",
            "status",
            "requested_at",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("approval"), primary_key=True)
    tenant_id: str = Field(index=True)
    resource_id: str = Field(index=True)
    resource_type: str = Field(index=True)
    resource_name: str
    action_type: str = Field(index=True)
    summary: str
    payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    content_digest: str = Field(default="", index=True)
    resource_snapshot_digest: str = Field(default="", index=True)
    status: str = Field(default="pending", index=True)
    requester_user_id: str = Field(index=True)
    requester_business_role: str = Field(index=True)
    decided_by_user_id: Optional[str] = Field(default=None, index=True)
    decision_reason: Optional[str] = None
    requested_at: datetime = Field(default_factory=utc_now, index=True)
    decided_at: Optional[datetime] = Field(default=None, index=True)
    invalidated_at: Optional[datetime] = Field(default=None, index=True)
    invalidation_reason: Optional[str] = None
    updated_at: datetime = Field(default_factory=utc_now)


class HighRiskActionEvent(SQLModel, table=True):
    """Append-only evidence for the high-risk approval state machine."""

    __tablename__ = "high_risk_action_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('requested', 'approved', 'rejected', 'cancelled', 'invalidated')",
            name="high_risk_action_events_type_check",
        ),
        Index("ix_high_risk_action_events_request_time", "request_id", "occurred_at"),
    )

    id: str = Field(default_factory=lambda: new_id("approval_event"), primary_key=True)
    tenant_id: str = Field(index=True)
    request_id: str = Field(index=True)
    event_type: str = Field(index=True)
    actor_user_id: str = Field(index=True)
    actor_business_role: str = Field(index=True)
    detail_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    occurred_at: datetime = Field(default_factory=utc_now, index=True)


class BusinessActionExecution(SQLModel, table=True):
    """Durable Saga state for one approved external business operation."""

    __tablename__ = "business_action_executions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "request_id",
            name="uq_business_action_execution_request",
        ),
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_business_action_execution_idempotency",
        ),
        CheckConstraint(
            "environment IN ('sandbox', 'live')",
            name="business_action_executions_environment_check",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'retry_wait', 'succeeded', 'failed', "
            "'compensation_requested', 'compensating', 'compensated', "
            "'compensation_failed', 'manual_resolution_required')",
            name="business_action_executions_status_check",
        ),
        Index(
            "ix_business_action_executions_tenant_due",
            "tenant_id",
            "status",
            "next_attempt_at",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("bizexec"), primary_key=True)
    tenant_id: str = Field(index=True)
    request_id: str = Field(index=True)
    resource_id: str = Field(index=True)
    action_type: str = Field(index=True)
    connector_type: str = Field(index=True)
    environment: str = Field(default="sandbox", index=True)
    workflow_version: int = Field(default=1)
    approval_content_digest: str = Field(default="", index=True)
    resource_snapshot_digest: str = Field(default="", index=True)
    status: str = Field(default="queued", index=True)
    idempotency_key: str = Field(index=True)
    attempt_count: int = Field(default=0)
    compensation_attempt_count: int = Field(default=0)
    max_attempts: int = Field(default=3)
    next_attempt_at: Optional[datetime] = Field(default=None, index=True)
    deadline_at: Optional[datetime] = Field(default=None, index=True)
    lease_owner: Optional[str] = Field(default=None, index=True)
    lease_expires_at: Optional[datetime] = Field(default=None, index=True)
    execution_generation: int = Field(default=0)
    external_operation_id: Optional[str] = Field(default=None, index=True)
    receipt_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    last_error_code: Optional[str] = Field(default=None, index=True)
    last_error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = Field(default=None, index=True)
    compensated_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class BusinessActionExecutionEvent(SQLModel, table=True):
    """Append-only execution, retry, receipt, compensation and operator evidence."""

    __tablename__ = "business_action_execution_events"
    __table_args__ = (
        CheckConstraint(
            "phase IN ('execution', 'compensation', 'reconciliation', 'operator')",
            name="business_action_execution_events_phase_check",
        ),
        Index(
            "ix_business_action_execution_events_execution_time",
            "execution_id",
            "occurred_at",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("bizexec_event"), primary_key=True)
    tenant_id: str = Field(index=True)
    execution_id: str = Field(index=True)
    request_id: str = Field(index=True)
    phase: str = Field(index=True)
    event_type: str = Field(index=True)
    attempt_no: int = Field(default=0)
    actor_type: str = Field(default="system", index=True)
    actor_id: Optional[str] = Field(default=None, index=True)
    actor_business_role: Optional[str] = Field(default=None, index=True)
    detail_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    occurred_at: datetime = Field(default_factory=utc_now, index=True)


class OperationsReport(SQLModel, table=True):
    """Tenant-scoped daily or weekly management snapshot with explicit evidence."""

    __tablename__ = "operations_reports"
    __table_args__ = (
        UniqueConstraint("tenant_id", "report_key", name="uq_operations_report_key"),
        CheckConstraint(
            "report_type IN ('daily', 'weekly')",
            name="operations_reports_type_check",
        ),
        CheckConstraint(
            "status IN ('draft', 'confirmed', 'rejected')",
            name="operations_reports_status_check",
        ),
        Index(
            "ix_operations_reports_tenant_period",
            "tenant_id",
            "report_type",
            "period_start",
            "period_end",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("opsreport"), primary_key=True)
    tenant_id: str = Field(index=True)
    report_key: str = Field(index=True)
    report_type: str = Field(index=True)
    title: str
    status: str = Field(default="draft", index=True)
    timezone: str = Field(default="Asia/Shanghai")
    period_start: datetime = Field(index=True)
    period_end: datetime = Field(index=True)
    scope_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    metrics_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    sections_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    data_status: str = Field(default="partial", index=True)
    source_count: int = Field(default=0)
    generated_by_user_id: str = Field(index=True)
    generated_at: datetime = Field(default_factory=utc_now, index=True)
    reviewed_by_user_id: Optional[str] = Field(default=None, index=True)
    review_note: Optional[str] = None
    reviewed_at: Optional[datetime] = Field(default=None, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class OperationsReportSource(SQLModel, table=True):
    """Evidence link used by one report conclusion; immutable after generation."""

    __tablename__ = "operations_report_sources"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "report_id",
            "source_type",
            "source_id",
            name="uq_operations_report_source",
        ),
        Index("ix_operations_report_sources_report_time", "report_id", "occurred_at"),
    )

    id: str = Field(default_factory=lambda: new_id("opsreport_source"), primary_key=True)
    tenant_id: str = Field(index=True)
    report_id: str = Field(index=True)
    source_type: str = Field(index=True)
    source_id: str = Field(index=True)
    business_key: str = Field(index=True)
    severity: str = Field(default="info", index=True)
    label: str
    summary: str
    source_route: str
    occurred_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now)


class OperationsReportComment(SQLModel, table=True):
    """Append-only management comment, review decision or follow-up request."""

    __tablename__ = "operations_report_comments"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ('comment', 'confirmed', 'rejected', 'follow_up_created')",
            name="operations_report_comments_action_check",
        ),
        Index("ix_operations_report_comments_report_time", "report_id", "created_at"),
    )

    id: str = Field(default_factory=lambda: new_id("opsreport_comment"), primary_key=True)
    tenant_id: str = Field(index=True)
    report_id: str = Field(index=True)
    action_type: str = Field(default="comment", index=True)
    author_user_id: str = Field(index=True)
    author_business_role: str = Field(index=True)
    body: str
    detail_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, index=True)


class BiIngestionBatch(SQLModel, table=True):
    """Auditable BI payload attempt; exact payloads are idempotent within one source window."""

    __tablename__ = "bi_ingestion_batches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_bi_ingestion_batch_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "id",
            "source_key",
            name="uq_bi_ingestion_batch_source_identity",
        ),
        UniqueConstraint(
            "tenant_id",
            "source_key",
            "window_start",
            "window_end",
            "input_digest",
            name="uq_bi_ingestion_batch_payload",
        ),
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'rejected', 'superseded')",
            name="bi_ingestion_batches_status_check",
        ),
        CheckConstraint(
            "quality_status IN ('pending', 'passed', 'failed')",
            name="bi_ingestion_batches_quality_status_check",
        ),
        CheckConstraint(
            "snapshot_mode IN ('full_window', 'incremental')",
            name="bi_ingestion_batches_snapshot_mode_check",
        ),
        CheckConstraint(
            "window_end > window_start",
            name="bi_ingestion_batches_window_check",
        ),
        CheckConstraint(
            "row_count >= 0 AND accepted_count >= 0 AND rejected_count >= 0",
            name="bi_ingestion_batches_count_check",
        ),
        Index(
            "ix_bi_ingestion_batches_tenant_source_window",
            "tenant_id",
            "source_key",
            "window_start",
            "window_end",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("bibatch"), primary_key=True)
    tenant_id: str = Field(index=True)
    source_key: str = Field(index=True)
    window_start: datetime = Field(index=True)
    window_end: datetime = Field(index=True)
    business_timezone: str
    snapshot_mode: str = Field(default="full_window", index=True)
    input_digest: str = Field(index=True)
    status: str = Field(default="pending", index=True)
    quality_status: str = Field(default="pending", index=True)
    row_count: int = Field(default=0)
    accepted_count: int = Field(default=0)
    rejected_count: int = Field(default=0)
    expected_row_count: Optional[int] = None
    expected_gross_sales: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(24, 6), nullable=True),
    )
    expected_ad_spend: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(24, 6), nullable=True),
    )
    actual_gross_sales: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(24, 6), nullable=False),
    )
    actual_ad_spend: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(24, 6), nullable=False),
    )
    reconciliation_tolerance: Decimal = Field(
        default=Decimal("0.01"),
        sa_column=Column(Numeric(24, 6), nullable=False),
    )
    metric_definition_version: str = Field(default="1.0.0")
    latest_source_observed_at: Optional[datetime] = Field(default=None, index=True)
    created_by_user_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now_aware, index=True)
    completed_at: Optional[datetime] = Field(default=None, index=True)


class BiDataQualityCheck(SQLModel, table=True):
    """Append-only deterministic quality and reconciliation evidence for one BI batch."""

    __tablename__ = "bi_data_quality_checks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_bi_quality_check_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "batch_id",
            "check_code",
            name="uq_bi_quality_check_batch_code",
        ),
        CheckConstraint(
            "status IN ('passed', 'failed', 'skipped')",
            name="bi_data_quality_checks_status_check",
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'error')",
            name="bi_data_quality_checks_severity_check",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["bi_ingestion_batches.tenant_id", "bi_ingestion_batches.id"],
            name="bi_quality_checks_batch_fk",
            ondelete="RESTRICT",
        ),
        Index("ix_bi_quality_checks_batch_status", "batch_id", "status"),
    )

    id: str = Field(default_factory=lambda: new_id("biquality"), primary_key=True)
    tenant_id: str = Field(index=True)
    batch_id: str = Field(index=True)
    check_code: str = Field(index=True)
    status: str = Field(index=True)
    severity: str = Field(default="error", index=True)
    observed_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    expected_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    detail: str
    created_at: datetime = Field(default_factory=utc_now_aware, index=True)


class BiDailyCommerceFact(SQLModel, table=True):
    """Versioned source fact at a declared daily business grain; prior versions remain traceable."""

    __tablename__ = "bi_daily_commerce_facts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_bi_daily_fact_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "source_key",
            "external_id",
            "source_version",
            name="uq_bi_daily_fact_source_version",
        ),
        CheckConstraint(
            "entity_type IN ('store', 'asin', 'sku')",
            name="bi_daily_facts_entity_type_check",
        ),
        CheckConstraint(
            "gross_sales >= 0 AND refund_amount >= 0 AND ad_spend >= 0 "
            "AND attributed_ad_sales >= 0",
            name="bi_daily_facts_amount_check",
        ),
        CheckConstraint(
            "impressions >= 0 AND clicks >= 0 AND orders >= 0 "
            "AND available_inventory >= 0 AND rolling_units_sold >= 0 "
            "AND rolling_window_days > 0",
            name="bi_daily_facts_count_check",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id", "source_key"],
            [
                "bi_ingestion_batches.tenant_id",
                "bi_ingestion_batches.id",
                "bi_ingestion_batches.source_key",
            ],
            name="bi_daily_facts_batch_fk",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "replaces_fact_id"],
            ["bi_daily_commerce_facts.tenant_id", "bi_daily_commerce_facts.id"],
            name="bi_daily_facts_replaces_fk",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_bi_daily_facts_current_grain",
            "tenant_id",
            "source_key",
            "business_date",
            "brand_id",
            "store_id",
            "is_current",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("bifact"), primary_key=True)
    tenant_id: str = Field(index=True)
    batch_id: str = Field(index=True)
    source_key: str = Field(index=True)
    external_id: str = Field(index=True)
    source_version: str = Field(index=True)
    content_digest: str = Field(index=True)
    replaces_fact_id: Optional[str] = Field(default=None, index=True)
    is_current: bool = Field(default=True, index=True)
    business_date: date = Field(index=True)
    brand_id: str = Field(index=True)
    store_id: str = Field(index=True)
    platform: str = Field(index=True)
    entity_type: str = Field(index=True)
    entity_id: str = Field(index=True)
    currency: str = Field(index=True)
    gross_sales: Decimal = Field(sa_column=Column(Numeric(24, 6), nullable=False))
    refund_amount: Decimal = Field(sa_column=Column(Numeric(24, 6), nullable=False))
    ad_spend: Decimal = Field(sa_column=Column(Numeric(24, 6), nullable=False))
    attributed_ad_sales: Decimal = Field(
        sa_column=Column(Numeric(24, 6), nullable=False)
    )
    impressions: int = Field(default=0)
    clicks: int = Field(default=0)
    orders: int = Field(default=0)
    available_inventory: int = Field(default=0)
    rolling_units_sold: int = Field(default=0)
    rolling_window_days: int = Field(default=30)
    source_observed_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now_aware, index=True)


class BiMetricDefinition(SQLModel, table=True):
    """Tenant-scoped immutable version of a deterministic metric contract."""

    __tablename__ = "bi_metric_definitions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_bi_metric_definition_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "id",
            "code",
            "version",
            name="uq_bi_metric_definition_identity",
        ),
        UniqueConstraint(
            "tenant_id",
            "code",
            "version",
            name="uq_bi_metric_definition_version",
        ),
        CheckConstraint(
            "status IN ('active', 'retired')",
            name="bi_metric_definitions_status_check",
        ),
        CheckConstraint(
            "attribution_window_days > 0",
            name="bi_metric_definitions_attribution_check",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("bimetricdef"), primary_key=True)
    tenant_id: str = Field(index=True)
    code: str = Field(index=True)
    version: str = Field(index=True)
    name: str
    formula: str
    grain: str
    business_timezone: str
    currency_policy: str
    attribution_window_days: int = Field(default=7)
    status: str = Field(default="active", index=True)
    effective_from: datetime = Field(default_factory=utc_now_aware, index=True)
    created_by_user_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now_aware, index=True)


class BiDailyMetric(SQLModel, table=True):
    """Rebuildable daily aggregate that retains batch, definition and fact selection evidence."""

    __tablename__ = "bi_daily_metrics"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_bi_daily_metric_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "batch_id",
            "metric_definition_id",
            "business_date",
            "entity_type",
            "entity_id",
            "currency",
            name="uq_bi_daily_metric_batch_grain",
        ),
        CheckConstraint(
            "freshness_status IN ('fresh', 'stale', 'unknown')",
            name="bi_daily_metrics_freshness_check",
        ),
        CheckConstraint(
            "entity_type IN ('tenant', 'store')",
            name="bi_daily_metrics_entity_type_check",
        ),
        CheckConstraint(
            "(value IS NOT NULL AND null_reason IS NULL) "
            "OR (value IS NULL AND null_reason IS NOT NULL)",
            name="bi_daily_metrics_value_reason_check",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id", "source_key"],
            [
                "bi_ingestion_batches.tenant_id",
                "bi_ingestion_batches.id",
                "bi_ingestion_batches.source_key",
            ],
            name="bi_daily_metrics_batch_fk",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "metric_definition_id",
                "metric_code",
                "metric_definition_version",
            ],
            [
                "bi_metric_definitions.tenant_id",
                "bi_metric_definitions.id",
                "bi_metric_definitions.code",
                "bi_metric_definitions.version",
            ],
            name="bi_daily_metrics_definition_fk",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_bi_daily_metrics_current_query",
            "tenant_id",
            "business_date",
            "metric_code",
            "entity_type",
            "is_current",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("bimetric"), primary_key=True)
    tenant_id: str = Field(index=True)
    batch_id: str = Field(index=True)
    metric_definition_id: str = Field(index=True)
    metric_code: str = Field(index=True)
    metric_definition_version: str = Field(index=True)
    business_date: date = Field(index=True)
    source_key: str = Field(index=True)
    brand_id: str = Field(default="", index=True)
    store_id: str = Field(default="", index=True)
    platform: str = Field(default="", index=True)
    entity_type: str = Field(index=True)
    entity_id: str = Field(index=True)
    currency: str = Field(default="")
    value: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(24, 6), nullable=True),
    )
    null_reason: Optional[str] = None
    freshness_status: str = Field(default="unknown", index=True)
    latest_source_observed_at: Optional[datetime] = Field(default=None, index=True)
    evidence_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    is_current: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=utc_now_aware, index=True)


class WorkTask(SQLModel, table=True):
    """Cross-department work item owned by one business-role queue."""

    __tablename__ = "work_tasks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_work_task_idempotency"),
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'waiting_input', 'review', 'completed', "
            "'failed', 'cancelled', 'archived')",
            name="work_tasks_status_check",
        ),
        CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')",
            name="work_tasks_priority_check",
        ),
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high', 'critical')",
            name="work_tasks_risk_check",
        ),
        CheckConstraint(
            "control_mode IN ('agent', 'human')",
            name="work_tasks_control_mode_check",
        ),
        Index("ix_work_tasks_tenant_role_status", "tenant_id", "owner_business_role", "status"),
        Index("ix_work_tasks_tenant_due", "tenant_id", "due_at"),
        Index("ix_work_tasks_execution_queue", "tenant_id", "control_mode", "status", "next_attempt_at"),
    )

    id: str = Field(default_factory=lambda: new_id("worktask"), primary_key=True)
    tenant_id: str = Field(index=True)
    idempotency_key: str = Field(index=True)
    source_type: str = Field(default="manual", index=True)
    source_id: Optional[str] = Field(default=None, index=True)
    source_report_id: Optional[str] = Field(default=None, index=True)
    title: str
    description: Optional[str] = None
    owner_business_role: str = Field(index=True)
    assignee_agent_id: Optional[str] = Field(default=None, index=True)
    assigned_by_user_id: str = Field(index=True)
    priority: str = Field(default="normal", index=True)
    risk_level: str = Field(default="medium", index=True)
    status: str = Field(default="pending", index=True)
    control_mode: str = Field(default="agent", index=True)
    cancel_requested: bool = Field(default=False, index=True)
    lease_owner: Optional[str] = Field(default=None, index=True)
    lease_expires_at: Optional[datetime] = Field(default=None, index=True)
    execution_generation: int = Field(default=0)
    attempt_count: int = Field(default=0)
    max_attempts: int = Field(default=3)
    next_attempt_at: Optional[datetime] = Field(default=None, index=True)
    latest_session_id: Optional[str] = Field(default=None, index=True)
    taken_over_by_user_id: Optional[str] = Field(default=None, index=True)
    taken_over_at: Optional[datetime] = Field(default=None)
    last_error_code: Optional[str] = Field(default=None, index=True)
    last_error_message: Optional[str] = None
    result_summary: Optional[str] = None
    scope_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    input_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    due_at: Optional[datetime] = Field(default=None, index=True)
    started_at: Optional[datetime] = Field(default=None, index=True)
    completed_at: Optional[datetime] = Field(default=None, index=True)
    version: int = Field(default=0)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkTaskRun(SQLModel, table=True):
    """One durable, fenced attempt by a digital employee."""

    __tablename__ = "work_task_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "task_id", "attempt_no", name="uq_work_task_run_attempt"),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'retrying', 'failed', 'cancelled', 'stale')",
            name="work_task_runs_status_check",
        ),
        CheckConstraint(
            "execution_mode IN ('sandbox', 'live')",
            name="work_task_runs_execution_mode_check",
        ),
        Index("ix_work_task_runs_task_time", "task_id", "created_at"),
    )

    id: str = Field(default_factory=lambda: new_id("worktask_run"), primary_key=True)
    tenant_id: str = Field(index=True)
    task_id: str = Field(index=True)
    attempt_no: int = Field(index=True)
    generation: int = Field(index=True)
    agent_id: str = Field(index=True)
    session_id: str = Field(index=True)
    service_identity_id: Optional[str] = Field(default=None, index=True)
    execution_snapshot_id: Optional[str] = Field(default=None, index=True)
    snapshot_digest: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="running", index=True)
    execution_mode: str = Field(default="sandbox", index=True)
    result_summary: Optional[str] = None
    error_code: Optional[str] = Field(default=None, index=True)
    error_message: Optional[str] = None
    trace_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    started_at: datetime = Field(default_factory=utc_now, index=True)
    finished_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkTaskExecutionSnapshot(SQLModel, table=True):
    """Append-only, secret-free execution inputs frozen when a Run is claimed."""

    __tablename__ = "work_task_execution_snapshots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "run_id", name="uq_work_task_execution_snapshot_run"),
        Index("ix_work_task_execution_snapshots_task_time", "task_id", "created_at"),
    )

    id: str = Field(default_factory=lambda: new_id("worktask_snapshot"), primary_key=True)
    tenant_id: str = Field(index=True)
    task_id: str = Field(index=True)
    run_id: str = Field(index=True)
    service_identity_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    agent_snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    sop_snapshots_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    knowledge_snapshots_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    tool_snapshots_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    capability_snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    service_identity_snapshot_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    snapshot_digest: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class WorkTaskEvidence(SQLModel, table=True):
    """Append-only evidence copied as a safe reference when a task is created."""

    __tablename__ = "work_task_evidence"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "task_id", "source_type", "source_id", name="uq_work_task_evidence"
        ),
        Index("ix_work_task_evidence_task_time", "task_id", "occurred_at"),
    )

    id: str = Field(default_factory=lambda: new_id("worktask_evidence"), primary_key=True)
    tenant_id: str = Field(index=True)
    task_id: str = Field(index=True)
    source_type: str = Field(index=True)
    source_id: str = Field(index=True)
    severity: str = Field(default="info", index=True)
    label: str
    summary: str
    source_route: str
    occurred_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class WorkTaskEvent(SQLModel, table=True):
    """Append-only task lifecycle event used for trace and recovery."""

    __tablename__ = "work_task_events"
    __table_args__ = (Index("ix_work_task_events_task_time", "task_id", "created_at"),)

    id: str = Field(default_factory=lambda: new_id("worktask_event"), primary_key=True)
    tenant_id: str = Field(index=True)
    task_id: str = Field(index=True)
    event_type: str = Field(index=True)
    actor_type: str = Field(default="human", index=True)
    actor_id: Optional[str] = Field(default=None, index=True)
    actor_business_role: Optional[str] = Field(default=None, index=True)
    from_status: Optional[str] = Field(default=None, index=True)
    to_status: Optional[str] = Field(default=None, index=True)
    detail_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, index=True)


class Skill(SQLModel, table=True):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("tenant_id", "skill_id", name="uq_skill_tenant_skill_id"),)

    id: str = Field(default_factory=lambda: new_id("skill"), primary_key=True)
    tenant_id: str = Field(index=True)
    skill_id: str = Field(index=True)
    version: str = "1.0.0"
    name: str
    business_domain: Optional[str] = None
    description: Optional[str] = None
    content_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    status: str = Field(default="draft", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SkillVersion(SQLModel, table=True):
    __tablename__ = "skill_versions"
    __table_args__ = (UniqueConstraint("tenant_id", "skill_id", "version", name="uq_skill_version"),)

    id: str = Field(default_factory=lambda: new_id("skillver"), primary_key=True)
    tenant_id: str = Field(index=True)
    skill_id: str = Field(index=True)
    version: str = Field(index=True)
    name: str
    business_domain: Optional[str] = None
    description: Optional[str] = None
    content_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    status: str = Field(default="draft", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentSkillBranch(SQLModel, table=True):
    __tablename__ = "agent_skill_branches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", "skill_id", name="uq_agent_skill_branch"),
    )

    id: str = Field(default_factory=lambda: new_id("agentbranch"), primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    skill_id: str = Field(index=True)
    source_skill_id: str = Field(index=True)
    base_version: str = "1.0.0"
    head_version: str = "1.0.0"
    content_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    status: str = Field(default="active", index=True)
    sync_state: str = Field(default="synced", index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentSkillBranchVersion(SQLModel, table=True):
    __tablename__ = "agent_skill_branch_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", "skill_id", "version", name="uq_agent_skill_branch_version"),
    )

    id: str = Field(default_factory=lambda: new_id("agentbranchver"), primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    skill_id: str = Field(index=True)
    source_skill_id: str = Field(index=True)
    version: str = Field(index=True)
    base_version: str = "1.0.0"
    content_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    status: str = Field(default="active", index=True)
    sync_state: str = Field(default="diverged", index=True)
    change_summary: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class GeneralSkill(SQLModel, table=True):
    __tablename__ = "general_skills"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_general_skill_tenant_slug"),)

    id: str = Field(default_factory=lambda: new_id("genskill"), primary_key=True)
    tenant_id: str = Field(index=True)
    slug: str = Field(index=True)
    name: str
    description: Optional[str] = None
    homepage: Optional[str] = None
    skill_markdown: str
    skill_files_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = Field(default="draft", index=True)
    capability_scope: str = Field(default="general", index=True)
    permissions_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    runtime_config_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgeBase(SQLModel, table=True):
    __tablename__ = "knowledge_bases"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_knowledge_base_tenant_name"),)

    id: str = Field(default_factory=lambda: new_id("kb"), primary_key=True)
    tenant_id: str = Field(index=True)
    name: str
    description: Optional[str] = None
    status: str = Field(default="active", index=True)
    capability_scope: str = Field(default="general", index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgeBaseVersion(SQLModel, table=True):
    __tablename__ = "knowledge_base_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "knowledge_base_id", "version", name="uq_knowledge_base_version"),
    )

    id: str = Field(default_factory=lambda: new_id("kbver"), primary_key=True)
    tenant_id: str = Field(index=True)
    knowledge_base_id: str = Field(index=True)
    version: str = Field(default="1.0.0", index=True)
    name: str
    description: Optional[str] = None
    status: str = Field(default="active", index=True)
    capability_scope: str = Field(default="general", index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentKnowledgeBranch(SQLModel, table=True):
    __tablename__ = "agent_knowledge_branches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", "knowledge_base_id", name="uq_agent_knowledge_branch"),
    )

    id: str = Field(default_factory=lambda: new_id("agentkb"), primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    knowledge_base_id: str = Field(index=True)
    base_version: str = "1.0.0"
    head_version: str = "1.0.0"
    status: str = Field(default="active", index=True)
    sync_state: str = Field(default="synced", index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgeDocument(SQLModel, table=True):
    __tablename__ = "knowledge_documents"

    id: str = Field(default_factory=lambda: new_id("kdoc"), primary_key=True)
    tenant_id: str = Field(index=True)
    knowledge_base_id: str = Field(index=True)
    knowledge_base_version_id: Optional[str] = Field(default=None, index=True)
    filename: str
    file_type: str = Field(index=True)
    title: Optional[str] = None
    status: str = Field(default="processing", index=True)
    bucket_count: int = 0
    chunk_count: int = 0
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgeBucket(SQLModel, table=True):
    __tablename__ = "knowledge_buckets"

    id: str = Field(default_factory=lambda: new_id("kbucket"), primary_key=True)
    tenant_id: str = Field(index=True)
    knowledge_base_id: str = Field(index=True)
    knowledge_base_version_id: Optional[str] = Field(default=None, index=True)
    document_id: str = Field(index=True)
    bucket_key: str = Field(index=True)
    title: str
    summary: str
    token_estimate: int = 0
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgeChunk(SQLModel, table=True):
    __tablename__ = "knowledge_chunks"

    id: str = Field(default_factory=lambda: new_id("kchunk"), primary_key=True)
    tenant_id: str = Field(index=True)
    knowledge_base_id: str = Field(index=True)
    knowledge_base_version_id: Optional[str] = Field(default=None, index=True)
    document_id: str = Field(index=True)
    bucket_id: str = Field(index=True)
    chunk_index: int = Field(index=True)
    content: str
    summary: Optional[str] = None
    source_ref: Optional[str] = None
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgeConcept(SQLModel, table=True):
    __tablename__ = "knowledge_concepts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "knowledge_base_version_id",
            "concept_id",
            name="uq_knowledge_concept_version_path",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("kconcept"), primary_key=True)
    tenant_id: str = Field(index=True)
    knowledge_base_id: str = Field(index=True)
    knowledge_base_version_id: Optional[str] = Field(default=None, index=True)
    document_id: Optional[str] = Field(default=None, index=True)
    concept_id: str = Field(index=True)
    concept_type: str = Field(index=True)
    title: str
    description: Optional[str] = None
    content_md: str
    frontmatter_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    links_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    citations_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    source_refs_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = Field(default="active", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgeDiscoverySuggestion(SQLModel, table=True):
    __tablename__ = "knowledge_discovery_suggestions"

    id: str = Field(default_factory=lambda: new_id("kdisc"), primary_key=True)
    tenant_id: str = Field(index=True)
    knowledge_base_id: str = Field(index=True)
    knowledge_base_version_id: Optional[str] = Field(default=None, index=True)
    document_id: str = Field(index=True)
    bucket_id: Optional[str] = Field(default=None, index=True)
    suggestion_type: str = Field(index=True)
    title: str
    status: str = Field(default="pending", index=True)
    payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    source_refs_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    reason: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgeIngestJob(SQLModel, table=True):
    __tablename__ = "knowledge_ingest_jobs"

    id: str = Field(default_factory=lambda: new_id("kjob"), primary_key=True)
    tenant_id: str = Field(index=True)
    knowledge_base_id: str = Field(index=True)
    knowledge_base_version_id: Optional[str] = Field(default=None, index=True)
    document_id: Optional[str] = Field(default=None, index=True)
    filename: str
    status: str = Field(default="queued", index=True)
    stage: str = "queued"
    progress: float = 0.0
    error: Optional[str] = None
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=utc_now)


class ModelConfig(SQLModel, table=True):
    __tablename__ = "model_configs"

    id: str = Field(default_factory=lambda: new_id("model"), primary_key=True)
    tenant_id: str = Field(index=True)
    name: str
    provider: str = "openai_compatible"
    api_protocol: str = Field(default="openai_chat_completions", index=True)
    base_url: Optional[str] = None
    api_key_encrypted: str
    model: str
    temperature: float = 0.2
    max_output_tokens: int = 8192
    extra_body_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    protocol_options_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    legacy_unmapped_options_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    trust_status: str = Field(default="unverified", index=True)
    verified_at: Optional[datetime] = None
    verified_fingerprint: Optional[str] = None
    verification_attempt_id: Optional[str] = None
    verification_started_at: Optional[datetime] = None
    verification_attempt_status: str = Field(default="idle", index=True)
    verification_attempt_error_code: Optional[str] = None
    config_revision: int = 1
    security_revision: int = 1
    key_revision: int = 1
    is_default: bool = False
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PersonaConfig(SQLModel, table=True):
    __tablename__ = "persona_configs"

    tenant_id: str = Field(primary_key=True)
    system_prompt: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class UIConfig(SQLModel, table=True):
    __tablename__ = "ui_configs"

    tenant_id: str = Field(primary_key=True)
    show_thinking_trace: bool = True
    show_skill_trace: bool = True
    show_tool_trace: bool = True
    reflection_max_rounds: int = 1
    agent_loop_max_actions: int = 32
    context_token_budget: int = 32_000
    context_compaction_trigger_ratio: float = 0.70
    context_recent_round_limit: int = 6
    context_long_summary_token_budget: int = 4_000
    context_medium_summary_token_budget: int = 4_000
    context_allowed_roles: list[str] = Field(
        default_factory=lambda: ["user", "assistant"],
        sa_column=Column(JSON),
    )
    context_long_summary_prefix: str = "历史的信息可以被总结为："
    context_medium_summary_prefix: str = "近期的历史信息总结为："
    sandbox_enabled: bool = False
    sandbox_network_mode: str = Field(default="all")
    sandbox_allowed_domains: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    harness_storage_path: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentProfile(SQLModel, table=True):
    __tablename__ = "agent_profiles"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_agent_profile_tenant_name"),)

    id: str = Field(default_factory=lambda: new_id("agent"), primary_key=True)
    tenant_id: str = Field(index=True)
    name: str
    description: Optional[str] = None
    persona_prompt: Optional[str] = None
    is_overall: bool = Field(default=False, index=True)
    status: str = Field(default="active", index=True)
    release_state: str = Field(default="draft", index=True)
    published_release_id: Optional[str] = Field(default=None, index=True)
    published_release_version: int = Field(default=0, index=True)
    harness_max_actions: int = Field(default=32)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentRelease(SQLModel, table=True):
    """Immutable production configuration snapshot for one digital employee."""

    __tablename__ = "agent_releases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", "version", name="uq_agent_release_version"),
        CheckConstraint(
            "status IN ('published', 'superseded')",
            name="agent_releases_status_check",
        ),
        Index("ix_agent_releases_tenant_agent_status", "tenant_id", "agent_id", "status"),
    )

    id: str = Field(default_factory=lambda: new_id("agent_release"), primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    version: int = Field(index=True)
    status: str = Field(default="published", index=True)
    snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    snapshot_digest: str = Field(index=True)
    source_release_id: Optional[str] = Field(default=None, index=True)
    created_by_user_id: str = Field(index=True)
    release_reason: str
    created_at: datetime = Field(default_factory=utc_now, index=True)
    published_at: datetime = Field(default_factory=utc_now, index=True)


class AgentReleaseEvent(SQLModel, table=True):
    """Append-only release, rollback, and lifecycle evidence."""

    __tablename__ = "agent_release_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('published', 'rolled_back', 'draft_changed', 'deactivated')",
            name="agent_release_events_type_check",
        ),
        Index("ix_agent_release_events_tenant_agent_time", "tenant_id", "agent_id", "occurred_at"),
    )

    id: str = Field(default_factory=lambda: new_id("agent_release_event"), primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    release_id: Optional[str] = Field(default=None, index=True)
    event_type: str = Field(index=True)
    actor_user_id: str = Field(index=True)
    detail_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    occurred_at: datetime = Field(default_factory=utc_now, index=True)


class AgentServiceIdentity(SQLModel, table=True):
    """Tenant-scoped non-human identity bound to exactly one digital employee."""

    __tablename__ = "agent_service_identities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", name="uq_agent_service_identity_agent"),
        UniqueConstraint("provider", "client_id", name="uq_agent_service_identity_client"),
        CheckConstraint(
            "status IN ('active', 'disabled', 'error')",
            name="agent_service_identities_status_check",
        ),
        Index("ix_agent_service_identities_tenant_role", "tenant_id", "business_role", "status"),
    )

    id: str = Field(default_factory=lambda: new_id("agent_identity"), primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    business_role: str = Field(index=True)
    provider: str = Field(default="casdoor", index=True)
    issuer: str
    token_endpoint: str
    jwks_uri: str
    application_owner: str
    application_name: str = Field(index=True)
    client_id: str = Field(index=True)
    client_id_fingerprint: str = Field(index=True)
    credential_ref: str
    status: str = Field(default="active", index=True)
    token_ttl_seconds: int = Field(default=900)
    last_verified_at: Optional[datetime] = Field(default=None, index=True)
    last_verified_subject: Optional[str] = None
    last_error_code: Optional[str] = Field(default=None, index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentUsage(SQLModel, table=True):
    __tablename__ = "agent_usages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "agent_id", name="uq_agent_usage_user_agent"),
    )

    id: str = Field(default_factory=lambda: new_id("agentuse"), primary_key=True)
    tenant_id: str = Field(index=True)
    user_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentModelBinding(SQLModel, table=True):
    __tablename__ = "agent_model_bindings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", "role", name="uq_agent_model_binding"),
    )

    id: str = Field(default_factory=lambda: new_id("agentmodel"), primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    role: str = Field(default="default", index=True)
    model_config_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentResourceBinding(SQLModel, table=True):
    __tablename__ = "agent_resource_bindings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", "resource_type", "resource_id", name="uq_agent_resource"),
    )

    id: str = Field(default_factory=lambda: new_id("agentres"), primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    resource_type: str = Field(index=True)
    resource_id: str = Field(index=True)
    status: str = Field(default="active", index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Tool(SQLModel, table=True):
    __tablename__ = "tools"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_tool_tenant_name"),)

    id: str = Field(default_factory=lambda: new_id("tool"), primary_key=True)
    tenant_id: str = Field(index=True)
    name: str = Field(index=True)
    display_name: Optional[str] = None
    description: Optional[str] = None
    bucket: str = Field(default="未分桶", index=True)
    tool_type: str = Field(default="http", index=True)
    method: str
    url: str
    headers_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    auth_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    config_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    input_schema: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    output_schema: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    allowed_skills_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    mcp_server_id: Optional[str] = Field(default=None, index=True)
    capability_scope: str = Field(default="general", index=True)
    capability_scope_inherited: bool = True
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MCPServer(SQLModel, table=True):
    __tablename__ = "mcp_servers"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_mcp_server_tenant_name"),)

    id: str = Field(default_factory=lambda: new_id("mcpsrv"), primary_key=True)
    tenant_id: str = Field(index=True)
    name: str = Field(index=True)
    display_name: Optional[str] = None
    description: Optional[str] = None
    bucket: str = Field(default="MCP 工具", index=True)
    # 连接方式：stdio / streamable_http / sse / builtin
    transport: str = Field(default="streamable_http", index=True)
    # streamable_http / sse 使用
    url: Optional[str] = None
    headers_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # stdio 使用
    command: Optional[str] = None
    args_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    env_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    cwd: Optional[str] = None
    # MCP Apps is opt-in so legacy standard MCP servers retain identical behavior.
    apps_mode: str = Field(default="disabled", index=True)
    negotiated_capabilities_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
    # 最近一次发现的原始工具定义（预览/审计用）
    discovered_tools_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    last_synced_at: Optional[datetime] = None
    capability_scope: str = Field(default="general", index=True)
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MockOrder(SQLModel, table=True):
    __tablename__ = "mock_orders"

    order_id: str = Field(primary_key=True)
    user_id: Optional[str] = Field(default=None, index=True)
    product_id: Optional[str] = Field(default=None, index=True)
    sku_id: Optional[str] = None
    quantity: int = 1
    status: str = Field(default="created", index=True)
    payment_status: Optional[str] = None
    order_status: Optional[str] = None
    signed_days: int = 0
    refundable: bool = True
    total_amount: float = 0.0
    currency: str = "CNY"
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ChatSession(SQLModel, table=True):
    __tablename__ = "sessions"

    id: str = Field(primary_key=True)
    tenant_id: str = Field(index=True)
    user_id: Optional[str] = Field(default=None, index=True)
    agent_id: Optional[str] = Field(default=None, index=True)
    title: Optional[str] = None
    active_skill_id: Optional[str] = None
    active_step_id: Optional[str] = None
    slots_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    skill_stack_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    pending_tasks_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    resume_after_answer_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    awaiting_input_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    knowledge_context_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    context_state_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    summary: Optional[str] = None
    last_agent_question: Optional[str] = None
    status: str = "active"
    channel: Optional[str] = None
    external_conv_id: Optional[str] = None
    channel_target_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    # 渠道会话直挂绑定:出站 staging 优先按它直查,不再靠 (agent_id, channel) 反查
    channel_binding_id: Optional[str] = None
    # 渠道外部账号稳定键:绑定删除后仍保留,仅允许同一外部 Bot 精确认领历史会话
    channel_account_key: Optional[str] = Field(default=None, index=True)
    # 团队会话挂接:非空表示该会话属于某团队(TL 对话/任务执行等)
    team_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ChannelBinding(SQLModel, table=True):
    __tablename__ = "channel_bindings"

    id: str = Field(default_factory=lambda: new_id("chan"), primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    channel: str = Field(default="wechat", index=True)
    # 用户可编辑的接入显示名;为空时前端回退展示渠道类型名
    name: Optional[str] = Field(default=None)
    # 团队绑定:非空表示该渠道接入某团队(与员工挂载互斥),入站消息直路由团队 TL;
    # 存 team_id 不存 leader,换帅自动跟随
    team_id: Optional[str] = Field(default=None, index=True)
    # pending/active/expired/disabled
    status: str = Field(default="pending", index=True)
    # Fernet 加密后的渠道凭证（如微信 bot_token），绝不回传明文
    credentials_enc: Optional[str] = None
    # ilink_bot_id、baseurl、get_updates_buf 游标、session_expired、bound_at 等
    config_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # provider 侧 Bot 的稳定连接键,全部署唯一;pending 绑定激活前允许为空
    external_account_key: Optional[str] = Field(default=None, unique=True, index=True)
    # 身份作用域稳定键:企微为 corp_id,微信为空字符串
    identity_scope_key: Optional[str] = Field(default=None, index=True)
    # provider 回调声明的租户边界；飞书首次可信事件中 CAS 固定 tenant_key
    provider_tenant_key: Optional[str] = Field(default=None, index=True)
    # 每次凭证/账号配置成功提交后递增,用于 ingress 代际隔离
    config_revision: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    connected: bool = False
    # 最近一次成功连上渠道的时间(企微断开超时告警的时间基准)
    last_connected_at: Optional[datetime] = None
    created_by_user_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ChannelBindingAgent(SQLModel, table=True):
    """渠道账号可调度的员工集合（一个微信号挂载多个数字员工，恰好一个默认）。"""

    __tablename__ = "channel_binding_agents"
    __table_args__ = (UniqueConstraint("binding_id", "agent_id", name="uq_channel_binding_agent"),)

    id: str = Field(default_factory=lambda: new_id("chba"), primary_key=True)
    tenant_id: str = Field(index=True)
    binding_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    is_default: bool = False
    sort_order: int = 0
    created_at: datetime = Field(default_factory=utc_now)


class ChannelBindingManager(SQLModel, table=True):
    """渠道绑定协作者:创建者/admin 显式授权的非创建者,可凭证/挂载/启停但不能删除。

    同一 (binding, user) 仅一行;移除即软撤销(revoked_at),重新添加复活该行,
    保留最近一次授权/撤销记录用于审计。删除渠道绑定级联清空协作者行。
    """

    __tablename__ = "channel_binding_managers"
    __table_args__ = (
        UniqueConstraint("binding_id", "user_id", name="uq_channel_binding_manager"),
        Index("ix_channel_binding_managers_tenant_user", "tenant_id", "user_id"),
    )

    id: str = Field(default_factory=lambda: new_id("chbm"), primary_key=True)
    tenant_id: str = Field(index=True)
    binding_id: str = Field(index=True)
    user_id: str = Field(index=True)
    granted_by_user_id: str
    granted_at: datetime = Field(default_factory=utc_now)
    revoked_at: Optional[datetime] = None


class ChannelConvState(SQLModel, table=True):
    """路由指针：每个 (binding, external_conv_id) 会话的当前员工。"""

    __tablename__ = "channel_conv_states"
    __table_args__ = (
        UniqueConstraint("binding_id", "external_conv_id", name="uq_channel_conv_state"),
    )

    id: str = Field(default_factory=lambda: new_id("chconv"), primary_key=True)
    tenant_id: str = Field(index=True)
    binding_id: str = Field(index=True)
    external_conv_id: str
    current_agent_id: str
    # 路由指针版本；自动路由分类完成后必须以此做 CAS，避免覆盖期间的手动切换。
    routing_revision: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    # 手动 /切换 后的保护窗:此时间之前跳过智能自动分发
    manual_pin_until: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ChannelBindCode(SQLModel, table=True):
    """渠道身份自助绑定码:网页端生成,渠道侧 /绑定 <码> 核销。"""

    __tablename__ = "channel_bind_codes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_channel_bind_code_tenant_code"),
        UniqueConstraint("tenant_id", "user_id", name="uq_channel_bind_code_tenant_user"),
    )

    id: str = Field(default_factory=lambda: new_id("chbc"), primary_key=True)
    tenant_id: str = Field(index=True)
    user_id: str = Field(index=True)
    code: str = Field(index=True)
    expires_at: datetime
    used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)


class ChannelIdentity(SQLModel, table=True):
    __tablename__ = "channel_identities"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "channel",
            "external_account_scope",
            "external_user_id",
            name="uq_channel_identity_scope_external",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("chident"), primary_key=True)
    tenant_id: str = Field(index=True)
    channel: str = Field(index=True)
    # 渠道账号作用域:wechat 置空(全局 wxid);wecom 取 corp_id/bot_id/binding.id,隔离跨企业身份
    external_account_scope: str = Field(default="", index=True)
    external_user_id: str
    staffdeck_user_id: str = Field(index=True)
    display_name: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ChannelInboundEvent(SQLModel, table=True):
    __tablename__ = "channel_inbound_events"
    __table_args__ = (
        UniqueConstraint("binding_id", "event_id", name="uq_channel_inbound_event_binding"),
        Index(
            "ix_channel_inbound_events_binding_status_created",
            "binding_id",
            "status",
            "created_at",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("chevt"), primary_key=True)
    tenant_id: str = Field(index=True)
    binding_id: str = Field(index=True)
    channel: str = Field(index=True)
    event_id: str
    payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # 入站时的绑定配置代次，仅用于 ingress 代际审计；已落库事件不因后续轮换失效
    config_revision: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    # 每条事件不可变的回复目标；异步处理不得读取会话上的可变 target
    target_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default="{}"),
    )
    # 收到确认标记的句柄；最终回复送达后据此异步撤回。飞书存远端 reaction_id；
    # 钉钉 emotion 接口不返回 ID，存本地哨兵值表示"已挂上待撤回"。
    reaction_id: Optional[str] = Field(default=None, index=True)
    # received/processing/done/failed
    status: str = Field(default="received", index=True)
    # 创建/接管该事件的进程启动代次；当前代次仍在运行时禁止按墙钟误接管。
    processor_run_id: Optional[str] = Field(default=None, index=True)
    processor_lease_expires_at: Optional[datetime] = Field(default=None, index=True)
    error: Optional[str] = None
    processed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ChannelDelivery(SQLModel, table=True):
    __tablename__ = "channel_deliveries"

    id: str = Field(default_factory=lambda: new_id("chdlv"), primary_key=True)
    tenant_id: str = Field(index=True)
    binding_id: str = Field(index=True)
    session_id: str = Field(index=True)
    message_id: Optional[str] = Field(default=None, index=True)
    # 投递目标：to_user_id + context_token
    target_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # reply/error_notice
    kind: str = Field(default="reply", index=True)
    text: str
    # pending/sending/delivered/failed
    status: str = Field(default="pending", index=True)
    attempts: int = 0
    next_attempt_at: Optional[datetime] = Field(default=None, index=True)
    # 原子 claim 的抢占时间(守护据此重置卡死投递)
    sending_since: Optional[datetime] = None
    # 每次领取投递都会生成新的 owner 并递增 generation；旧 worker 的迟到结果不得落库。
    delivery_owner: Optional[str] = Field(default=None, index=True)
    delivery_generation: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    last_error: Optional[str] = None
    # 回复类投递 = message_id，天然幂等
    idempotency_key: str = Field(unique=True, index=True)
    # 第一次真正尝试远端发送的时间，用于飞书 UUID 一小时去重窗口
    first_attempt_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class HumanHandoffRequest(SQLModel, table=True):
    __tablename__ = "human_handoff_requests"

    id: str = Field(default_factory=lambda: new_id("handoff"), primary_key=True)
    tenant_id: str = Field(index=True)
    session_id: str = Field(index=True)
    agent_id: Optional[str] = Field(default=None, index=True)
    requester_user_id: Optional[str] = Field(default=None, index=True)
    assignee_user_id: Optional[str] = Field(default=None, index=True)
    trigger_skill_id: Optional[str] = Field(default=None, index=True)
    trigger_step_id: Optional[str] = Field(default=None, index=True)
    context_summary: Optional[str] = None
    pending_question: Optional[str] = None
    status: str = Field(default="pending", index=True)
    human_reply: Optional[str] = None
    resume_payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    answered_at: Optional[datetime] = None
    # 飞书 handoff_notice 投递成功后回写的飞书 message_id;阶段 4 据此关联处理人回复。
    # 网页触发的 handoff 无此字段(为空),不影响现有网页回复链路。
    notify_message_id: Optional[str] = Field(default=None, index=True)


class ScheduledTask(SQLModel, table=True):
    __tablename__ = "scheduled_tasks"

    id: str = Field(default_factory=lambda: new_id("sched"), primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    created_by_user_id: str = Field(index=True)
    title: str
    prompt: str
    description: Optional[str] = None
    schedule_type: str = Field(default="daily", index=True)
    schedule_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    timezone: str = Field(default="Asia/Shanghai", index=True)
    rrule: Optional[str] = None
    status: str = Field(default="active", index=True)
    concurrency_policy: str = Field(default="forbid", index=True)
    misfire_policy: str = Field(default="coalesce", index=True)
    max_runs: Optional[int] = None
    end_at: Optional[datetime] = Field(default=None, index=True)
    next_run_at: Optional[datetime] = Field(default=None, index=True)
    last_run_at: Optional[datetime] = Field(default=None, index=True)
    last_status: Optional[str] = Field(default=None, index=True)
    run_count: int = 0
    lease_owner: Optional[str] = Field(default=None, index=True)
    lease_until: Optional[datetime] = Field(default=None, index=True)
    source_session_id: Optional[str] = Field(default=None, index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ScheduledTaskRun(SQLModel, table=True):
    __tablename__ = "scheduled_task_runs"
    __table_args__ = (
        UniqueConstraint("scheduled_task_id", "scheduled_for", name="uq_scheduled_task_run_due_time"),
    )

    id: str = Field(default_factory=lambda: new_id("schedrun"), primary_key=True)
    tenant_id: str = Field(index=True)
    scheduled_task_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    user_id: str = Field(index=True)
    session_id: Optional[str] = Field(default=None, index=True)
    scheduled_for: datetime = Field(index=True)
    status: str = Field(default="queued", index=True)
    started_at: Optional[datetime] = Field(default=None, index=True)
    finished_at: Optional[datetime] = Field(default=None, index=True)
    result_summary: Optional[str] = None
    error: Optional[str] = None
    trace_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class HarnessAgentLoopRecord(SQLModel, table=True):
    """Durable logical AgentLoop shared across Harness activations."""

    __tablename__ = "harness_agent_loops"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "loop_key", name="uq_harness_agent_loop_session_key"
        ),
    )

    id: str = Field(default_factory=lambda: new_id("hloop"), primary_key=True)
    tenant_id: str = Field(index=True)
    session_id: str = Field(index=True)
    loop_key: str = Field(index=True)
    kind: str = Field(default="general", index=True)
    status: str = Field(default="active", index=True)
    owner_task_frame_record_id: Optional[str] = Field(default=None, index=True)
    skill_id: Optional[str] = Field(default=None, index=True)
    workspace_scope_id: Optional[str] = Field(default=None, index=True)
    checkpoint_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    last_run_id: Optional[str] = Field(default=None, index=True)
    state_version: int = 1
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    finished_at: Optional[datetime] = None


class HarnessTaskFrameRecord(SQLModel, table=True):
    """Durable TaskFrame state for the isolated Harness v2 execution path."""

    __tablename__ = "harness_task_frames"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "task_id", name="uq_harness_task_frame_session_task"
        ),
    )

    id: str = Field(default_factory=lambda: new_id("htask"), primary_key=True)
    tenant_id: str = Field(index=True)
    session_id: str = Field(index=True)
    source_turn_id: str = Field(index=True)
    task_id: str = Field(index=True)
    agent_loop_id: Optional[str] = Field(default=None, index=True)
    kind: str = Field(default="conversation", index=True)
    decision: str = Field(default="answer_only", index=True)
    status: str = Field(default="queued", index=True)
    sequence: int = 0
    skill_id: Optional[str] = Field(default=None, index=True)
    step_id: Optional[str] = Field(default=None, index=True)
    user_intent: Optional[str] = None
    requirements_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    slots_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    depends_on_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    task_requirement_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    result_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    error_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    state_version: int = 1
    attempt_no: int = 0
    lease_owner: Optional[str] = Field(default=None, index=True)
    lease_expires_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class HarnessRunRecord(SQLModel, table=True):
    __tablename__ = "harness_runs"

    id: str = Field(default_factory=lambda: new_id("hrun"), primary_key=True)
    tenant_id: str = Field(index=True)
    session_id: str = Field(index=True)
    task_frame_record_id: str = Field(index=True)
    agent_loop_id: Optional[str] = Field(default=None, index=True)
    task_id: str = Field(index=True)
    source_turn_id: str = Field(index=True)
    status: str = Field(default="running", index=True)
    attempt_no: int = 1
    lease_owner: Optional[str] = Field(default=None, index=True)
    lease_expires_at: Optional[datetime] = Field(default=None, index=True)
    action_count: int = 0
    task_requirement_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    capability_snapshot_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    result_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class HarnessTurnRecord(SQLModel, table=True):
    """Exactly-once receipt for one client-addressable Harness turn."""

    __tablename__ = "harness_turns"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "session_id",
            "client_turn_id",
            name="uq_harness_turn_client_receipt",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("hturn"), primary_key=True)
    tenant_id: str = Field(index=True)
    session_id: str = Field(index=True)
    client_turn_id: str = Field(index=True)
    request_digest: str = Field(index=True)
    status: str = Field(default="started", index=True)
    lease_owner: str = Field(index=True)
    lease_expires_at: datetime = Field(index=True)
    user_message_id: Optional[str] = Field(default=None, index=True)
    response_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
    error_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class HarnessSessionLeaseRecord(SQLModel, table=True):
    """Cross-process execution fence for one Harness chat session."""

    __tablename__ = "harness_session_leases"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "session_id",
            name="uq_harness_session_execution_lease",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("hslease"), primary_key=True)
    tenant_id: str = Field(index=True)
    session_id: str = Field(index=True)
    lease_owner: str = Field(index=True)
    lease_expires_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class HarnessInvocationRecord(SQLModel, table=True):
    __tablename__ = "harness_invocations"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "call_id", name="uq_harness_invocation_run_call"
        ),
    )

    id: str = Field(default_factory=lambda: new_id("hinvoke"), primary_key=True)
    tenant_id: str = Field(index=True)
    session_id: str = Field(index=True)
    task_id: str = Field(index=True)
    run_id: str = Field(index=True)
    call_id: str = Field(index=True)
    tool_name: str = Field(index=True)
    request_digest: str = Field(index=True)
    logical_action_key: Optional[str] = Field(
        default=None,
        unique=True,
        index=True,
    )
    replayed_from_invocation_id: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="started", index=True)
    arguments_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    result_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    response_cache_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
    approval_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: str = Field(default_factory=lambda: new_id("msg"), primary_key=True)
    tenant_id: str = Field(index=True)
    session_id: str = Field(index=True)
    role: str
    content: str
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)


class MessageFeedback(SQLModel, table=True):
    __tablename__ = "message_feedback"
    __table_args__ = (UniqueConstraint("tenant_id", "message_id", "user_id", name="uq_feedback_message_user"),)

    id: str = Field(default_factory=lambda: new_id("fb"), primary_key=True)
    tenant_id: str = Field(index=True)
    session_id: str = Field(index=True)
    message_id: str = Field(index=True)
    user_id: str = Field(index=True)
    rating: str = Field(index=True)
    analysis_status: str = Field(default="pending", index=True)
    analysis_bucket: Optional[str] = Field(default=None, index=True)
    analysis_reason: Optional[str] = None
    analysis_summary: Optional[str] = None
    analysis_confidence: Optional[float] = None
    analysis_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    analyzed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SkillFeedback(SQLModel, table=True):
    __tablename__ = "skill_feedback"
    __table_args__ = (UniqueConstraint("tenant_id", "message_id", "user_id", name="uq_skill_feedback_message_user"),)

    id: str = Field(default_factory=lambda: new_id("skillfb"), primary_key=True)
    tenant_id: str = Field(index=True)
    skill_id: str = Field(index=True)
    skill_version: Optional[str] = Field(default=None, index=True)
    step_id: Optional[str] = Field(default=None, index=True)
    session_id: str = Field(index=True)
    message_id: str = Field(index=True)
    user_id: str = Field(index=True)
    rating: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class EvolutionProposal(SQLModel, table=True):
    __tablename__ = "evolution_proposals"

    id: str = Field(default_factory=lambda: new_id("evo"), primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    resource_type: str = Field(index=True)
    resource_id: str = Field(index=True)
    resource_key: str = Field(index=True)
    resource_name: str
    base_version: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="ready_for_review", index=True)
    trigger_type: str = Field(default="feedback", index=True)
    risk_level: str = Field(default="medium", index=True)
    hypothesis: str = ""
    rationale: str = ""
    expected_outcome: str = ""
    source_feedback_ids_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    evidence_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    candidate_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    diff_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    evaluation_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    published_snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    error: Optional[str] = None
    created_by_user_id: str = Field(index=True)
    reviewed_by_user_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    reviewed_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    rolled_back_at: Optional[datetime] = None


class AgentEvent(SQLModel, table=True):
    __tablename__ = "agent_events"

    id: str = Field(default_factory=lambda: new_id("evt"), primary_key=True)
    tenant_id: str = Field(index=True)
    session_id: str = Field(index=True)
    event_type: str = Field(index=True)
    payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)


class MemoryRecord(SQLModel, table=True):
    __tablename__ = "memories"

    id: str = Field(default_factory=lambda: new_id("mem"), primary_key=True)
    tenant_id: str = Field(index=True)
    user_id: str = Field(index=True)
    username: Optional[str] = Field(default=None, index=True)
    session_id: Optional[str] = Field(default=None, index=True)
    kind: str = Field(default="conversation", index=True)
    content: str
    importance: float = 0.5
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MemoryReviewRequest(SQLModel, table=True):
    """User-authorized, point-in-time review of one private memory snapshot."""

    __tablename__ = "memory_review_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_memory_review_idempotency"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled', 'invalidated')",
            name="memory_review_requests_status_check",
        ),
        Index("ix_memory_review_tenant_status_time", "tenant_id", "status", "requested_at"),
    )

    id: str = Field(default_factory=lambda: new_id("memreview"), primary_key=True)
    tenant_id: str = Field(index=True)
    memory_id: str = Field(index=True)
    memory_owner_user_id: str = Field(index=True)
    agent_id: Optional[str] = Field(default=None, index=True)
    idempotency_key: str = Field(index=True)
    memory_digest: str = Field(index=True)
    memory_snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = Field(default="pending", index=True)
    requester_user_id: str = Field(index=True)
    request_note: Optional[str] = None
    decided_by_user_id: Optional[str] = Field(default=None, index=True)
    decision_note: Optional[str] = None
    requested_at: datetime = Field(default_factory=utc_now, index=True)
    decided_at: Optional[datetime] = Field(default=None, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class MemoryReviewEvent(SQLModel, table=True):
    """Append-only evidence for personal-memory review decisions."""

    __tablename__ = "memory_review_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('submitted', 'approved', 'rejected', 'cancelled', 'invalidated')",
            name="memory_review_events_type_check",
        ),
        Index("ix_memory_review_events_request_time", "review_request_id", "occurred_at"),
    )

    id: str = Field(default_factory=lambda: new_id("memreview_event"), primary_key=True)
    tenant_id: str = Field(index=True)
    review_request_id: str = Field(index=True)
    event_type: str = Field(index=True)
    actor_user_id: str = Field(index=True)
    actor_business_role: str = Field(index=True)
    detail_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    occurred_at: datetime = Field(default_factory=utc_now, index=True)


class AfterSalesCase(SQLModel, table=True):
    """Tenant-scoped after-sales aggregate from intake through reviewed resolution."""

    __tablename__ = "after_sales_cases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "case_key", name="uq_after_sales_case_key"),
        CheckConstraint(
            "status IN ('intake', 'queried', 'classified', 'drafted', "
            "'waiting_approval', 'needs_human', 'closed', 'rejected')",
            name="after_sales_cases_status_check",
        ),
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high', 'critical')",
            name="after_sales_cases_risk_check",
        ),
        Index("ix_after_sales_cases_tenant_status_updated", "tenant_id", "status", "updated_at"),
        Index("ix_after_sales_cases_tenant_store", "tenant_id", "store_resource_id"),
    )

    id: str = Field(default_factory=lambda: new_id("aftersales"), primary_key=True)
    tenant_id: str = Field(index=True)
    case_key: str = Field(index=True)
    store_resource_id: str = Field(index=True)
    store_code: str = Field(index=True)
    platform: str = Field(index=True)
    marketplace_country: str = Field(index=True)
    language: str = Field(default="en", index=True)
    order_reference_digest: str = Field(index=True)
    order_reference_masked: str
    status: str = Field(default="intake", index=True)
    category: Optional[str] = Field(default=None, index=True)
    risk_level: str = Field(default="medium", index=True)
    needs_human: bool = Field(default=False, index=True)
    human_reason: Optional[str] = None
    task_id: str = Field(index=True)
    approval_request_id: Optional[str] = Field(default=None, index=True)
    order_snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    citations_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    recommendation_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    draft_reply: Optional[str] = None
    root_cause: Optional[str] = None
    follow_up_task_ids_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_by_user_id: str = Field(index=True)
    closed_by_user_id: Optional[str] = Field(default=None, index=True)
    version: int = Field(default=0)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)
    closed_at: Optional[datetime] = Field(default=None, index=True)


class AfterSalesCaseEvent(SQLModel, table=True):
    """Append-only after-sales business trace."""

    __tablename__ = "after_sales_case_events"
    __table_args__ = (
        Index("ix_after_sales_case_events_case_time", "case_id", "occurred_at"),
    )

    id: str = Field(default_factory=lambda: new_id("aftersales_event"), primary_key=True)
    tenant_id: str = Field(index=True)
    case_id: str = Field(index=True)
    event_type: str = Field(index=True)
    actor_type: str = Field(default="human", index=True)
    actor_id: Optional[str] = Field(default=None, index=True)
    actor_business_role: Optional[str] = Field(default=None, index=True)
    from_status: Optional[str] = Field(default=None, index=True)
    to_status: Optional[str] = Field(default=None, index=True)
    detail_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    occurred_at: datetime = Field(default_factory=utc_now, index=True)


class LogisticsAnomaly(SQLModel, table=True):
    """Deduplicated logistics exception aggregate and escalation receipt."""

    __tablename__ = "logistics_anomalies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "fingerprint", name="uq_logistics_anomaly_fingerprint"),
        CheckConstraint(
            "status IN ('detected', 'clustered', 'escalated', 'resolved')",
            name="logistics_anomalies_status_check",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="logistics_anomalies_severity_check",
        ),
        Index("ix_logistics_anomalies_tenant_status_updated", "tenant_id", "status", "updated_at"),
        Index("ix_logistics_anomalies_tenant_cluster", "tenant_id", "cluster_key"),
    )

    id: str = Field(default_factory=lambda: new_id("logistics"), primary_key=True)
    tenant_id: str = Field(index=True)
    fingerprint: str = Field(index=True)
    carrier_resource_id: str = Field(index=True)
    carrier_code: str = Field(index=True)
    store_resource_id: Optional[str] = Field(default=None, index=True)
    platform: str = Field(index=True)
    order_reference_digest: str = Field(index=True)
    order_reference_masked: str
    status_event_id: str = Field(index=True)
    shipment_status: str = Field(index=True)
    anomaly_type: str = Field(index=True)
    status: str = Field(default="detected", index=True)
    severity: str = Field(default="medium", index=True)
    customer_impact: str = Field(default="medium", index=True)
    cluster_key: str = Field(index=True)
    dimensions_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    evidence_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    escalation_targets_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    follow_up_task_ids_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    task_id: str = Field(index=True)
    occurrence_count: int = Field(default=1)
    deadline_at: Optional[datetime] = Field(default=None, index=True)
    first_observed_at: datetime = Field(default_factory=utc_now, index=True)
    last_observed_at: datetime = Field(default_factory=utc_now, index=True)
    resolved_by_user_id: Optional[str] = Field(default=None, index=True)
    resolution: Optional[str] = None
    version: int = Field(default=0)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)
    resolved_at: Optional[datetime] = Field(default=None, index=True)


class LogisticsAnomalyEvent(SQLModel, table=True):
    """Append-only logistics detection, deduplication and escalation trace."""

    __tablename__ = "logistics_anomaly_events"
    __table_args__ = (
        Index("ix_logistics_anomaly_events_anomaly_time", "anomaly_id", "occurred_at"),
    )

    id: str = Field(default_factory=lambda: new_id("logistics_event"), primary_key=True)
    tenant_id: str = Field(index=True)
    anomaly_id: str = Field(index=True)
    event_type: str = Field(index=True)
    actor_type: str = Field(default="system", index=True)
    actor_id: Optional[str] = Field(default=None, index=True)
    actor_business_role: Optional[str] = Field(default=None, index=True)
    from_status: Optional[str] = Field(default=None, index=True)
    to_status: Optional[str] = Field(default=None, index=True)
    detail_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    occurred_at: datetime = Field(default_factory=utc_now, index=True)


class IntegrationHealthState(SQLModel, table=True):
    """Visible, tenant-scoped dependency health used to prevent silent degradation."""

    __tablename__ = "integration_health_states"
    __table_args__ = (
        UniqueConstraint("tenant_id", "dependency_key", name="uq_integration_health_dependency"),
        CheckConstraint(
            "status IN ('healthy', 'degraded', 'unavailable')",
            name="integration_health_states_status_check",
        ),
        Index("ix_integration_health_tenant_status", "tenant_id", "status"),
    )

    id: str = Field(default_factory=lambda: new_id("integration_health"), primary_key=True)
    tenant_id: str = Field(index=True)
    dependency_key: str = Field(index=True)
    display_name: str
    domain: str = Field(index=True)
    status: str = Field(default="healthy", index=True)
    reason_code: Optional[str] = Field(default=None, index=True)
    message: str = ""
    recovery_hint: str = ""
    source: str = Field(default="operator", index=True)
    last_success_at: Optional[datetime] = Field(default=None, index=True)
    observed_at: datetime = Field(default_factory=utc_now, index=True)
    stale_after_seconds: int = Field(default=900)
    version: int = Field(default=0)
    updated_by_user_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)


class IntegrationHealthEvent(SQLModel, table=True):
    """Append-only evidence for dependency degradation and recovery."""

    __tablename__ = "integration_health_events"
    __table_args__ = (
        Index("ix_integration_health_events_state_time", "state_id", "occurred_at"),
    )

    id: str = Field(default_factory=lambda: new_id("integration_health_event"), primary_key=True)
    tenant_id: str = Field(index=True)
    state_id: str = Field(index=True)
    event_type: str = Field(index=True)
    actor_type: str = Field(default="system", index=True)
    actor_id: Optional[str] = Field(default=None, index=True)
    from_status: Optional[str] = Field(default=None, index=True)
    to_status: str = Field(index=True)
    detail_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    occurred_at: datetime = Field(default_factory=utc_now, index=True)


class ListingRuleSet(SQLModel, table=True):
    """Immutable, reviewed platform rule version used by listing checks."""

    __tablename__ = "listing_rule_sets"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "platform",
            "marketplace",
            "category",
            "version",
            name="uq_listing_rule_set_version",
        ),
        CheckConstraint(
            "status IN ('draft', 'published', 'retired')",
            name="listing_rule_sets_status_check",
        ),
        Index(
            "ix_listing_rule_sets_scope_status",
            "tenant_id",
            "platform",
            "marketplace",
            "category",
            "status",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("listing_rules"), primary_key=True)
    tenant_id: str = Field(index=True)
    platform: str = Field(index=True)
    marketplace: str = Field(index=True)
    category: str = Field(index=True)
    version: str = Field(index=True)
    status: str = Field(default="draft", index=True)
    rules_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    content_digest: str = Field(index=True)
    source_references_json: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    effective_at: datetime = Field(index=True)
    expires_at: Optional[datetime] = Field(default=None, index=True)
    created_by_user_id: str = Field(index=True)
    reviewed_by_user_id: Optional[str] = Field(default=None, index=True)
    reviewed_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class ListingComplianceCheck(SQLModel, table=True):
    """Point-in-time listing review bound to rules, facts and creative assets."""

    __tablename__ = "listing_compliance_checks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "check_key", name="uq_listing_compliance_check_key"),
        CheckConstraint(
            "gate_status IN ('pass', 'warn', 'block')",
            name="listing_compliance_checks_gate_check",
        ),
        Index(
            "ix_listing_compliance_checks_product_time",
            "tenant_id",
            "product_key",
            "created_at",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("listing_check"), primary_key=True)
    tenant_id: str = Field(index=True)
    check_key: str = Field(index=True)
    store_resource_id: str = Field(index=True)
    product_key: str = Field(index=True)
    sku: str = Field(index=True)
    language: str = Field(index=True)
    rule_set_id: str = Field(index=True)
    rule_version: str = Field(index=True)
    rule_digest: str = Field(index=True)
    sku_fact_version: str = Field(index=True)
    sku_facts_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    content_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    asset_version_ids_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    findings_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    gate_status: str = Field(default="block", index=True)
    input_digest: str = Field(index=True)
    task_id: str = Field(index=True)
    created_by_user_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class CreativeBrief(SQLModel, table=True):
    """Versionable creative request with explicit delivery constraints."""

    __tablename__ = "creative_briefs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "brief_key", name="uq_creative_brief_key"),
        CheckConstraint(
            "status IN ('open', 'in_progress', 'completed', 'cancelled')",
            name="creative_briefs_status_check",
        ),
        Index("ix_creative_briefs_product_status", "tenant_id", "product_key", "status"),
    )

    id: str = Field(default_factory=lambda: new_id("creative_brief"), primary_key=True)
    tenant_id: str = Field(index=True)
    brief_key: str = Field(index=True)
    store_resource_id: str = Field(index=True)
    product_key: str = Field(index=True)
    language: str = Field(index=True)
    dimensions_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    selling_points_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    scenes_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    required_assets_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    constraints_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    fact_snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    brand_snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    platform_spec_snapshot_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    snapshot_digest: str = Field(default="", index=True)
    status: str = Field(default="open", index=True)
    task_id: str = Field(index=True)
    due_at: Optional[datetime] = Field(default=None, index=True)
    created_by_user_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)


class CreativeAssetVersion(SQLModel, table=True):
    """Append-only creative asset lineage; source versions are never overwritten."""

    __tablename__ = "creative_asset_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "asset_key", "version", name="uq_creative_asset_version"
        ),
        CheckConstraint(
            "status IN ('draft', 'pending_review', 'approved', 'rejected')",
            name="creative_asset_versions_status_check",
        ),
        Index(
            "ix_creative_asset_versions_product_status",
            "tenant_id",
            "product_key",
            "status",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("asset_version"), primary_key=True)
    tenant_id: str = Field(index=True)
    asset_key: str = Field(index=True)
    version: int = Field(index=True)
    brief_id: str = Field(index=True)
    parent_version_id: Optional[str] = Field(default=None, index=True)
    store_resource_id: str = Field(index=True)
    product_key: str = Field(index=True)
    asset_type: str = Field(index=True)
    file_reference: str
    file_digest: str = Field(index=True)
    provenance_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    generation_parameters_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    checks_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    required_human_approval: bool = Field(default=True, index=True)
    status: str = Field(default="pending_review", index=True)
    creator_user_id: str = Field(index=True)
    reviewed_by_user_id: Optional[str] = Field(default=None, index=True)
    review_note: Optional[str] = None
    reviewed_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class DesignQCReport(SQLModel, table=True):
    """Immutable, reproducible QC evidence for one creative asset version."""

    __tablename__ = "design_qc_reports"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "asset_version_id", "input_digest", name="uq_design_qc_input"
        ),
        CheckConstraint(
            "overall_status IN ('pass', 'fail', 'unknown', 'not_applicable')",
            name="design_qc_reports_status_check",
        ),
        Index(
            "ix_design_qc_reports_asset_created",
            "tenant_id",
            "asset_version_id",
            "created_at",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("design_qc"), primary_key=True)
    tenant_id: str = Field(index=True)
    asset_version_id: str = Field(index=True)
    asset_digest: str = Field(index=True)
    brief_id: str = Field(index=True)
    store_resource_id: str = Field(index=True)
    snapshot_digest: str = Field(index=True)
    checker_version: str = Field(index=True)
    overall_status: str = Field(default="unknown", index=True)
    findings_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    input_digest: str = Field(index=True)
    created_by_user_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class CreativeEvidenceRecord(SQLModel, table=True):
    """Tenant-scoped evidence registry used to expire Brief inputs safely."""

    __tablename__ = "creative_evidence_records"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "evidence_type",
            "source_ref",
            "version",
            name="uq_creative_evidence_version",
        ),
        CheckConstraint(
            "status IN ('draft', 'verified', 'expired', 'revoked')",
            name="creative_evidence_status_check",
        ),
        CheckConstraint(
            "evidence_type IN ('facts', 'brand', 'platform_spec')",
            name="creative_evidence_type_check",
        ),
        Index(
            "ix_creative_evidence_active_lookup",
            "tenant_id",
            "evidence_type",
            "source_ref",
            "version",
            "status",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("creative_evidence"), primary_key=True)
    tenant_id: str = Field(index=True)
    evidence_type: str = Field(index=True)
    source_ref: str = Field(index=True)
    version: str = Field(index=True)
    payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    content_digest: str = Field(index=True)
    status: str = Field(default="draft", index=True)
    effective_at: datetime = Field(default_factory=utc_now, index=True)
    expires_at: Optional[datetime] = Field(default=None, index=True)
    synced_at: datetime = Field(default_factory=utc_now, index=True)
    sync_error: Optional[str] = None
    created_by_user_id: str = Field(index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)


class CreativeDeliveryChecklist(SQLModel, table=True):
    """Evidence-bound delivery checklist; ready is not an external publish."""

    __tablename__ = "creative_delivery_checklists"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "brief_id", "delivery_digest", name="uq_creative_delivery_digest"
        ),
        CheckConstraint(
            "status IN ('blocked', 'ready', 'delivered', 'failed')",
            name="creative_delivery_status_check",
        ),
        Index(
            "ix_creative_delivery_brief_created",
            "tenant_id",
            "brief_id",
            "created_at",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("creative_delivery"), primary_key=True)
    tenant_id: str = Field(index=True)
    brief_id: str = Field(index=True)
    store_resource_id: str = Field(index=True)
    product_key: str = Field(index=True)
    asset_version_ids_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    qc_report_ids_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    checklist_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    blockers_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    delivery_digest: str = Field(index=True)
    status: str = Field(default="blocked", index=True)
    created_by_user_id: str = Field(index=True)
    delivered_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class CreativeGenerationRequest(SQLModel, table=True):
    """Idempotent provider submission; provider output is never auto-approved."""

    __tablename__ = "creative_generation_requests"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "provider_key", "idempotency_key", name="uq_creative_generation_key"
        ),
        CheckConstraint(
            "status IN ('queued', 'submitted', 'succeeded', 'failed', 'cancelled')",
            name="creative_generation_status_check",
        ),
        Index(
            "ix_creative_generation_brief_created",
            "tenant_id",
            "brief_id",
            "created_at",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("creative_generation"), primary_key=True)
    tenant_id: str = Field(index=True)
    brief_id: str = Field(index=True)
    provider_key: str = Field(index=True)
    idempotency_key: str = Field(index=True)
    status: str = Field(default="queued", index=True)
    request_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    response_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    external_request_id: Optional[str] = Field(default=None, index=True)
    error_code: Optional[str] = Field(default=None, index=True)
    error_message: Optional[str] = None
    created_by_user_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)


class ProcurementRecommendation(SQLModel, table=True):
    """Auditable replenishment recommendation; it is never a purchase order."""

    __tablename__ = "procurement_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "recommendation_key", name="uq_procurement_recommendation_key"
        ),
        CheckConstraint(
            "status IN ('draft', 'reviewed', 'rejected')",
            name="procurement_recommendations_status_check",
        ),
        Index(
            "ix_procurement_recommendations_product_status",
            "tenant_id",
            "product_key",
            "status",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("procurement_rec"), primary_key=True)
    tenant_id: str = Field(index=True)
    recommendation_key: str = Field(index=True)
    supplier_resource_id: str = Field(index=True)
    store_resource_id: Optional[str] = Field(default=None, index=True)
    product_key: str = Field(index=True)
    sku: str = Field(index=True)
    input_snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    formula: str
    recommended_quantity: int
    estimated_landed_cost: float
    lead_time_days: int
    risk_level: str = Field(default="medium", index=True)
    risk_reasons_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = Field(default="draft", index=True)
    task_id: str = Field(index=True)
    created_by_user_id: str = Field(index=True)
    reviewed_by_user_id: Optional[str] = Field(default=None, index=True)
    review_note: Optional[str] = None
    reviewed_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class ProductLaunchGate(SQLModel, table=True):
    """Cross-role launch gate that blocks publishing until every input is approved."""

    __tablename__ = "product_launch_gates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "launch_key", name="uq_product_launch_gate_key"),
        CheckConstraint(
            "status IN ('blocked', 'ready', 'waiting_approval', 'approved', 'rejected')",
            name="product_launch_gates_status_check",
        ),
        Index("ix_product_launch_gates_product_status", "tenant_id", "product_key", "status"),
    )

    id: str = Field(default_factory=lambda: new_id("launch_gate"), primary_key=True)
    tenant_id: str = Field(index=True)
    launch_key: str = Field(index=True)
    store_resource_id: str = Field(index=True)
    supplier_resource_id: str = Field(index=True)
    product_key: str = Field(index=True)
    sku: str = Field(index=True)
    sku_fact_version: str = Field(index=True)
    bom_version: str = Field(index=True)
    packaging_version: str = Field(index=True)
    certification_ids_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    supplier_lead_time_confirmed: bool = Field(default=False)
    listing_check_id: str = Field(index=True)
    asset_version_ids_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    procurement_recommendation_id: str = Field(index=True)
    blockers_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    evidence_digest: str = Field(index=True)
    status: str = Field(default="blocked", index=True)
    approval_request_id: Optional[str] = Field(default=None, index=True)
    task_id: str = Field(index=True)
    created_by_user_id: str = Field(index=True)
    version: int = Field(default=0)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)


class ProductQualityIssue(SQLModel, table=True):
    """Quality signal fanned out from after-sales to procurement, design and listing."""

    __tablename__ = "product_quality_issues"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_case_id", name="uq_product_quality_issue_case"),
        CheckConstraint(
            "status IN ('open', 'investigating', 'resolved')",
            name="product_quality_issues_status_check",
        ),
        Index("ix_product_quality_issues_tenant_status_time", "tenant_id", "status", "created_at"),
    )

    id: str = Field(default_factory=lambda: new_id("quality_issue"), primary_key=True)
    tenant_id: str = Field(index=True)
    source_case_id: str = Field(index=True)
    store_resource_id: str = Field(index=True)
    product_key: str = Field(default="unknown", index=True)
    category: str = Field(index=True)
    root_cause: str
    task_ids_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = Field(default="open", index=True)
    created_by_user_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)


class CommerceGovernanceEvent(SQLModel, table=True):
    """Append-only lifecycle evidence shared by listing, creative and procurement."""

    __tablename__ = "commerce_governance_events"
    __table_args__ = (
        Index(
            "ix_commerce_governance_events_aggregate_time",
            "aggregate_type",
            "aggregate_id",
            "occurred_at",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("commerce_event"), primary_key=True)
    tenant_id: str = Field(index=True)
    aggregate_type: str = Field(index=True)
    aggregate_id: str = Field(index=True)
    event_type: str = Field(index=True)
    actor_type: str = Field(default="human", index=True)
    actor_id: Optional[str] = Field(default=None, index=True)
    actor_business_role: Optional[str] = Field(default=None, index=True)
    detail_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    occurred_at: datetime = Field(default_factory=utc_now, index=True)


class AdvertisingRecommendation(SQLModel, table=True):
    """Constraint-aware ad recommendation; external changes remain approval-bound."""

    __tablename__ = "advertising_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "recommendation_key", name="uq_advertising_recommendation_key"
        ),
        CheckConstraint(
            "status IN ('ready', 'blocked', 'action_pending', 'action_approved', 'action_rejected')",
            name="advertising_recommendations_status_check",
        ),
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high', 'critical')",
            name="advertising_recommendations_risk_check",
        ),
        Index(
            "ix_advertising_recommendations_campaign_time",
            "tenant_id",
            "campaign_id",
            "created_at",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("ad_recommendation"), primary_key=True)
    tenant_id: str = Field(index=True)
    recommendation_key: str = Field(index=True)
    ad_account_resource_id: str = Field(index=True)
    store_resource_id: Optional[str] = Field(default=None, index=True)
    campaign_id: str = Field(index=True)
    product_key: str = Field(index=True)
    metric_snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    constraint_snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    findings_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    recommendation_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    proposed_action_type: Optional[str] = Field(default=None, index=True)
    proposed_action_payload_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    risk_level: str = Field(default="medium", index=True)
    status: str = Field(default="ready", index=True)
    input_digest: str = Field(index=True)
    task_id: str = Field(index=True)
    linked_task_ids_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    approval_request_id: Optional[str] = Field(default=None, index=True)
    created_by_user_id: str = Field(index=True)
    version: int = Field(default=0)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)


class PdcaSearchTermRun(SQLModel, table=True):
    """Immutable rules-only diagnosis run over one tenant-scoped search-term input."""

    __tablename__ = "pdca_search_term_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_pdca_search_term_run_tenant_id"),
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_pdca_search_term_run_idempotency"
        ),
        UniqueConstraint(
            "tenant_id",
            "input_digest",
            "attempt",
            name="uq_pdca_search_term_run_snapshot_attempt",
        ),
        CheckConstraint("mode = 'rules_only'", name="pdca_search_term_runs_mode_check"),
        CheckConstraint("state = 'succeeded'", name="pdca_search_term_runs_state_check"),
        CheckConstraint(
            "external_execution_allowed = false",
            name="pdca_search_term_runs_no_execution_check",
        ),
        CheckConstraint(
            "quality_score >= 0 AND quality_score <= 100",
            name="pdca_search_term_runs_quality_check",
        ),
        CheckConstraint(
            "source_row_count > 0 AND fact_count > 0 AND action_count >= 0",
            name="pdca_search_term_runs_counts_check",
        ),
        CheckConstraint(
            "target_acos > 0 AND target_acos <= 1",
            name="pdca_search_term_runs_target_check",
        ),
        CheckConstraint("attempt > 0", name="pdca_search_term_runs_attempt_check"),
        Index(
            "ix_pdca_search_term_runs_account_time",
            "tenant_id",
            "ad_account_resource_id",
            "created_at",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("pdca_run"), primary_key=True)
    tenant_id: str = Field(index=True)
    idempotency_key: str = Field(index=True)
    ad_account_resource_id: str = Field(index=True)
    store_resource_id: Optional[str] = Field(default=None, index=True)
    source_type: str = Field(default="amazon_search_term_csv")
    source_label: str = Field(default="local source file")
    source_sha256: str = Field(index=True)
    input_digest: str = Field(index=True)
    attempt: int = Field(default=1)
    mapping_version: str = Field(index=True)
    rule_version: str = Field(index=True)
    metric_definition_version: str = Field(index=True)
    mode: str = Field(default="rules_only", index=True)
    state: str = Field(default="succeeded", index=True)
    target_acos: Decimal = Field(sa_column=Column(Numeric(12, 8), nullable=False))
    currency: str = Field(default="USD")
    source_row_count: int = Field(default=0)
    fact_count: int = Field(default=0)
    action_count: int = Field(default=0)
    quality_score: int = Field(default=0)
    mapping_snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    summary_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    warnings_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    external_execution_allowed: bool = Field(default=False)
    created_by_user_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class PdcaIdempotencyKey(SQLModel, table=True):
    """Append-only binding from every accepted request key to its frozen run."""

    __tablename__ = "pdca_idempotency_keys"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["pdca_search_term_runs.tenant_id", "pdca_search_term_runs.id"],
            ondelete="RESTRICT",
            name="fk_pdca_idempotency_key_run_tenant",
        ),
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_pdca_idempotency_key_tenant_key"
        ),
        Index("ix_pdca_idempotency_keys_run", "tenant_id", "run_id"),
    )

    id: str = Field(default_factory=lambda: new_id("pdca_key"), primary_key=True)
    tenant_id: str = Field(index=True)
    idempotency_key: str = Field(index=True)
    run_id: str = Field(index=True)
    input_digest: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class PdcaFactSearchTerm(SQLModel, table=True):
    """Frozen Amazon account facts aggregated at the documented search-term grain."""

    __tablename__ = "pdca_fact_search_terms"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["pdca_search_term_runs.tenant_id", "pdca_search_term_runs.id"],
            ondelete="RESTRICT",
            name="fk_pdca_fact_search_term_run_tenant",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_pdca_fact_search_term_tenant_id"),
        UniqueConstraint(
            "tenant_id", "run_id", "grain_key", name="uq_pdca_fact_search_term_grain"
        ),
        CheckConstraint(
            "impressions >= 0 AND clicks >= 0 AND orders >= 0 AND spend >= 0 AND sales >= 0",
            name="pdca_fact_search_terms_metric_check",
        ),
        Index(
            "ix_pdca_fact_search_terms_run",
            "tenant_id",
            "run_id",
            "campaign_id",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("pdca_fact"), primary_key=True)
    tenant_id: str = Field(index=True)
    run_id: str = Field(index=True)
    grain_key: str = Field(index=True)
    date_start: date
    date_end: date
    campaign_id: str = Field(index=True)
    campaign_name: str
    ad_group_id: str = Field(index=True)
    ad_group_name: str
    targeting: str
    match_type: str = Field(index=True)
    search_term: str
    search_term_norm: str = Field(index=True)
    impressions: int = Field(default=0)
    clicks: int = Field(default=0)
    spend: Decimal = Field(sa_column=Column(Numeric(20, 6), nullable=False))
    sales: Decimal = Field(sa_column=Column(Numeric(20, 6), nullable=False))
    orders: int = Field(default=0)
    metric_snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    evidence_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    source_row_refs_json: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now, index=True)


class PdcaAction(SQLModel, table=True):
    """Advice-only rule output with no foreign execution or approval binding."""

    __tablename__ = "pdca_actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["pdca_search_term_runs.tenant_id", "pdca_search_term_runs.id"],
            ondelete="RESTRICT",
            name="fk_pdca_action_run_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "fact_id"],
            ["pdca_fact_search_terms.tenant_id", "pdca_fact_search_terms.id"],
            ondelete="RESTRICT",
            name="fk_pdca_action_fact_tenant",
        ),
        UniqueConstraint(
            "tenant_id", "run_id", "fact_id", "action_type", name="uq_pdca_action_rule_output"
        ),
        CheckConstraint(
            "action_type IN ('manual_review', 'lower_bid', 'convert_exact', "
            "'protect_scale', 'observe')",
            name="pdca_actions_type_check",
        ),
        CheckConstraint(
            "priority IN ('critical', 'high', 'medium', 'low')",
            name="pdca_actions_priority_check",
        ),
        CheckConstraint("status = 'suggested'", name="pdca_actions_status_check"),
        CheckConstraint(
            "external_execution_allowed = false", name="pdca_actions_no_execution_check"
        ),
        CheckConstraint(
            "must_do_score >= 0 AND must_do_score <= 100",
            name="pdca_actions_score_check",
        ),
        CheckConstraint(
            "verification_window_days > 0",
            name="pdca_actions_window_check",
        ),
        Index("ix_pdca_actions_run_priority", "tenant_id", "run_id", "must_do_score"),
    )

    id: str = Field(default_factory=lambda: new_id("pdca_action"), primary_key=True)
    tenant_id: str = Field(index=True)
    run_id: str = Field(index=True)
    fact_id: str = Field(index=True)
    action_type: str = Field(index=True)
    priority: str = Field(index=True)
    must_do_score: int = Field(default=0)
    rationale: str
    evidence_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    thresholds_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    current_values_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    expected_effect: str
    risk_note: str
    verification_window_days: int = Field(default=7)
    execution_hint: str
    status: str = Field(default="suggested", index=True)
    external_execution_allowed: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class AdvertisingEffectFollowUp(SQLModel, table=True):
    """Idempotent 7/14/30-day effectiveness review created after an ad write."""

    __tablename__ = "advertising_effect_follow_ups"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "execution_id",
            "horizon_days",
            name="uq_advertising_effect_follow_up",
        ),
        CheckConstraint(
            "horizon_days IN (7, 14, 30)",
            name="advertising_effect_follow_ups_horizon_check",
        ),
        CheckConstraint(
            "status IN ('pending', 'completed', 'cancelled')",
            name="advertising_effect_follow_ups_status_check",
        ),
        Index(
            "ix_advertising_effect_follow_ups_due",
            "tenant_id",
            "status",
            "due_at",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("ad_effect"), primary_key=True)
    tenant_id: str = Field(index=True)
    execution_id: str = Field(index=True)
    request_id: str = Field(index=True)
    recommendation_id: Optional[str] = Field(default=None, index=True)
    horizon_days: int = Field(index=True)
    baseline_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    task_id: str = Field(index=True)
    status: str = Field(default="pending", index=True)
    due_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class ExecutionAutomationPolicy(SQLModel, table=True):
    """Optional stricter gate for approved low-risk external actions."""

    __tablename__ = "execution_automation_policies"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "resource_id",
            "action_type",
            name="uq_execution_automation_policy",
        ),
        CheckConstraint(
            "status IN ('active', 'paused')",
            name="execution_automation_policies_status_check",
        ),
        CheckConstraint(
            "rollout_percent >= 0 AND rollout_percent <= 100",
            name="execution_automation_policies_rollout_check",
        ),
        Index(
            "ix_execution_automation_policies_lookup",
            "tenant_id",
            "resource_id",
            "action_type",
            "status",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("automation_policy"), primary_key=True)
    tenant_id: str = Field(index=True)
    resource_id: str = Field(index=True)
    action_type: str = Field(index=True)
    status: str = Field(default="paused", index=True)
    rollout_percent: int = Field(default=0)
    max_single_value: float = Field(default=0)
    max_daily_value: float = Field(default=0)
    max_risk_level: str = Field(default="low", index=True)
    approval_required: bool = Field(default=True)
    kill_switch_engaged: bool = Field(default=True, index=True)
    revision: int = Field(default=1)
    created_by_user_id: str = Field(index=True)
    updated_by_user_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)


class AutomationUsageLedger(SQLModel, table=True):
    """Append-only rollout and quantitative-limit decision for one approved action."""

    __tablename__ = "automation_usage_ledger"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "request_id", name="uq_automation_usage_request"
        ),
        CheckConstraint(
            "decision IN ('allowed', 'blocked')",
            name="automation_usage_ledger_decision_check",
        ),
        Index(
            "ix_automation_usage_policy_day",
            "tenant_id",
            "policy_id",
            "usage_date",
            "decision",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("automation_usage"), primary_key=True)
    tenant_id: str = Field(index=True)
    policy_id: str = Field(index=True)
    policy_revision: int
    request_id: str = Field(index=True)
    action_type: str = Field(index=True)
    cohort_bucket: int
    quantitative_value: float
    usage_date: str = Field(index=True)
    decision: str = Field(index=True)
    reason: str
    created_at: datetime = Field(default_factory=utc_now, index=True)


class Team(SQLModel, table=True):
    """多 Agent 团队:一名 TL(leader 角色成员)+ 若干成员(数字员工)。"""

    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_team_tenant_name"),)

    id: str = Field(default_factory=lambda: new_id("team"), primary_key=True)
    tenant_id: str = Field(index=True)
    name: str
    description: Optional[str] = None
    owner_user_id: str = Field(index=True)
    # 预留:并发策略/竞标等团队级配置
    config_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = Field(default="active", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TeamMember(SQLModel, table=True):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "agent_id", name="uq_team_member_agent"),)

    id: str = Field(default_factory=lambda: new_id("team_member"), primary_key=True)
    team_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    # role: leader(TL,每团队至多一名)/ member
    role: str = Field(default="member", index=True)
    created_at: datetime = Field(default_factory=utc_now)


class TeamRun(SQLModel, table=True):
    """One durable TL plan from delegation through final team synthesis."""

    __tablename__ = "team_runs"
    __table_args__ = (
        UniqueConstraint(
            "tl_session_id",
            "source_turn_id",
            name="uq_team_run_tl_session_source_turn",
        ),
    )

    id: str = Field(default_factory=lambda: new_id("team_run"), primary_key=True)
    team_id: str = Field(index=True)
    tenant_id: str = Field(index=True)
    tl_session_id: str = Field(index=True)
    source_turn_id: str = Field(index=True)
    created_by_user_id: Optional[str] = Field(default=None, index=True)
    # planning -> running/awaiting_input -> synthesizing -> completed/failed
    status: str = Field(default="planning", index=True)
    synthesis_session_id: Optional[str] = Field(default=None, index=True)
    final_message_id: Optional[str] = Field(default=None, index=True)
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None


class TeamTask(SQLModel, table=True):
    """团队任务:blocked -> pending -> in_progress -> review -> done/rework/escalated;

    rework -> in_progress 重入;pending -> bidding -> pending 为任务池竞标链路。
    """

    __tablename__ = "team_tasks"

    id: str = Field(default_factory=lambda: new_id("team_task"), primary_key=True)
    team_id: str = Field(index=True)
    tenant_id: str = Field(index=True)
    team_run_id: Optional[str] = Field(default=None, index=True)
    source_turn_id: Optional[str] = Field(default=None, index=True)
    parent_task_id: Optional[str] = Field(default=None, index=True)
    title: str
    description: Optional[str] = None
    priority: str = Field(default="normal", index=True)
    status: str = Field(default="pending", index=True)
    created_by_user_id: Optional[str] = Field(default=None, index=True)
    created_by_tl: bool = False
    assignee_agent_id: Optional[str] = Field(default=None, index=True)
    session_id: Optional[str] = Field(default=None, index=True)
    depends_on_task_ids_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    activation_condition_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    report_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    review_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # 乐观锁版本号,人改判/验收并发时防覆盖
    version: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TeamTaskEvent(SQLModel, table=True):
    """团队任务审计流水。"""

    __tablename__ = "team_task_events"

    id: str = Field(default_factory=lambda: new_id("team_task_event"), primary_key=True)
    task_id: str = Field(index=True)
    team_id: str = Field(index=True)
    # actor_type: user / agent / system
    actor_type: str = Field(index=True)
    actor_id: Optional[str] = Field(default=None, index=True)
    event_type: str = Field(index=True)
    payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)


class TeamWakeEvent(SQLModel, table=True):
    """团队唤醒事件:任务派发/报告/退回时唤醒对应成员或 TL 的后台会话。"""

    __tablename__ = "team_wake_events"

    id: str = Field(default_factory=lambda: new_id("team_wake"), primary_key=True)
    team_id: str = Field(index=True)
    tenant_id: str = Field(index=True)
    target_agent_id: str = Field(index=True)
    # trigger_type: task_assigned / task_report / task_rework / tl_message 等
    trigger_type: str = Field(index=True)
    payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # status: pending -> claimed -> done / failed
    status: str = Field(default="pending", index=True)
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TeamBlackboardEntry(SQLModel, table=True):
    """团队黑板:团队工作记忆,TL 裁决写入/人直写,按团队隔离。"""

    __tablename__ = "team_blackboard_entries"

    id: str = Field(default_factory=lambda: new_id("bbentry"), primary_key=True)
    team_id: str = Field(index=True)
    tenant_id: str = Field(index=True)
    content: str
    tags_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # source_type: member(TL 裁决的成员建议) / leader / human(人直写)
    source_type: str = Field(default="human", index=True)
    source_agent_id: Optional[str] = Field(default=None, index=True)
    source_task_id: Optional[str] = Field(default=None, index=True)
    # 引用回链:如 {"task_id": ..., "task_title": ...}
    citation_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # status: active / archived
    status: str = Field(default="active", index=True)
    pinned: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TeamTaskBid(SQLModel, table=True):
    """团队任务竞标:候选成员的方案陈述(round=1)/反驳(round=2)及 TL 打分。"""

    __tablename__ = "team_task_bids"
    __table_args__ = (
        UniqueConstraint("task_id", "agent_id", "round", "kind", name="uq_team_task_bid_round"),
    )

    id: str = Field(default_factory=lambda: new_id("bid"), primary_key=True)
    task_id: str = Field(index=True)
    team_id: str = Field(index=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    round: int = 1
    # kind: statement(方案陈述) / rebuttal(反驳)
    kind: str = Field(default="statement", index=True)
    content: str
    # TL 裁决后回写的分数与理由,未裁决前为 None
    score: Optional[float] = None
    score_rationale: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
