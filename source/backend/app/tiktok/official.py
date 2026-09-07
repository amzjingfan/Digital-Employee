from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.db.models import (
    BusinessResource,
    BusinessResourceScope,
    ExternalAuthorization,
    TikTokOAuthState,
    User,
    utc_now,
)
from app.security.encryption import decrypt_secret, encrypt_secret
from app.security.permissions import ensure_tenant_admin
from app.tiktok.oauth import TikTokAuthorizationStartResponse, _safe_return_to, state_hash
from app.tiktok.schema import TikTokOfficialAuthorizationStart

OFFICIAL_TOKEN_ENDPOINT = "https://auth.tiktok-shops.com/api/v2/token/get"
OFFICIAL_REFRESH_ENDPOINT = "https://auth.tiktok-shops.com/api/v2/token/refresh"
OFFICIAL_API_BASE_URL = "https://open-api.tiktokglobalshop.com"
OFFICIAL_STATE_TTL_SECONDS = 10 * 60
OFFICIAL_READ_ONLY_SCOPES = frozenset(
    {
        "seller.shop.info",
        "seller.order.info",
        "seller.fulfillment.info",
        "seller.product.info",
        "shop.read",
    }
)
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")


class TikTokOfficialError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class FileTokenStore:
    """Small local secret-store adapter for development and single-node deployments."""

    def __init__(
        self,
        path: str | Path,
        *,
        encrypt: Callable[[str], str] = encrypt_secret,
        decrypt: Callable[[str], str] = decrypt_secret,
    ) -> None:
        self.path = Path(path).expanduser().resolve()
        self._encrypt = encrypt
        self._decrypt = decrypt

    def get(self, credential_ref: str) -> dict[str, Any] | None:
        records = self._read().get("credentials", {})
        row = records.get(credential_ref) if isinstance(records, dict) else None
        if not isinstance(row, dict):
            return None
        result = dict(row)
        for key in ("access_token", "refresh_token"):
            encrypted = result.pop(f"{key}_encrypted", None)
            if encrypted:
                result[key] = self._decrypt(str(encrypted))
        return result

    def put(self, credential_ref: str, values: Mapping[str, Any]) -> None:
        payload = self._read()
        records = payload.setdefault("credentials", {})
        if not isinstance(records, dict):
            raise TikTokOfficialError("token_store_invalid", "TikTok Token Store credentials must be an object")
        row: dict[str, Any] = {}
        for key, value in values.items():
            if key in {"access_token", "refresh_token"}:
                row[f"{key}_encrypted"] = self._encrypt(str(value))
            else:
                row[key] = value
        records[credential_ref] = row
        self._write(payload)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TikTokOfficialError("token_store_unavailable", "TikTok Token Store 不可用") from exc
        if not isinstance(payload, dict):
            raise TikTokOfficialError("token_store_invalid", "TikTok Token Store 格式无效")
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f".{self.path.name}.{secrets.token_hex(8)}.tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            try:
                temporary.replace(self.path)
            finally:
                if temporary.exists():
                    temporary.unlink()
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        except OSError as exc:
            raise TikTokOfficialError("token_store_unavailable", "TikTok Token Store 不可写") from exc


def sign_tiktok_request(
    *,
    path: str,
    query: Mapping[str, object],
    app_secret: str,
    body: object | None = None,
) -> str:
    """Create the HMAC-SHA256 signature required by TikTok Shop 202309 APIs."""

    parameter_string = "".join(
        f"{key}{query[key]}"
        for key in sorted(query)
        if key not in {"sign", "access_token"}
    )
    sign_string = f"{path}{parameter_string}"
    if body:
        sign_string += json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    wrapped = f"{app_secret}{sign_string}{app_secret}"
    return hmac.new(app_secret.encode("utf-8"), wrapped.encode("utf-8"), hashlib.sha256).hexdigest()


class TikTokOfficialClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        token_store: FileTokenStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.transport = transport
        self.token_store = token_store or FileTokenStore(self.settings.tiktok_token_store_file)

    def validate_configuration(self) -> None:
        if not self.settings.tiktok_official_enabled:
            raise TikTokOfficialError("tiktok_official_disabled", "TikTok 官方授权尚未启用")
        if not self.settings.tiktok_app_key.strip() or not self.settings.tiktok_app_secret:
            raise TikTokOfficialError("tiktok_official_credentials_incomplete", "TikTok App Key/Secret 未配置")
        if not self.settings.tiktok_redirect_uri.strip():
            raise TikTokOfficialError("tiktok_official_redirect_missing", "TikTok 官方回调地址未配置")
        if not self.settings.tiktok_token_store_file.strip():
            raise TikTokOfficialError("tiktok_token_store_missing", "TikTok Token Store 路径未配置")

    def exchange_code(self, code: str) -> dict[str, Any]:
        self.validate_configuration()
        try:
            with httpx.Client(timeout=self.settings.tiktok_http_timeout_seconds, transport=self.transport) as client:
                response = client.get(
                    OFFICIAL_TOKEN_ENDPOINT,
                    params={
                        "app_key": self.settings.tiktok_app_key,
                        "app_secret": self.settings.tiktok_app_secret,
                        "auth_code": code,
                        "grant_type": "authorized_code",
                    },
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                return _official_data(response.json())
        except (httpx.HTTPError, ValueError, TikTokOfficialError) as exc:
            raise TikTokOfficialError("tiktok_token_exchange_failed", "TikTok 官方授权码交换失败") from exc

    def get_access_token(self, credential_ref: str) -> str:
        record = self.token_store.get(credential_ref)
        if not record:
            raise TikTokOfficialError("tiktok_token_missing", "TikTok 官方授权凭据不存在")
        expires_at = int(record.get("access_token_expires_at") or 0)
        if record.get("access_token") and expires_at > int(time.time()) + self.settings.tiktok_token_refresh_skew_seconds:
            return str(record["access_token"])
        refresh_token = str(record.get("refresh_token") or "")
        if not refresh_token or int(record.get("refresh_token_expires_at") or 0) <= int(time.time()):
            raise TikTokOfficialError("tiktok_refresh_token_expired", "TikTok 官方 Refresh Token 已过期")
        self.validate_configuration()
        try:
            with httpx.Client(timeout=self.settings.tiktok_http_timeout_seconds, transport=self.transport) as client:
                response = client.get(
                    OFFICIAL_REFRESH_ENDPOINT,
                    params={
                        "app_key": self.settings.tiktok_app_key,
                        "app_secret": self.settings.tiktok_app_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                    },
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                data = _official_data(response.json())
        except (httpx.HTTPError, ValueError, TikTokOfficialError) as exc:
            raise TikTokOfficialError("tiktok_token_refresh_failed", "TikTok 官方 Token 刷新失败") from exc
        merged = {**record, **_token_values(data)}
        self.token_store.put(credential_ref, merged)
        return str(merged["access_token"])

    def get_authorized_shops(self, credential_ref: str) -> list[dict[str, Any]]:
        access_token = self.get_access_token(credential_ref)
        timestamp = str(int(time.time()))
        query = {"app_key": self.settings.tiktok_app_key, "timestamp": timestamp}
        query["sign"] = sign_tiktok_request(
            path="/authorization/202309/shops",
            query=query,
            app_secret=self.settings.tiktok_app_secret,
        )
        try:
            with httpx.Client(timeout=self.settings.tiktok_http_timeout_seconds, transport=self.transport) as client:
                response = client.get(
                    f"{OFFICIAL_API_BASE_URL}/authorization/202309/shops",
                    params=query,
                    headers={"Accept": "application/json", "x-tts-access-token": access_token},
                )
                response.raise_for_status()
                data = _official_data(response.json())
        except (httpx.HTTPError, ValueError, TikTokOfficialError) as exc:
            raise TikTokOfficialError("tiktok_authorized_shops_failed", "TikTok 授权店铺读取失败") from exc
        shops = data.get("shops") or data.get("shop_list") or []
        return [dict(shop) for shop in shops if isinstance(shop, dict)]

    def get_seller_permissions(self, credential_ref: str) -> dict[str, Any]:
        access_token = self.get_access_token(credential_ref)
        timestamp = str(int(time.time()))
        query = {"app_key": self.settings.tiktok_app_key, "timestamp": timestamp}
        query["sign"] = sign_tiktok_request(
            path="/seller/202309/permissions",
            query=query,
            app_secret=self.settings.tiktok_app_secret,
        )
        try:
            with httpx.Client(timeout=self.settings.tiktok_http_timeout_seconds, transport=self.transport) as client:
                response = client.get(
                    f"{OFFICIAL_API_BASE_URL}/seller/202309/permissions",
                    params=query,
                    headers={"Accept": "application/json", "x-tts-access-token": access_token},
                )
                response.raise_for_status()
                return _official_data(response.json())
        except (httpx.HTTPError, ValueError, TikTokOfficialError) as exc:
            raise TikTokOfficialError("tiktok_seller_permissions_failed", "TikTok 店铺权限读取失败") from exc


def start_official_authorization(
    db: Session,
    user: User,
    request: TikTokOfficialAuthorizationStart,
    *,
    settings: Settings | None = None,
) -> TikTokAuthorizationStartResponse:
    settings = settings or get_settings()
    ensure_tenant_admin(user.tenant_id, user)
    TikTokOfficialClient(settings).validate_configuration()
    scopes = sorted({scope.strip() for scope in request.scopes if scope.strip()})
    unsupported = sorted(set(scopes) - OFFICIAL_READ_ONLY_SCOPES)
    if not scopes or unsupported:
        raise TikTokOfficialError(
            "tiktok_scope_not_read_only",
            f"TikTok 官方授权仅允许已审核只读 Scope: {', '.join(unsupported)}",
        )
    market = request.market.upper()
    if request.authorization_type == "seller":
        service_id = settings.tiktok_service_id.strip()
        if not service_id:
            raise TikTokOfficialError(
                "tiktok_service_id_missing",
                "TikTok Service ID 未配置；请从 Partner Center 的 App & Service 详情页复制独立 Service ID",
            )
        base = "https://services.us.tiktokshop.com/open/authorize" if market == "US" else "https://services.tiktokshop.com/open/authorize"
        parameters = {"service_id": service_id}
    elif request.authorization_type == "partner":
        service_id = settings.tiktok_service_id.strip()
        if not service_id:
            raise TikTokOfficialError(
                "tiktok_service_id_missing",
                "TikTok Service ID 未配置；请从 Partner Center 的 App & Service 详情页复制独立 Service ID",
            )
        base = "https://partner.us.tiktokshop.com/open/authorize" if market == "US" else "https://partner.tiktokshop.com/open/authorize"
        parameters = {"service_id": service_id}
    else:
        base = "https://shop.tiktok.com/alliance/creator/auth"
        parameters = {"app_key": settings.tiktok_app_key.strip()}
    state = secrets.token_urlsafe(32)
    expires_at = utc_now() + timedelta(seconds=OFFICIAL_STATE_TTL_SECONDS)
    db.add(
        TikTokOAuthState(
            state_hash=state_hash(state),
            tenant_id=user.tenant_id,
            user_id=user.id,
            authorization_type=request.authorization_type,
            subject_id="pending",
            scopes_json=scopes,
            code_challenge=secrets.token_urlsafe(64),
            flow="official",
            return_to=_safe_return_to(request.return_to),
            expires_at=expires_at,
        )
    )
    db.commit()
    parameters["state"] = state
    return TikTokAuthorizationStartResponse(
        state=state,
        authorize_url=f"{base}?{urlencode(parameters)}",
        expires_at=expires_at.isoformat() + "Z",
    )


def exchange_official_authorization(
    db: Session,
    user: User,
    *,
    state: str,
    code: str,
    client: TikTokOfficialClient | None = None,
) -> list[ExternalAuthorization]:
    ensure_tenant_admin(user.tenant_id, user)
    row = db.get(TikTokOAuthState, state_hash(state))
    if not row or row.flow != "official" or row.expires_at <= utc_now():
        raise HTTPException(status_code=400, detail="TikTok official OAuth state is invalid or expired")
    if row.user_id != user.id or row.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="TikTok official OAuth state does not belong to this user")
    if not code.strip():
        raise HTTPException(status_code=400, detail="TikTok official OAuth code is missing")
    db.delete(row)
    db.commit()
    client = client or TikTokOfficialClient()
    try:
        data = client.exchange_code(code)
        token_values = _token_values(data)
        credential_ref = f"secret://tiktok/{user.tenant_id}/{secrets.token_urlsafe(18)}"
        client.token_store.put(credential_ref, token_values)
        shops = client.get_authorized_shops(credential_ref) if row.authorization_type == "seller" else []
    except TikTokOfficialError as exc:
        raise HTTPException(status_code=502, detail=exc.code) from exc

    subject_id = str(data.get("open_id") or "").strip()
    if not subject_id:
        raise HTTPException(status_code=502, detail="tiktok_open_id_missing")
    scopes = [str(scope) for scope in data.get("granted_scopes", []) if str(scope).strip()]
    if not scopes:
        scopes = list(row.scopes_json or [])
    authorizations: list[ExternalAuthorization] = []
    if shops:
        for shop in shops:
            resource = _upsert_official_resource(db, user, shop, row.authorization_type, data)
            _ensure_default_shop_scopes(db, user.tenant_id, resource.id)
            authorizations.append(
                _upsert_authorization(
                    db,
                    user=user,
                    authorization_type=row.authorization_type,
                    subject_id=subject_id,
                    resource_id=resource.id,
                    scopes=scopes,
                    credential_ref=credential_ref,
                    token_values=token_values,
                    data=data,
                )
            )
    else:
        authorizations.append(
            _upsert_authorization(
                db,
                user=user,
                authorization_type=row.authorization_type,
                subject_id=subject_id,
                resource_id=None,
                scopes=scopes,
                credential_ref=credential_ref,
                token_values=token_values,
                data=data,
            )
        )
    db.commit()
    return authorizations


def _official_data(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TikTokOfficialError("tiktok_response_invalid", "TikTok 官方响应格式无效")
    code = payload.get("code")
    if code not in (None, 0, "0"):
        raise TikTokOfficialError("tiktok_api_rejected", "TikTok 官方 API 拒绝请求")
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise TikTokOfficialError("tiktok_response_invalid", "TikTok 官方数据格式无效")
    return dict(data)


def _token_values(data: Mapping[str, Any]) -> dict[str, Any]:
    access_token = str(data.get("access_token") or "").strip()
    refresh_token = str(data.get("refresh_token") or "").strip()
    if not access_token or not refresh_token:
        raise TikTokOfficialError("tiktok_token_missing", "TikTok 官方 Token 响应不完整")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "access_token_expires_at": int(data.get("access_token_expire_in") or 0),
        "refresh_token_expires_at": int(data.get("refresh_token_expire_in") or 0),
    }


def _upsert_official_resource(
    db: Session,
    user: User,
    shop: Mapping[str, Any],
    authorization_type: str,
    token_data: Mapping[str, Any],
) -> BusinessResource:
    shop_id = str(shop.get("shop_id") or shop.get("id") or shop.get("shop_cipher") or "").strip()
    if not shop_id:
        raise TikTokOfficialError("tiktok_shop_id_missing", "TikTok 授权店铺缺少 shop_id")
    safe_shop_id = _SAFE_ID_RE.sub("-", shop_id)[:100]
    resource_id = f"tiktok_shop_{safe_shop_id}"
    resource = db.get(BusinessResource, resource_id)
    metadata = {
        "platform": "tiktok",
        "market": str(shop.get("region") or token_data.get("seller_base_region") or ""),
        "shop_cipher": str(shop.get("shop_cipher") or shop.get("cipher") or ""),
        "authorization_flow": "official",
        "read_only": True,
    }
    if resource is None:
        resource = BusinessResource(
            id=resource_id,
            tenant_id=user.tenant_id,
            resource_type="store",
            code=shop_id,
            name=str(shop.get("shop_name") or shop.get("name") or shop_id)[:160],
            created_by_user_id=user.id,
            metadata_json=metadata,
        )
    elif resource.tenant_id != user.tenant_id or resource.resource_type != "store":
        raise TikTokOfficialError("tiktok_shop_resource_conflict", "TikTok 店铺资源归属冲突")
    else:
        resource.name = str(shop.get("shop_name") or shop.get("name") or resource.name)[:160]
        resource.metadata_json = {**(resource.metadata_json or {}), **metadata}
        resource.revision += 1
        resource.updated_at = utc_now()
    db.add(resource)
    db.flush()
    return resource


def _ensure_default_shop_scopes(db: Session, tenant_id: str, resource_id: str) -> None:
    for business_role in ("operations_supervisor", "tiktok_shop_operator"):
        existing = db.exec(
            select(BusinessResourceScope).where(
                BusinessResourceScope.tenant_id == tenant_id,
                BusinessResourceScope.resource_id == resource_id,
                BusinessResourceScope.business_role == business_role,
            )
        ).first()
        if existing is None:
            db.add(
                BusinessResourceScope(
                    tenant_id=tenant_id,
                    resource_id=resource_id,
                    business_role=business_role,
                    access_level="viewer",
                )
            )


def _upsert_authorization(
    db: Session,
    *,
    user: User,
    authorization_type: str,
    subject_id: str,
    resource_id: str | None,
    scopes: list[str],
    credential_ref: str,
    token_values: Mapping[str, Any],
    data: Mapping[str, Any],
) -> ExternalAuthorization:
    authorization = db.exec(
        select(ExternalAuthorization).where(
            ExternalAuthorization.tenant_id == user.tenant_id,
            ExternalAuthorization.provider == "tiktok",
            ExternalAuthorization.authorization_type == authorization_type,
            ExternalAuthorization.subject_id == subject_id,
            ExternalAuthorization.resource_id == resource_id,
        )
    ).first()
    metadata = {
        "authorization_flow": "official",
        "official_scopes": sorted(set(scopes)),
        "user_type": data.get("user_type"),
        "seller_name": str(data.get("seller_name") or "")[:160],
        "seller_base_region": str(data.get("seller_base_region") or "")[:20],
        "read_only": True,
    }
    expires_at = _timestamp_datetime(token_values.get("access_token_expires_at"))
    fingerprint = "sha256:" + hashlib.sha256(
        str(token_values["access_token"]).encode("utf-8")
    ).hexdigest()
    if authorization is None:
        authorization = ExternalAuthorization(
            tenant_id=user.tenant_id,
            provider="tiktok",
            authorization_type=authorization_type,
            subject_id=subject_id,
            resource_id=resource_id,
            scopes_json=sorted(set(scopes)),
            credential_ref=credential_ref,
            token_fingerprint=fingerprint,
            expires_at=expires_at,
            metadata_json=metadata,
        )
    else:
        authorization.scopes_json = sorted(set(scopes))
        authorization.credential_ref = credential_ref
        authorization.token_fingerprint = fingerprint
        authorization.expires_at = expires_at
        authorization.status = "active"
        authorization.revision += 1
        authorization.metadata_json = {**(authorization.metadata_json or {}), **metadata}
        authorization.updated_at = utc_now()
    db.add(authorization)
    db.flush()
    return authorization


def _timestamp_datetime(value: Any) -> datetime | None:
    try:
        timestamp = int(value or 0)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC).replace(tzinfo=None)
