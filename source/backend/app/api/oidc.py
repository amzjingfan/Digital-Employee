from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
from datetime import timedelta
from functools import lru_cache
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from app.accounts.lifecycle import record_account_event
from app.config import Settings, get_settings
from app.db import get_session, set_tenant_context
from app.db.models import (
    OIDCLoginState,
    Tenant,
    User,
    UserIdentity,
    UserInvitation,
    utc_now,
)
from app.security.auth import OIDC_SESSION_COOKIE, create_access_token, hash_password
from app.security.business_roles import (
    GroupRoleMappingError,
    normalized_group_claim,
    parse_group_role_mapping,
    resolve_business_role,
)
from app.tiktok.service import reconcile_casdoor_membership

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])
_OIDC_STATE_TTL_SECONDS = 10 * 60
_OIDC_ALGORITHMS = ["RS256", "RS512", "ES256", "ES384", "ES512"]


class OIDCConfigRead(BaseModel):
    enabled: bool
    login_url: str | None = None


@router.get("/oidc/config", response_model=OIDCConfigRead)
def oidc_config() -> OIDCConfigRead:
    settings = get_settings()
    return OIDCConfigRead(
        enabled=settings.oidc_enabled,
        login_url="/api/auth/oidc/login" if settings.oidc_enabled else None,
    )


