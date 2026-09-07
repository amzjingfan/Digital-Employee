from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session, set_tenant_context
from app.db.models import Tenant, User

TOKEN_TTL_SECONDS = 60 * 60 * 24 * 14
OIDC_SESSION_COOKIE = "staffdeck_session"
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${base64.urlsafe_b64encode(digest).decode('utf-8')}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        _algo, salt, _digest = stored_hash.split("$", 2)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    candidate = f"pbkdf2_sha256${salt}${base64.urlsafe_b64encode(digest).decode('utf-8')}"
    return hmac.compare_digest(candidate, stored_hash)


def create_access_token(user: User, ttl_seconds: int = TOKEN_TTL_SECONDS) -> str:
    payload = {
        "tenant_id": user.tenant_id,
        "user_id": user.id,
        "username": user.username,
        "session_version": user.session_version,
        "exp": int(time.time()) + ttl_seconds,
    }
    body = _b64(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    signature = _sign(body)
    return f"{body}.{signature}"


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[Session, Depends(get_session)],
) -> User:
    token = credentials.credentials if credentials else request.cookies.get(OIDC_SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = _decode_token(token)
    tenant_id = str(payload.get("tenant_id") or "")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Invalid user token")
    set_tenant_context(db, tenant_id)
    tenant = db.get(Tenant, tenant_id)
    if not tenant or tenant.status != "active":
        raise HTTPException(status_code=401, detail="Tenant is not active")
    user = db.get(User, payload.get("user_id", ""))
    if not user or user.tenant_id != tenant_id:
        raise HTTPException(status_code=401, detail="Invalid user token")
    if user.status != "active":
        raise HTTPException(status_code=401, detail="Account is suspended")
    token_session_version = payload.get("session_version", 1)
    if not isinstance(token_session_version, int) or token_session_version != user.session_version:
        raise HTTPException(status_code=401, detail="Session has been revoked")
    return user


def ensure_current_user_tenant(tenant_id: str, current_user: User) -> None:
    if not isinstance(current_user, User):
        raise HTTPException(status_code=401, detail="Not authenticated")
    if tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")


def require_current_tenant(
    tenant_id: Annotated[str, Query()],
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    ensure_current_user_tenant(tenant_id, current_user)
    return current_user


def _decode_token(token: str) -> dict[str, Any]:
    try:
        body, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    if not hmac.compare_digest(_sign(body), signature):
        raise HTTPException(status_code=401, detail="Invalid token signature")
    try:
        payload = json.loads(base64.urlsafe_b64decode(_pad_b64(body)).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token payload") from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=401, detail="Token expired")
    return payload


def _sign(body: str) -> str:
    secret = get_settings().app_secret.encode("utf-8")
    return _b64(hmac.new(secret, body.encode("utf-8"), hashlib.sha256).digest())


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _pad_b64(value: str) -> bytes:
    return (value + "=" * (-len(value) % 4)).encode("utf-8")
