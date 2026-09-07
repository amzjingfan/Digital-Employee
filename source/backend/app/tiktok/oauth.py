from __future__ import annotations

import base64
import hashlib
import re
import secrets
from datetime import timedelta
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db.models import ExternalAuthorization, TikTokOAuthState, User, utc_now
from app.security.permissions import ensure_tenant_admin

MOCK_OAUTH_TTL_SECONDS = 10 * 60
MOCK_CODE_TTL_SECONDS = 60
_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
AuthorizationType = Literal["seller", "creator", "partner", "ads", "social"]


class TikTokAuthorizationStart(BaseModel):
    authorization_type: AuthorizationType
    subject_id: str = Field(min_length=1, max_length=160)
    resource_id: str | None = Field(default=None, max_length=160)
    scopes: list[str] = Field(default_factory=list, min_length=1, max_length=20)
    code_challenge: str = Field(min_length=43, max_length=128)
    return_to: str = Field(default="/enterprise/tiktok", max_length=200)


class TikTokAuthorizationStartResponse(BaseModel):
    state: str
    authorize_url: str
    code_challenge_method: Literal["S256"] = "S256"
    expires_at: str


def state_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_return_to(value: str) -> str:
    candidate = value.strip()
    if not candidate.startswith("/") or candidate.startswith("//") or len(candidate) > 200:
        return "/enterprise/tiktok"
    return candidate


def _validate_challenge(value: str) -> str:
    challenge = value.strip()
    if len(challenge) < 43 or len(challenge) > 128 or not _BASE64URL_RE.fullmatch(challenge):
        raise HTTPException(status_code=422, detail="PKCE code_challenge must be base64url encoded")
    return challenge


def start_mock_authorization(
    db: Session, user: User, request: TikTokAuthorizationStart
) -> TikTokAuthorizationStartResponse:
    ensure_tenant_admin(user.tenant_id, user)
    challenge = _validate_challenge(request.code_challenge)
    now = utc_now()
    expired = db.exec(
        select(TikTokOAuthState).where(TikTokOAuthState.expires_at <= now)
    ).all()
    for row in expired:
        db.delete(row)
    state = secrets.token_urlsafe(32)
    expires_at = now + timedelta(seconds=MOCK_OAUTH_TTL_SECONDS)
    db.add(
        TikTokOAuthState(
            state_hash=state_hash(state),
            tenant_id=user.tenant_id,
            user_id=user.id,
            authorization_type=request.authorization_type,
            subject_id=request.subject_id.strip(),
            resource_id=request.resource_id.strip() if request.resource_id else None,
            scopes_json=sorted({scope.strip() for scope in request.scopes if scope.strip()}),
            code_challenge=challenge,
            return_to=_safe_return_to(request.return_to),
            expires_at=expires_at,
        )
    )
    db.commit()
    return TikTokAuthorizationStartResponse(
        state=state,
        authorize_url=f"/api/enterprise/tiktok/mock/authorize?state={state}",
        expires_at=expires_at.isoformat() + "Z",
    )


def approve_mock_authorization(db: Session, state: str) -> str:
    row = db.get(TikTokOAuthState, state_hash(state))
    if not row or row.expires_at <= utc_now():
        raise HTTPException(status_code=400, detail="TikTok OAuth state is invalid or expired")
    if row.code_hash:
        raise HTTPException(status_code=400, detail="TikTok OAuth authorization code already issued")
    code = secrets.token_urlsafe(32)
    row.code_hash = state_hash(code)
    row.code_expires_at = utc_now() + timedelta(seconds=MOCK_CODE_TTL_SECONDS)
    row.approved_at = utc_now()
    db.add(row)
    db.commit()
    return code


def exchange_mock_authorization(
    db: Session, state: str, code: str, code_verifier: str
) -> ExternalAuthorization:
    row = db.get(TikTokOAuthState, state_hash(state))
    if not row or row.expires_at <= utc_now() or not row.code_hash:
        raise HTTPException(status_code=400, detail="TikTok OAuth authorization code is invalid")
    if not row.code_expires_at or row.code_expires_at <= utc_now():
        raise HTTPException(status_code=400, detail="TikTok OAuth authorization code expired")
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("utf-8")).digest()
    ).decode("ascii").rstrip("=")
    if not secrets.compare_digest(expected, row.code_challenge):
        raise HTTPException(status_code=400, detail="TikTok OAuth PKCE verification failed")
    if not secrets.compare_digest(row.code_hash, state_hash(code)):
        raise HTTPException(status_code=400, detail="TikTok OAuth authorization code is invalid")

    fingerprint = "sha256:" + hashlib.sha256(
        f"mock-access-token:{row.state_hash}".encode()
    ).hexdigest()
    authorization = db.exec(
        select(ExternalAuthorization).where(
            ExternalAuthorization.tenant_id == row.tenant_id,
            ExternalAuthorization.provider == "tiktok",
            ExternalAuthorization.authorization_type == row.authorization_type,
            ExternalAuthorization.subject_id == row.subject_id,
            ExternalAuthorization.resource_id == row.resource_id,
        )
    ).first()
    if authorization is None:
        authorization = ExternalAuthorization(
            tenant_id=row.tenant_id,
            provider="tiktok",
            authorization_type=row.authorization_type,
            subject_id=row.subject_id,
            resource_id=row.resource_id,
            scopes_json=list(row.scopes_json or []),
            credential_ref=f"secret://tiktok/{secrets.token_urlsafe(18)}",
            token_fingerprint=fingerprint,
            metadata_json={"authorization_flow": "mock", "pkce": "S256", "review_status": "approved"},
        )
    else:
        authorization.scopes_json = list(row.scopes_json or [])
        authorization.token_fingerprint = fingerprint
        authorization.status = "active"
        authorization.revision += 1
        authorization.updated_at = utc_now()
        authorization.metadata_json = {
            **(authorization.metadata_json or {}),
            "authorization_flow": "mock",
            "pkce": "S256",
            "review_status": "approved",
        }
    db.add(authorization)
    db.delete(row)
    db.commit()
    db.refresh(authorization)
    return authorization
