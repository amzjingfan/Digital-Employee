from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta
from typing import Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.accounts.casdoor import CasdoorManagementClient
from app.accounts.lifecycle import (
    accept_invitation,
    cancel_invitation,
    create_invitation,
    record_account_event,
)
from app.config import get_settings
from app.db import get_session, set_tenant_context
from app.db.models import (
    AccountLifecycleEvent,
    APIClient,
    APICredential,
    Tenant,
    User,
    UserAvatar,
    UserInvitation,
    utc_now,
)
from app.public_api.auth import generate_api_key
from app.public_api.credential_profiles import USER_FULL_ACCESS_SCOPES
from app.security.auth import (
    create_access_token,
    ensure_current_user_tenant,
    get_current_user,
    hash_password,
    verify_password,
)
from app.security.authorization import enterprise_capabilities
from app.security.permissions import MEMBER_ROLE, is_admin_user
from app.security.tenant import ensure_tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    tenant_id: str
    username: str
    password: str


class UserCreateRequest(BaseModel):
    tenant_id: str
    username: str
    password: str
    display_name: Optional[str] = None
    role: Literal["admin", "member"] = MEMBER_ROLE


class UserUpdateRequest(BaseModel):
    tenant_id: str
    display_name: Optional[str] = None
    password: Optional[str] = None
    role: Optional[Literal["admin", "member"]] = None


class UserStatusRequest(BaseModel):
    tenant_id: str
    status: Literal["active", "suspended"]
    reason: str = Field(min_length=1, max_length=500)


class UserForceLogoutRequest(BaseModel):
    tenant_id: str
    reason: str = Field(min_length=1, max_length=500)


class UserInvitationCreateRequest(BaseModel):
    tenant_id: str
    username: str
    display_name: Optional[str] = None
    role: Literal["admin", "member"] = MEMBER_ROLE
    business_role: str = "member"
    auth_source: Literal["local", "oidc"] = "local"


class UserInvitationAcceptRequest(BaseModel):
    tenant_id: str
    token: str = Field(min_length=16, max_length=500)
    password: Optional[str] = Field(default=None, max_length=500)


class UserInvitationRead(BaseModel):
    id: str
    tenant_id: str
    username: str
    display_name: Optional[str] = None
    role: str
    business_role: str
    auth_source: str
    status: str
    invited_by_user_id: str
    accepted_by_user_id: Optional[str] = None
    expires_at: str
    accepted_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    created_at: str


class UserInvitationCreated(UserInvitationRead):
    invite_token: str
    accept_path: str


class AccountLifecycleEventRead(BaseModel):
    id: str
    tenant_id: str
    event_type: str
    actor_user_id: Optional[str] = None
    subject_user_id: Optional[str] = None
    subject_ref: str
    outcome: str
    reason: str
    detail: dict[str, object] = Field(default_factory=dict)
    occurred_at: str


class UserPreferencesRequest(BaseModel):
    locale: Literal["zh-CN", "en"]
    timezone: str = Field(min_length=1, max_length=80)


class TenantPreferencesRequest(BaseModel):
    tenant_id: str
    default_locale: Literal["zh-CN", "en"]
    default_timezone: str = Field(min_length=1, max_length=80)
    default_currency: str = Field(min_length=3, max_length=3)


class PreferencesRead(BaseModel):
    user_locale: Optional[str] = None
    user_timezone: Optional[str] = None
    tenant_default_locale: str
    tenant_default_timezone: str
    tenant_default_currency: str
    effective_locale: str
    effective_timezone: str


class UserChannelIdentity(BaseModel):
    channel: str
    display_name: Optional[str] = None
    external_user_id: Optional[str] = None
    external_account_scope: Optional[str] = None