@router.get("/oidc/login")
def oidc_login(
    db: Annotated[Session, Depends(get_session)],
    return_to: Annotated[str, Query()] = "/workspace/gallery",
    locale: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    settings = _validated_settings()
    now = utc_now()
    expired = db.exec(select(OIDCLoginState).where(OIDCLoginState.expires_at <= now)).all()
    for row in expired:
        db.delete(row)

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(32)
    db.add(
        OIDCLoginState(
            state_hash=_state_hash(state),
            code_verifier=verifier,
            nonce=nonce,
            return_to=_safe_return_to(return_to),
            expires_at=now + timedelta(seconds=_OIDC_STATE_TTL_SECONDS),
        )
    )
    db.commit()

    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode()
    challenge = challenge.rstrip("=")
    authorization_parameters = {
            "client_id": settings.oidc_client_id,
            "response_type": "code",
            "redirect_uri": settings.oidc_redirect_uri,
            "scope": " ".join(settings.oidc_scope_list),
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    if locale in {"zh-CN", "en"}:
        authorization_parameters["ui_locales"] = locale
    query = urlencode(authorization_parameters)
    return RedirectResponse(f"{settings.oidc_authorization_endpoint}?{query}", status_code=302)


@router.get("/oidc/callback")
async def oidc_callback(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    settings = _validated_settings()
    if error:
        raise HTTPException(status_code=401, detail="OIDC authorization was denied")
    if not code or not state:
        raise HTTPException(status_code=400, detail="OIDC callback is missing code or state")

    login_state = db.get(OIDCLoginState, _state_hash(state))
    if not login_state or login_state.expires_at <= utc_now():
        raise HTTPException(status_code=400, detail="OIDC state is invalid or expired")
    db.delete(login_state)
    db.commit()

    token_data = await _exchange_code(settings, code, login_state.code_verifier)
    raw_id_token = str(token_data.get("id_token") or token_data.get("access_token") or "")
    if not raw_id_token:
        raise HTTPException(status_code=502, detail="OIDC provider returned no identity token")
    claims = await run_in_threadpool(_validate_id_token, settings, raw_id_token)
    if not hmac.compare_digest(str(claims.get("nonce") or ""), login_state.nonce):
        raise HTTPException(status_code=401, detail="OIDC nonce validation failed")

    tenant_id, username, display_name, role, business_role, groups = _mapped_identity(
        settings, claims
    )
    set_tenant_context(db, tenant_id)
    user = _upsert_user_identity(
        db,
        tenant_id=tenant_id,
        issuer=settings.oidc_issuer,
        subject=str(claims["sub"]),
        username=username,
        display_name=display_name,
        role=role,
        business_role=business_role,
        groups=groups,
    )
    token = create_access_token(user, ttl_seconds=settings.oidc_session_ttl_seconds)
    response = RedirectResponse(_append_oidc_success(login_state.return_to), status_code=302)
    response.set_cookie(
        OIDC_SESSION_COOKIE,
        token,
        max_age=settings.oidc_session_ttl_seconds,
        httponly=True,
        secure=settings.oidc_cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
) -> Response:
    authorization = request.headers.get("authorization", "")
    bearer = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    token = bearer or request.cookies.get(OIDC_SESSION_COOKIE)
    if token:
        try:
            from app.security.auth import _decode_token

            payload = _decode_token(token)
            tenant_id = str(payload.get("tenant_id") or "")
            user_id = str(payload.get("user_id") or "")
            if tenant_id and user_id:
                set_tenant_context(db, tenant_id)
                user = db.get(User, user_id)
                if user and user.tenant_id == tenant_id:
                    record_account_event(
                        db,
                        tenant_id=tenant_id,
                        event_type="logout",
                        actor_user_id=user.id,
                        subject_user_id=user.id,
                        subject_ref=user.username,
                    )
                    db.commit()
        except HTTPException:
            db.rollback()
    response = Response(status_code=204)
    response.delete_cookie(OIDC_SESSION_COOKIE, path="/", samesite="lax")
    return response


async def _exchange_code(settings: Settings, code: str, verifier: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                settings.oidc_token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.oidc_client_id,
                    "client_secret": settings.oidc_client_secret,
                    "code": code,
                    "redirect_uri": settings.oidc_redirect_uri,
                    "code_verifier": verifier,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("OIDC code exchange failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="OIDC code exchange failed") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="OIDC token response is invalid")
    return payload


def _validate_id_token(settings: Settings, token: str) -> dict[str, Any]:
    try:
        key = _jwks_client(settings.oidc_jwks_uri).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=_OIDC_ALGORITHMS,
            audience=settings.oidc_client_id,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="OIDC identity token validation failed") from exc
    return dict(claims)


@lru_cache(maxsize=4)
def _jwks_client(uri: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(uri, cache_keys=True, lifespan=300)


def _mapped_identity(
    settings: Settings, claims: dict[str, Any]
) -> tuple[str, str, str, str, str, list[str]]:
    try:
        mapping = json.loads(settings.oidc_tenant_mapping_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="OIDC tenant mapping is invalid") from exc
    if not isinstance(mapping, dict):
        raise HTTPException(status_code=500, detail="OIDC tenant mapping is invalid")

    organization = str(claims.get("owner") or claims.get("organization") or "").strip()
    tenant_id = str(mapping.get(organization) or "").strip()
    if not organization or not tenant_id:
        raise HTTPException(status_code=403, detail="OIDC organization is not mapped to a tenant")

    preferred_username = str(claims.get("preferred_username") or "").strip()
    casdoor_name = str(claims.get("name") or "").strip()
    display_name_claim = str(claims.get("displayName") or "").strip()
    username = preferred_username or casdoor_name
    display_name = display_name_claim or (casdoor_name if preferred_username else username)
    if not username or not str(claims.get("sub") or "").strip():
        raise HTTPException(status_code=401, detail="OIDC identity claims are incomplete")
    role = "admin" if claims.get("isAdmin") is True else "member"
    try:
        groups = normalized_group_claim(claims.get(settings.oidc_group_claim))
        mapping = parse_group_role_mapping(settings.oidc_group_role_mapping_json)
        business_role = (
            "platform_admin"
            if role == "admin"
            else resolve_business_role(
                groups=groups,
                mapping=mapping,
                require_mapped_group=settings.oidc_require_mapped_group,
            )
        )
    except GroupRoleMappingError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return tenant_id, username[:120], display_name[:80], role, business_role, groups


def _upsert_user_identity(
    db: Session,
    *,
    tenant_id: str,
    issuer: str,
    subject: str,
    username: str,
    display_name: str,
    role: str,
    business_role: str,
    groups: list[str],
) -> User:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=403, detail="Mapped Joukir tenant does not exist")
    if tenant.status != "active":
        raise HTTPException(status_code=403, detail="Mapped Joukir tenant is not active")

    identity = db.exec(
        select(UserIdentity).where(
            UserIdentity.tenant_id == tenant_id,
            UserIdentity.provider == "oidc",
            UserIdentity.issuer == issuer,
            UserIdentity.subject == subject,
        )
    ).first()
    if identity:
        user = db.get(User, identity.user_id)
        if not user:
            raise HTTPException(status_code=409, detail="OIDC identity link is orphaned")
        _reject_suspended_oidc_user(db, user)
    else:
        user = db.exec(
            select(User).where(User.tenant_id == tenant_id, User.username == username)
        ).first()
        if user is not None and user.source != "oidc":
            raise HTTPException(
                status_code=409,
                detail="OIDC username conflicts with an existing local account",
            )
        if user is not None:
            _reject_suspended_oidc_user(db, user)
        if user is None:
            user = User(
                tenant_id=tenant_id,
                username=username,
                display_name=display_name,
                role=role,
                business_role=business_role,
                authorization_source="oidc_groups" if role != "admin" else "oidc_admin",
                identity_groups_json=groups,
                role_synced_at=utc_now(),
                source="oidc",
                password_hash=hash_password(secrets.token_urlsafe(48)),
            )
            db.add(user)
            db.flush()
        identity = UserIdentity(
            tenant_id=tenant_id,
            user_id=user.id,
            provider="oidc",
            issuer=issuer,
            subject=subject,
        )
        db.add(identity)

    user.display_name = display_name or user.display_name
    user.role = role
    user.business_role = business_role
    user.authorization_source = "oidc_admin" if role == "admin" else "oidc_groups"
    user.identity_groups_json = groups
    user.role_synced_at = utc_now()
    user.updated_at = utc_now()
    db.add(user)
    reconcile_casdoor_membership(db, user, source="casdoor")
    pending_invitation = db.exec(
        select(UserInvitation).where(
            UserInvitation.tenant_id == tenant_id,
            UserInvitation.username == username,
            UserInvitation.auth_source == "oidc",
            UserInvitation.status == "pending",
        )
    ).first()
    if pending_invitation:
        if pending_invitation.expires_at <= utc_now():
            pending_invitation.status = "expired"
        else:
            pending_invitation.status = "accepted"
            pending_invitation.accepted_by_user_id = user.id
            pending_invitation.accepted_at = utc_now()
        pending_invitation.updated_at = utc_now()
        db.add(pending_invitation)
    record_account_event(
        db,
        tenant_id=tenant_id,
        event_type="login_succeeded",
        actor_user_id=user.id,
        subject_user_id=user.id,
        subject_ref=user.username,
        detail={"auth_source": "oidc", "issuer": issuer},
    )
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="OIDC identity is already linked") from exc
    return user


def _reject_suspended_oidc_user(db: Session, user: User) -> None:
    if user.status == "active":
        return
    record_account_event(
        db,
        tenant_id=user.tenant_id,
        event_type="login_denied",
        actor_user_id=user.id,
        subject_user_id=user.id,
        subject_ref=user.username,
        outcome="denied",
        reason="account_suspended",
    )
    db.commit()
    raise HTTPException(status_code=403, detail="OIDC account is suspended")


def _validated_settings() -> Settings:
    settings = get_settings()
    required = (
        settings.oidc_issuer,
        settings.oidc_authorization_endpoint,
        settings.oidc_token_endpoint,
        settings.oidc_jwks_uri,
        settings.oidc_client_id,
        settings.oidc_client_secret,
        settings.oidc_redirect_uri,
    )
    if not settings.oidc_enabled:
        raise HTTPException(status_code=404, detail="OIDC login is disabled")
    if not all(required):
        raise HTTPException(status_code=503, detail="OIDC login is not fully configured")
    return settings


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _safe_return_to(value: str) -> str:
    candidate = value.strip()
    if not candidate.startswith("/") or candidate.startswith("//") or len(candidate) > 1024:
        return "/workspace/gallery"
    return candidate


def _append_oidc_success(value: str) -> str:
    parsed = urlsplit(_safe_return_to(value))
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["oidc"] = "success"
    return urlunsplit(("", "", parsed.path, urlencode(query), parsed.fragment))
