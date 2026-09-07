from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import jwt

from app.config import Settings
from app.db.models import AgentServiceIdentity

_ALGORITHMS = ["RS256", "RS512", "ES256", "ES384", "ES512"]
_cache_lock = threading.Lock()
_token_cache: dict[str, tuple[str, float, ServiceTokenReceipt]] = {}


class ServiceIdentityError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ServiceTokenReceipt:
    subject: str
    audience: tuple[str, ...]
    expires_at: datetime
    token_fingerprint: str


def authenticate_service_identity(
    identity: AgentServiceIdentity,
    settings: Settings,
) -> ServiceTokenReceipt:
    if identity.status != "active":
        raise ServiceIdentityError("service_identity_disabled", "数字员工服务身份未启用")
    _validate_provider_configuration(identity, settings)
    now = time.time()
    with _cache_lock:
        cached = _token_cache.get(identity.id)
        if cached and cached[1] > now + 60:
            return cached[2]

    secret = _load_client_secret(
        settings.work_task_m2m_secret_file,
        identity.credential_ref,
        identity.client_id,
    )
    try:
        response = httpx.post(
            identity.token_endpoint,
            data={
                "grant_type": "client_credentials",
                "client_id": identity.client_id,
                "client_secret": secret,
                "scope": "openid",
            },
            headers={"Accept": "application/json"},
            timeout=max(1.0, settings.work_task_m2m_timeout_seconds),
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ServiceIdentityError(
            "service_token_exchange_failed",
            "Casdoor M2M Token 获取失败",
        ) from exc
    token = str(payload.get("access_token") or "") if isinstance(payload, dict) else ""
    if not token:
        raise ServiceIdentityError(
            "service_token_missing",
            "Casdoor M2M Token 响应缺少 access_token",
        )
    receipt, exp_timestamp = _validate_token(identity, token)
    with _cache_lock:
        _token_cache[identity.id] = (token, exp_timestamp, receipt)
    return receipt


def clear_service_token_cache(identity_id: str | None = None) -> None:
    with _cache_lock:
        if identity_id:
            _token_cache.pop(identity_id, None)
        else:
            _token_cache.clear()


def _validate_token(
    identity: AgentServiceIdentity,
    token: str,
) -> tuple[ServiceTokenReceipt, float]:
    try:
        key = _jwks_client(identity.jwks_uri).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=_ALGORITHMS,
            audience=identity.client_id,
            issuer=identity.issuer,
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise ServiceIdentityError(
            "service_token_validation_failed",
            "Casdoor M2M Token 签名或声明校验失败",
        ) from exc
    raw_audience = claims.get("aud")
    audience = (
        tuple(str(item) for item in raw_audience)
        if isinstance(raw_audience, list)
        else (str(raw_audience),)
    )
    exp_timestamp = float(claims["exp"])
    return (
        ServiceTokenReceipt(
            subject=str(claims["sub"]),
            audience=audience,
            expires_at=datetime.fromtimestamp(exp_timestamp, tz=UTC).replace(tzinfo=None),
            token_fingerprint="sha256:" + hashlib.sha256(token.encode()).hexdigest(),
        ),
        exp_timestamp,
    )


def _validate_provider_configuration(
    identity: AgentServiceIdentity,
    settings: Settings,
) -> None:
    expected = {
        "issuer": settings.oidc_issuer.rstrip("/"),
        "token_endpoint": settings.oidc_token_endpoint,
        "jwks_uri": settings.oidc_jwks_uri,
    }
    actual = {
        "issuer": identity.issuer.rstrip("/"),
        "token_endpoint": identity.token_endpoint,
        "jwks_uri": identity.jwks_uri,
    }
    if not all(expected.values()) or actual != expected:
        raise ServiceIdentityError(
            "service_identity_provider_mismatch",
            "岗位服务身份的 Casdoor 端点与受信部署配置不一致",
        )


def _load_client_secret(
    secret_file: str,
    credential_ref: str,
    expected_client_id: str,
) -> str:
    if not secret_file.strip():
        raise ServiceIdentityError(
            "service_secret_store_unconfigured",
            "数字员工 M2M Secret Store 未配置",
        )
    path = Path(secret_file).expanduser().resolve()
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ServiceIdentityError(
            "service_secret_store_unavailable",
            "数字员工 M2M Secret Store 不可用",
        ) from exc
    records = payload.get("credentials") if isinstance(payload, dict) else None
    row = records.get(credential_ref) if isinstance(records, dict) else None
    secret = str(row.get("client_secret") or "") if isinstance(row, dict) else ""
    stored_client_id = str(row.get("client_id") or "") if isinstance(row, dict) else ""
    if not stored_client_id or stored_client_id != expected_client_id:
        raise ServiceIdentityError(
            "service_credential_binding_mismatch",
            "数字员工服务身份与 Secret Store 凭据不匹配",
        )
    if not secret:
        raise ServiceIdentityError(
            "service_secret_missing",
            "数字员工服务身份缺少对应凭据",
        )
    return secret


@lru_cache(maxsize=16)
def _jwks_client(uri: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(uri, cache_keys=True, lifespan=300)