class UserRead(BaseModel):
    id: str
    tenant_id: str
    username: str
    display_name: Optional[str] = None
    role: Literal["admin", "member"]
    business_role: str = "member"
    authorization_source: str = "local"
    identity_groups: list[str] = Field(default_factory=list)
    role_synced_at: Optional[str] = None
    enterprise_permissions: dict[str, list[str]] = Field(default_factory=dict)
    source: str = "web"
    status: Literal["active", "suspended"] = "active"
    session_version: int = 1
    identity_sync_status: str = "not_configured"
    preferred_locale: Optional[str] = None
    preferred_timezone: Optional[str] = None
    effective_locale: str = "en"
    effective_timezone: str = "UTC"
    # 仅 /me 与 /login 带出:头像资源指针(存在性标识),不内联二进制——
    # 完整 data_url 可达 2.67MB,内联会把登录/会话刷新响应与前端 localStorage 撑爆
    avatar_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # 渠道身份信息(仅 include_channel=True 时返回)
    channel_identities: Optional[list[UserChannelIdentity]] = None


class AvatarRead(BaseModel):
    avatar_url: str


class LoginResponse(BaseModel):
    token: str
    user: UserRead


class AccountAPICredentialCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    expires_at: datetime | None = None


class AccountAPICredentialRead(BaseModel):
    id: str
    user_id: str
    name: str
    access: Literal["user_full_access"] = "user_full_access"
    key_prefix: str
    scopes: list[str] = Field(default_factory=list)
    status: str
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime
    revoked_at: datetime | None = None


class AccountAPICredentialCreated(AccountAPICredentialRead):
    api_key: str


ACCOUNT_API_CLIENT_PREFIX = "九骥 Joukir 账号全量 API"


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_session)) -> LoginResponse:
    set_tenant_context(db, request.tenant_id)
    tenant = ensure_tenant(db, request.tenant_id)
    username = request.username.strip()
    if not username or not request.password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    user = db.exec(
        select(User).where(User.tenant_id == request.tenant_id, User.username == username)
    ).first()
    if not user:
        display_name_matches = db.exec(
            select(User)
            .where(User.tenant_id == request.tenant_id, User.display_name == username)
            .limit(2)
        ).all()
        if len(display_name_matches) == 1:
            user = display_name_matches[0]
    now = utc_now()
    if user and user.locked_until and user.locked_until > now:
        record_account_event(
            db,
            tenant_id=request.tenant_id,
            event_type="login_denied",
            actor_user_id=user.id,
            subject_user_id=user.id,
            subject_ref=user.username,
            outcome="denied",
            reason="account_temporarily_locked",
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user or not verify_password(request.password, user.password_hash):
        if user:
            settings = get_settings()
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= max(settings.auth_failed_login_limit, 1):
                user.locked_until = now + timedelta(
                    seconds=max(settings.auth_failed_login_lock_seconds, 1)
                )
                user.failed_login_attempts = 0
            user.updated_at = now
            db.add(user)
            record_account_event(
                db,
                tenant_id=request.tenant_id,
                event_type="login_denied",
                actor_user_id=user.id,
                subject_user_id=user.id,
                subject_ref=user.username,
                outcome="denied",
                reason="invalid_credentials",
                detail={"locked_until": user.locked_until.isoformat() if user.locked_until else None},
            )
            db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if user.status != "active":
        record_account_event(
            db,
            tenant_id=request.tenant_id,
            event_type="login_denied",
            actor_user_id=user.id,
            subject_user_id=user.id,
            subject_ref=user.username,
            outcome="denied",
            reason="account_suspended",
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.updated_at = now
    db.add(user)
    record_account_event(
        db,
        tenant_id=tenant.id,
        event_type="login_succeeded",
        actor_user_id=user.id,
        subject_user_id=user.id,
        subject_ref=user.username,
    )
    db.commit()
    db.refresh(user)

    return LoginResponse(
        token=create_access_token(user),
        user=_user_read(
            user,
            _avatar_pointer_for(db, user.id),
            include_enterprise_permissions=True,
            db=db,
        ),
    )


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_session)) -> UserRead:
    return _user_read(
        user,
        _avatar_pointer_for(db, user.id),
        include_enterprise_permissions=True,
        db=db,
    )


@router.get("/preferences", response_model=PreferencesRead)
def get_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> PreferencesRead:
    return _preferences_read(db, current_user)


@router.put("/preferences", response_model=PreferencesRead)
def update_preferences(
    request: UserPreferencesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> PreferencesRead:
    _validate_timezone(request.timezone)
    current_user.preferred_locale = request.locale
    current_user.preferred_timezone = request.timezone
    current_user.updated_at = utc_now()
    db.add(current_user)
    record_account_event(
        db,
        tenant_id=current_user.tenant_id,
        event_type="user_preferences_updated",
        actor_user_id=current_user.id,
        subject_user_id=current_user.id,
        subject_ref=current_user.username,
        detail={"locale": request.locale, "timezone": request.timezone},
    )
    db.commit()
    db.refresh(current_user)
    return _preferences_read(db, current_user)


@router.put("/tenant-preferences", response_model=PreferencesRead)
def update_tenant_preferences(
    request: TenantPreferencesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> PreferencesRead:
    _require_admin(current_user, request.tenant_id)
    _validate_timezone(request.default_timezone)
    tenant = ensure_tenant(db, request.tenant_id)
    tenant.default_locale = request.default_locale
    tenant.default_timezone = request.default_timezone
    tenant.default_currency = request.default_currency.upper()
    tenant.updated_at = utc_now()
    db.add(tenant)
    record_account_event(
        db,
        tenant_id=current_user.tenant_id,
        event_type="tenant_preferences_updated",
        actor_user_id=current_user.id,
        subject_user_id=current_user.id,
        subject_ref=tenant.id,
        detail={
            "default_locale": tenant.default_locale,
            "default_timezone": tenant.default_timezone,
            "default_currency": tenant.default_currency,
        },
    )
    db.commit()
    return _preferences_read(db, current_user)


MAX_AVATAR_BYTES = 2 * 1024 * 1024
# multipart 边界与头部开销的上限估计:Content-Length 预检放行正常图片,拦截明显超限请求
_AVATAR_MULTIPART_OVERHEAD = 64 * 1024
# 头像资源路径:login/me 返回的 avatar_url 即此指针,前端凭它用认证请求拉取字节
AVATAR_RESOURCE_PATH = "/api/auth/me/avatar"
# 头像类型嗅探:以实际字节头为准(防伪装 content-type),仅 png/jpeg/webp/gif
_AVATAR_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def _sniff_avatar_content_type(data: bytes) -> Optional[str]:
    """按字节头识别图片类型,返回规范 content-type;非支持图片返回 None。"""
    for magic, content_type in _AVATAR_MAGIC:
        if data.startswith(magic):
            return content_type
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.get("/me/avatar")
def get_my_avatar(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> Response:
    """头像资源端点:返回图片字节(不内联进 login/me,避免大字段进会话存储)。"""
    avatar = db.get(UserAvatar, current_user.id)
    if not avatar:
        raise HTTPException(status_code=404, detail="Avatar not found")
    parsed = _parse_avatar_data_url(avatar.data_url)
    if not parsed:
        logger.warning("用户 %s 的头像数据损坏,按不存在处理", current_user.id)
        raise HTTPException(status_code=404, detail="Avatar not found")
    data, content_type = parsed
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "private, no-cache"},
    )


@router.put("/me/avatar", response_model=AvatarRead)
async def update_my_avatar(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> AvatarRead:
    """上传/覆盖当前用户头像:multipart 单文件,图片 ≤2MB,以 data_url 存库(upsert)。"""
    # 先按 Content-Length 快速拒绝明显超限的请求,避免把超大请求体完整读入内存
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit():
        if int(content_length) > MAX_AVATAR_BYTES + _AVATAR_MULTIPART_OVERHEAD:
            raise HTTPException(status_code=413, detail="头像文件超过 2MB 大小限制")
    # 限量读取(最多 MAX+1 字节)做硬性兜底,覆盖 Content-Length 缺失或虚报的情况
    data = await file.read(MAX_AVATAR_BYTES + 1)
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="头像文件超过 2MB 大小限制")
    content_type = _sniff_avatar_content_type(data)
    if not content_type:
        raise HTTPException(status_code=400, detail="仅支持 png/jpeg/webp/gif 格式的图片")
    data_url = f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}"
    avatar = db.get(UserAvatar, current_user.id)
    if avatar:
        avatar.data_url = data_url
        avatar.updated_at = utc_now()
    else:
        avatar = UserAvatar(user_id=current_user.id, data_url=data_url)
    db.add(avatar)
    db.commit()
    # 响应同样不内联二进制:返回资源指针,前端经 GET /me/avatar 拉取字节
    return AvatarRead(avatar_url=AVATAR_RESOURCE_PATH)


@router.delete("/me/avatar", status_code=204)
def delete_my_avatar(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> Response:
    """删除当前用户头像(无头像时幂等 204)。"""
    avatar = db.get(UserAvatar, current_user.id)
    if avatar:
        db.delete(avatar)
        db.commit()
    return Response(status_code=204)


@router.post("/users", response_model=UserRead)
def create_user(
    request: UserCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> UserRead:
    if not is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Only administrator can create accounts")
    if request.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Cannot create accounts for another tenant")
    username = request.username.strip()
    if not username or not request.password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    existing = db.exec(
        select(User).where(User.tenant_id == request.tenant_id, User.username == username)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Account already exists")
    user = User(
        tenant_id=request.tenant_id,
        username=username,
        display_name=(request.display_name or username).strip()[:80],
        role=request.role,
        business_role="platform_admin" if request.role == "admin" else "member",
        authorization_source="local",
        password_hash=hash_password(request.password),
    )
    db.add(user)
    db.flush()
    record_account_event(
        db,
        tenant_id=request.tenant_id,
        event_type="user_created",
        actor_user_id=current_user.id,
        subject_user_id=user.id,
        subject_ref=user.username,
        detail={"account_role": user.role, "authorization_source": user.authorization_source},
    )
    db.commit()
    db.refresh(user)
    return _user_read(user)


@router.get("/users", response_model=list[UserRead])
def list_users(
    tenant_id: str = Query(...),
    include_channel: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[UserRead]:
    ensure_current_user_tenant(tenant_id, current_user)
    statement = select(User).where(User.tenant_id == tenant_id)
    # 非管理员只需要为处理人选择器读取内部成员。不能依赖前端过滤，否则
    # include_channel=true 会把渠道客户及群聊虚拟账号暴露给任意租户成员。
    if not is_admin_user(current_user) or not include_channel:
        statement = statement.where(User.source.in_(["web", "oidc"]))
    rows = db.exec(statement.order_by(User.created_at.desc())).all()
    if include_channel:
        # 附带内部成员已绑定的渠道身份，供处理人选择器判断当前 binding 是否可达。
        from app.db.models import ChannelIdentity

        all_identities: dict[str, list[ChannelIdentity]] = {}
        user_ids = [row.id for row in rows]
        identities = (
            db.exec(
                select(ChannelIdentity).where(
                    ChannelIdentity.tenant_id == tenant_id,
                    ChannelIdentity.staffdeck_user_id.in_(user_ids),
                    ~ChannelIdentity.external_user_id.startswith("group:"),
                )
            ).all()
            if user_ids
            else []
        )
        for ci in identities:
            all_identities.setdefault(ci.staffdeck_user_id, []).append(ci)
        result = []
        for row in rows:
            cis = all_identities.get(row.id)
            identities = (
                [
                    UserChannelIdentity(
                        channel=ci.channel,
                        display_name=ci.display_name,
                        external_user_id=ci.external_user_id,
                        external_account_scope=ci.external_account_scope,
                    )
                    for ci in cis
                ]
                if cis
                else None
            )
            result.append(_user_read(row, channel_identities=identities))
        return result
    return [_user_read(row) for row in rows]


@router.post("/users/invitations", response_model=UserInvitationCreated)
def invite_user(
    request: UserInvitationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> UserInvitationCreated:
    _require_admin(current_user, request.tenant_id)
    row, token = create_invitation(
        db,
        tenant_id=request.tenant_id,
        username=request.username,
        display_name=request.display_name or request.username,
        role=request.role,
        business_role=request.business_role,
        auth_source=request.auth_source,
        invited_by=current_user,
    )
    return UserInvitationCreated(
        **_invitation_read(row).model_dump(),
        invite_token=token,
        accept_path=(
            "/api/auth/oidc/login?return_to=%2Fworkspace%2Fgallery"
            if row.auth_source == "oidc"
            else f"/login?tenant_id={row.tenant_id}&invite_token={token}"
        ),
    )


@router.get("/users/invitations", response_model=list[UserInvitationRead])
def list_user_invitations(
    tenant_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[UserInvitationRead]:
    _require_admin(current_user, tenant_id)
    now = utc_now()
    rows = db.exec(
        select(UserInvitation)
        .where(UserInvitation.tenant_id == tenant_id)
        .order_by(UserInvitation.created_at.desc())
    ).all()
    changed = False
    for row in rows:
        if row.status == "pending" and row.expires_at <= now:
            row.status = "expired"
            row.updated_at = now
            db.add(row)
            changed = True
    if changed:
        db.commit()
    return [_invitation_read(row) for row in rows]


@router.post("/users/invitations/{invitation_id}/cancel", response_model=UserInvitationRead)
def cancel_user_invitation(
    invitation_id: str,
    tenant_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> UserInvitationRead:
    _require_admin(current_user, tenant_id)
    return _invitation_read(
        cancel_invitation(db, tenant_id=tenant_id, invitation_id=invitation_id, actor=current_user)
    )


@router.post("/invitations/accept", response_model=LoginResponse)
def accept_user_invitation(
    request: UserInvitationAcceptRequest,
    db: Session = Depends(get_session),
) -> LoginResponse:
    set_tenant_context(db, request.tenant_id)
    ensure_tenant(db, request.tenant_id)
    user = accept_invitation(
        db,
        tenant_id=request.tenant_id,
        token=request.token,
        password=request.password,
    )
    return LoginResponse(token=create_access_token(user), user=_user_read(user))


@router.get("/users/lifecycle-events", response_model=list[AccountLifecycleEventRead])
def list_account_lifecycle_events(
    tenant_id: str = Query(...),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[AccountLifecycleEventRead]:
    _require_admin(current_user, tenant_id)
    rows = db.exec(
        select(AccountLifecycleEvent)
        .where(AccountLifecycleEvent.tenant_id == tenant_id)
        .order_by(AccountLifecycleEvent.occurred_at.desc())
        .limit(limit)
    ).all()
    return [_lifecycle_event_read(row) for row in rows]


@router.get(
    "/me/api-credentials",
    response_model=list[AccountAPICredentialRead],
)
def list_account_api_credentials(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[AccountAPICredentialRead]:
    client = _ensure_account_api_client(db, current_user.tenant_id, current_user)
    if not client:
        return []
    rows = db.exec(
        select(APICredential)
        .where(
            APICredential.tenant_id == current_user.tenant_id,
            APICredential.client_id == client.id,
            APICredential.agent_id.is_(None),
        )
        .order_by(APICredential.created_at.desc())
    ).all()
    db.commit()
    return [_account_api_credential_read(row, current_user.id) for row in rows]


@router.post(
    "/me/api-credentials",
    response_model=AccountAPICredentialCreated,
)
def create_account_api_credential(
    request: AccountAPICredentialCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> AccountAPICredentialCreated:
    client = _ensure_account_api_client(db, current_user.tenant_id, current_user)
    token, prefix, digest = generate_api_key()
    row = APICredential(
        tenant_id=current_user.tenant_id,
        client_id=client.id,
        agent_id=None,
        name=request.name.strip(),
        key_prefix=prefix,
        key_digest=digest,
        scopes_json=sorted(USER_FULL_ACCESS_SCOPES),
        expires_at=request.expires_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return AccountAPICredentialCreated(
        **_account_api_credential_read(row, current_user.id).model_dump(),
        api_key=token,
    )


@router.post(
    "/me/api-credentials/{credential_id}/rotate",
    response_model=AccountAPICredentialCreated,
)
def rotate_account_api_credential(
    credential_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> AccountAPICredentialCreated:
    row = _get_account_api_credential(
        db, current_user.tenant_id, current_user.id, credential_id
    )
    token, prefix, digest = generate_api_key()
    row.key_prefix = prefix
    row.key_digest = digest
    row.status = "active"
    row.revoked_at = None
    row.updated_at = utc_now()
    db.add(row)
    db.commit()
    db.refresh(row)
    return AccountAPICredentialCreated(
        **_account_api_credential_read(row, current_user.id).model_dump(),
        api_key=token,
    )


@router.post(
    "/me/api-credentials/{credential_id}/revoke",
    response_model=AccountAPICredentialRead,
)
def revoke_account_api_credential(
    credential_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> AccountAPICredentialRead:
    row = _get_account_api_credential(
        db, current_user.tenant_id, current_user.id, credential_id
    )
    row.status = "revoked"
    row.revoked_at = utc_now()
    row.updated_at = utc_now()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _account_api_credential_read(row, current_user.id)


@router.put("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: str,
    request: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> UserRead:
    _require_admin(current_user, request.tenant_id)
    user = db.get(User, user_id)
    if not user or user.tenant_id != request.tenant_id:
        raise HTTPException(status_code=404, detail="Account not found")
    changes: dict[str, object] = {}
    if request.display_name is not None:
        display_name = request.display_name.strip()[:80]
        user.display_name = display_name or user.username
        changes["display_name"] = user.display_name
    if request.password is not None:
        password = request.password.strip()
        if password:
            user.password_hash = hash_password(password)
            user.session_version += 1
            changes["password_changed"] = True
    if request.role is not None and request.role != user.role:
        if user.authorization_source.startswith("oidc"):
            raise HTTPException(
                status_code=400,
                detail="OIDC-managed account roles must be changed in Casdoor",
            )
        if user.id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot change your own account role")
        user.role = request.role
        user.business_role = "platform_admin" if request.role == "admin" else "member"
        user.session_version += 1
        changes["account_role"] = user.role
    user.updated_at = utc_now()
    db.add(user)
    if changes:
        record_account_event(
            db,
            tenant_id=request.tenant_id,
            event_type="user_updated",
            actor_user_id=current_user.id,
            subject_user_id=user.id,
            subject_ref=user.username,
            detail=changes,
        )
    db.commit()
    db.refresh(user)
    return _user_read(user)


@router.post("/users/{user_id}/status", response_model=UserRead)
def set_user_status(
    user_id: str,
    request: UserStatusRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> UserRead:
    _require_admin(current_user, request.tenant_id)
    user = db.get(User, user_id)
    if not user or user.tenant_id != request.tenant_id:
        raise HTTPException(status_code=404, detail="Account not found")
    if user.id == current_user.id and request.status != "active":
        raise HTTPException(status_code=400, detail="Cannot suspend your own account")
    previous = user.status
    if previous == request.status:
        return _user_read(user)
    user.status = request.status
    user.session_version += 1
    user.failed_login_attempts = 0
    user.locked_until = None
    user.identity_sync_status = "pending" if user.source == "oidc" else "not_configured"
    user.updated_at = utc_now()
    db.add(user)
    record_account_event(
        db,
        tenant_id=request.tenant_id,
        event_type="user_status_changed",
        actor_user_id=current_user.id,
        subject_user_id=user.id,
        subject_ref=user.username,
        detail={
            "from": previous,
            "to": user.status,
            "reason": request.reason,
            "identity_sync_status": user.identity_sync_status,
        },
    )
    db.commit()
    db.refresh(user)
    if user.source == "oidc":
        tenant = ensure_tenant(db, request.tenant_id)
        sync = CasdoorManagementClient().sync_user_forbidden(
            organization=tenant.casdoor_organization,
            username=user.username,
            forbidden=user.status == "suspended",
        )
        user.identity_sync_status = sync.status
        user.updated_at = utc_now()
        db.add(user)
        record_account_event(
            db,
            tenant_id=request.tenant_id,
            event_type="identity_status_synced",
            actor_user_id=current_user.id,
            subject_user_id=user.id,
            subject_ref=user.username,
            outcome="allowed" if sync.status == "synced" else "degraded",
            reason=sync.reason,
            detail={"identity_sync_status": sync.status},
        )
        db.commit()
        db.refresh(user)
    return _user_read(user)


@router.post("/users/{user_id}/force-logout", response_model=UserRead)
def force_logout_user(
    user_id: str,
    request: UserForceLogoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> UserRead:
    _require_admin(current_user, request.tenant_id)
    user = db.get(User, user_id)
    if not user or user.tenant_id != request.tenant_id:
        raise HTTPException(status_code=404, detail="Account not found")
    user.session_version += 1
    user.updated_at = utc_now()
    db.add(user)
    record_account_event(
        db,
        tenant_id=request.tenant_id,
        event_type="sessions_revoked",
        actor_user_id=current_user.id,
        subject_user_id=user.id,
        subject_ref=user.username,
        reason=request.reason,
        detail={"session_version": user.session_version},
    )
    db.commit()
    db.refresh(user)
    return _user_read(user)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    tenant_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict[str, bool]:
    _require_admin(current_user, tenant_id)
    user = db.get(User, user_id)
    if not user or user.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Account not found")
    if user.id == current_user.id or is_admin_user(user):
        raise HTTPException(status_code=400, detail="Administrator account cannot be deleted")
    # 头像为独立小表、无外键级联:显式随用户删除,避免残留孤儿记录
    avatar = db.get(UserAvatar, user_id)
    if avatar:
        db.delete(avatar)
    record_account_event(
        db,
        tenant_id=tenant_id,
        event_type="user_deleted",
        actor_user_id=current_user.id,
        subject_user_id=user.id,
        subject_ref=user.username,
    )
    db.delete(user)
    db.commit()
    return {"ok": True}


def _user_read(
    user: User,
    avatar_url: Optional[str] = None,
    channel_identities: Optional[list[UserChannelIdentity]] = None,
    include_enterprise_permissions: bool = False,
    db: Session | None = None,
) -> UserRead:
    tenant = db.get(Tenant, user.tenant_id) if db else None
    return UserRead(
        id=user.id,
        tenant_id=user.tenant_id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        business_role=user.business_role,
        authorization_source=user.authorization_source,
        identity_groups=list(user.identity_groups_json or []),
        role_synced_at=user.role_synced_at.isoformat() if user.role_synced_at else None,
        enterprise_permissions=(
            enterprise_capabilities(get_settings(), user=user, db=db)
            if include_enterprise_permissions
            else {}
        ),
        source=user.source,
        status=user.status,
        session_version=user.session_version,
        identity_sync_status=user.identity_sync_status,
        preferred_locale=user.preferred_locale,
        preferred_timezone=user.preferred_timezone,
        effective_locale=user.preferred_locale or (tenant.default_locale if tenant else "en"),
        effective_timezone=user.preferred_timezone or (tenant.default_timezone if tenant else "UTC"),
        avatar_url=avatar_url,
        created_at=user.created_at.isoformat() if user.created_at else None,
        updated_at=user.updated_at.isoformat() if user.updated_at else None,
        channel_identities=channel_identities,
    )


def _preferences_read(db: Session, user: User) -> PreferencesRead:
    tenant = db.get(Tenant, user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return PreferencesRead(
        user_locale=user.preferred_locale,
        user_timezone=user.preferred_timezone,
        tenant_default_locale=tenant.default_locale,
        tenant_default_timezone=tenant.default_timezone,
        tenant_default_currency=tenant.default_currency,
        effective_locale=user.preferred_locale or tenant.default_locale,
        effective_timezone=user.preferred_timezone or tenant.default_timezone,
    )


def _validate_timezone(value: str) -> None:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=400, detail="Timezone is invalid") from exc


def _invitation_read(row: UserInvitation) -> UserInvitationRead:
    return UserInvitationRead(
        id=row.id,
        tenant_id=row.tenant_id,
        username=row.username,
        display_name=row.display_name,
        role=row.role,
        business_role=row.business_role,
        auth_source=row.auth_source,
        status=row.status,
        invited_by_user_id=row.invited_by_user_id,
        accepted_by_user_id=row.accepted_by_user_id,
        expires_at=row.expires_at.isoformat(),
        accepted_at=row.accepted_at.isoformat() if row.accepted_at else None,
        cancelled_at=row.cancelled_at.isoformat() if row.cancelled_at else None,
        created_at=row.created_at.isoformat(),
    )


def _lifecycle_event_read(row: AccountLifecycleEvent) -> AccountLifecycleEventRead:
    return AccountLifecycleEventRead(
        id=row.id,
        tenant_id=row.tenant_id,
        event_type=row.event_type,
        actor_user_id=row.actor_user_id,
        subject_user_id=row.subject_user_id,
        subject_ref=row.subject_ref,
        outcome=row.outcome,
        reason=row.reason,
        detail=dict(row.detail_json or {}),
        occurred_at=row.occurred_at.isoformat(),
    )


def _avatar_pointer_for(db: Session, user_id: str) -> Optional[str]:
    """头像存在性指针:有头像返回资源路径,无返回 None(绝不内联二进制)。"""
    avatar = db.get(UserAvatar, user_id)
    return AVATAR_RESOURCE_PATH if avatar else None


def _parse_avatar_data_url(data_url: str) -> Optional[tuple[bytes, str]]:
    """拆解 data:image/*;base64,... 为(字节, content-type);非法返回 None。"""
    try:
        meta, payload = data_url.split(",", 1)
        content_type = meta.removeprefix("data:").removesuffix(";base64")
        if not content_type.startswith("image/"):
            return None
        return base64.b64decode(payload), content_type
    except (ValueError, TypeError):
        return None


def _require_admin(user: User, tenant_id: str) -> None:
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Only administrator can manage accounts")
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Cannot manage accounts for another tenant")


def _account_api_client_name(user_id: str) -> str:
    return f"{ACCOUNT_API_CLIENT_PREFIX}:{user_id}"


def _find_account_api_client(
    db: Session,
    tenant_id: str,
    user_id: str,
) -> APIClient | None:
    return db.exec(
        select(APIClient).where(
            APIClient.tenant_id == tenant_id,
            APIClient.name == _account_api_client_name(user_id),
        )
    ).first()


def _ensure_account_api_client(db: Session, tenant_id: str, user: User) -> APIClient:
    row = _find_account_api_client(db, tenant_id, user.id)
    required_scopes = sorted(USER_FULL_ACCESS_SCOPES)
    if row:
        row.created_by_user_id = user.id
        row.status = "active"
        row.scopes_json = required_scopes
        row.metadata_json = {
            **dict(row.metadata_json or {}),
            "managed_by": "account_settings",
            "credential_mode": "user_full_access",
            "subject_user_id": user.id,
        }
        row.updated_at = utc_now()
        db.add(row)
        credentials = db.exec(
            select(APICredential).where(
                APICredential.tenant_id == tenant_id,
                APICredential.client_id == row.id,
                APICredential.agent_id.is_(None),
            )
        ).all()
        for credential in credentials:
            credential.scopes_json = required_scopes
            credential.updated_at = utc_now()
            db.add(credential)
        db.flush()
        return row
    row = APIClient(
        tenant_id=tenant_id,
        name=_account_api_client_name(user.id),
        description=f"账号 {user.username} 的全量 API 密钥，权限随账号可见员工动态变化。",
        scopes_json=required_scopes,
        status="active",
        created_by_user_id=user.id,
        metadata_json={
            "managed_by": "account_settings",
            "credential_mode": "user_full_access",
            "subject_user_id": user.id,
        },
    )
    db.add(row)
    db.flush()
    return row


def _get_account_api_credential(
    db: Session,
    tenant_id: str,
    user_id: str,
    credential_id: str,
) -> APICredential:
    client = _find_account_api_client(db, tenant_id, user_id)
    row = db.get(APICredential, credential_id)
    if (
        not client
        or not row
        or row.tenant_id != tenant_id
        or row.client_id != client.id
        or row.agent_id is not None
    ):
        raise HTTPException(status_code=404, detail="Account API credential not found")
    return row


def _account_api_credential_read(
    row: APICredential,
    user_id: str,
) -> AccountAPICredentialRead:
    return AccountAPICredentialRead(
        id=row.id,
        user_id=user_id,
        name=row.name,
        key_prefix=f"{row.key_prefix}…",
        scopes=list(row.scopes_json or []),
        status=row.status,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
        revoked_at=row.revoked_at,
    )
