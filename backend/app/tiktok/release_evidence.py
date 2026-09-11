"""Verify target-bound UAT release evidence without trusting local assertions."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.config import Settings

_MAX_EVIDENCE_BYTES = 64 * 1024
_MAX_PUBLIC_KEY_BYTES = 16 * 1024
_MAX_BUNDLE_LIFETIME = timedelta(days=90)
_CLOCK_SKEW = timedelta(minutes=5)
_GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_CONTROL_DEFINITIONS: tuple[tuple[str, str, str], ...] = (
    ("identity_mfa", "Casdoor MFA 实测", "passed"),
    ("transport_tls", "TLS/证书实测", "passed"),
    ("credential_rotation", "凭据与密钥轮换", "passed"),
    ("postgres_restore", "PostgreSQL 备份恢复演练", "passed"),
    ("business_signoff", "业务签字", "approved"),
    ("security_signoff", "安全签字", "approved"),
    ("product_signoff", "产品签字", "approved"),
)
_CONTROL_STATUSES = {key: status for key, _label, status in _CONTROL_DEFINITIONS}


class _ControlEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["passed", "approved", "rejected", "revoked"]
    authority: str = Field(min_length=1, max_length=256)
    record_id: str = Field(min_length=1, max_length=512)
    decided_at: AwareDatetime
    expires_at: AwareDatetime | None = None

    @field_validator("authority", "record_id")
    @classmethod
    def reject_blank_identifiers(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence identifiers must not be blank")
        return value


class _ReleaseEvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    tenant_id: str = Field(min_length=1, max_length=256)
    target_commit: str
    request_sha256: str
    key_id: str = Field(min_length=1, max_length=256)
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    controls: dict[str, _ControlEvidence]
    signature: str = Field(min_length=1, max_length=512)

    @field_validator("tenant_id", "key_id")
    @classmethod
    def reject_blank_identifiers(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence identifiers must not be blank")
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> _ReleaseEvidenceBundle:
        if not _GIT_OBJECT_RE.fullmatch(self.target_commit):
            raise ValueError("target_commit must be a Git object ID")
        if not _SHA256_RE.fullmatch(self.request_sha256):
            raise ValueError("request_sha256 must be a SHA-256 digest")
        if set(self.controls) != set(_CONTROL_STATUSES):
            raise ValueError("controls must exactly match the release evidence contract")
        if self.expires_at <= self.issued_at:
            raise ValueError("evidence bundle must expire after it is issued")
        if self.expires_at - self.issued_at > _MAX_BUNDLE_LIFETIME:
            raise ValueError("evidence bundle lifetime exceeds 90 days")
        return self


@dataclass(frozen=True, slots=True)
class TikTokReleaseEvidenceGate:
    key: str
    label: str
    status: Literal["passed", "blocked"]
    detail: str


@dataclass(frozen=True, slots=True)
class TikTokReleaseEvidenceResult:
    ok: bool
    error_code: str | None
    gates: tuple[TikTokReleaseEvidenceGate, ...]


def _secure_https_url(value: str) -> bool:
    parsed = urlsplit(value.strip())
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
    )


def _nonempty_json_object(value: str) -> bool:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return False
    return isinstance(parsed, dict) and bool(parsed)


def verify_tiktok_runtime_security_config(
    settings: Settings,
    tenant_id: str,
) -> TikTokReleaseEvidenceGate:
    """Check production-like runtime settings without revealing configured secrets."""

    issues: list[str] = []
    if settings.database_url.split(":", 1)[0] not in {"postgresql", "postgresql+psycopg"}:
        issues.append("database_not_postgresql")
    if settings.database_auto_create:
        issues.append("database_auto_create_enabled")
    if settings.database_seed_demo_data:
        issues.append("database_demo_seed_enabled")
    if not settings.database_rls_enabled:
        issues.append("database_rls_disabled")
    if settings.mock_api_enabled:
        issues.append("mock_api_enabled")
    if not settings.casbin_enabled:
        issues.append("casbin_disabled")
    if settings.app_secret == "change-me-in-development" or len(settings.app_secret) < 32:
        issues.append("app_secret_weak_or_default")

    if not settings.oidc_enabled:
        issues.append("oidc_disabled")
    for field_name in (
        "oidc_issuer",
        "oidc_authorization_endpoint",
        "oidc_token_endpoint",
        "oidc_jwks_uri",
        "oidc_redirect_uri",
    ):
        if not _secure_https_url(str(getattr(settings, field_name))):
            issues.append(f"{field_name}_not_https")
    if not settings.oidc_client_id.strip() or not settings.oidc_client_secret:
        issues.append("oidc_client_credentials_incomplete")
    if not settings.oidc_cookie_secure:
        issues.append("oidc_cookie_not_secure")
    if not _nonempty_json_object(settings.oidc_tenant_mapping_json):
        issues.append("oidc_tenant_mapping_missing")
    if not _nonempty_json_object(settings.oidc_group_role_mapping_json):
        issues.append("oidc_group_role_mapping_missing")
    if not settings.oidc_require_mapped_group:
        issues.append("oidc_mapped_group_not_required")

    if not settings.casdoor_management_enabled:
        issues.append("casdoor_management_disabled")
    if not _secure_https_url(settings.casdoor_management_endpoint):
        issues.append("casdoor_management_endpoint_not_https")
    if (
        not settings.casdoor_management_client_id.strip()
        or not settings.casdoor_management_client_secret
    ):
        issues.append("casdoor_management_credentials_incomplete")
    elif settings.casdoor_management_client_id == settings.oidc_client_id:
        issues.append("casdoor_management_client_not_separate")

    if not settings.tiktok_official_enabled:
        issues.append("tiktok_official_disabled")
    if settings.tiktok_connector_mode != "live":
        issues.append("tiktok_connector_not_live")
    if not settings.tiktok_app_key.strip() or not settings.tiktok_app_secret:
        issues.append("tiktok_app_credentials_incomplete")
    if not settings.tiktok_service_id.strip():
        issues.append("tiktok_service_id_missing")
    if not _secure_https_url(settings.tiktok_redirect_uri):
        issues.append("tiktok_redirect_uri_not_https")
    token_store = Path(settings.tiktok_token_store_file).expanduser()
    if (
        not settings.tiktok_token_store_file.strip()
        or not token_store.is_absolute()
        or token_store.is_symlink()
        or not token_store.is_file()
    ):
        issues.append("tiktok_token_store_not_protected_file")
    if not settings.tiktok_shadow_enabled:
        issues.append("tiktok_shadow_disabled")
    if tenant_id not in settings.tiktok_shadow_tenant_id_list:
        issues.append("tenant_not_enabled_for_shadow")

    return TikTokReleaseEvidenceGate(
        key="runtime_security_config",
        label="真实环境与 TLS 配置",
        status="blocked" if issues else "passed",
        detail=(
            "生产型数据库、OIDC/Casdoor、TLS、安全 Cookie、TikTok Live 与影子租户配置已通过"
            if not issues
            else "配置失败关闭：" + ", ".join(issues)
        ),
    )


def _blocked_result(error_code: str) -> TikTokReleaseEvidenceResult:
    return TikTokReleaseEvidenceResult(
        ok=False,
        error_code=error_code,
        gates=tuple(
            TikTokReleaseEvidenceGate(
                key=key,
                label=label,
                status="blocked",
                detail=f"外部证据未验证：{error_code}",
            )
            for key, label, _expected_status in _CONTROL_DEFINITIONS
        ),
    )


def _read_bounded_regular_file(path: Path, *, limit: int, error_code: str) -> bytes:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError(error_code)
    if path.stat().st_size > limit:
        raise ValueError(error_code)
    return path.read_bytes()


def _decode_signature(value: str) -> bytes:
    try:
        padded = value + "=" * (-len(value) % 4)
        signature = base64.b64decode(padded, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("evidence_signature_invalid") from exc
    if len(signature) != 64:
        raise ValueError("evidence_signature_invalid")
    return signature


def _canonical_payload(raw_bundle: dict[str, object]) -> bytes:
    payload = dict(raw_bundle)
    payload.pop("signature", None)
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def verify_tiktok_release_evidence(
    settings: Settings,
    tenant_id: str,
    *,
    now: datetime | None = None,
) -> TikTokReleaseEvidenceResult:
    """Verify an externally signed, immutable release evidence bundle."""

    expected_commit = settings.tiktok_release_target_commit.strip()
    expected_request = settings.tiktok_release_request_sha256.strip()
    expected_key_id = settings.tiktok_release_evidence_key_id.strip()
    if (
        not _GIT_OBJECT_RE.fullmatch(expected_commit)
        or not _SHA256_RE.fullmatch(expected_request)
        or not expected_key_id
    ):
        return _blocked_result("release_target_configuration_incomplete")

    evidence_root = Path(settings.tiktok_release_evidence_dir).expanduser()
    public_key_path = Path(settings.tiktok_release_evidence_public_key_file).expanduser()
    if (
        not settings.tiktok_release_evidence_dir.strip()
        or not evidence_root.is_absolute()
        or evidence_root.is_symlink()
        or not evidence_root.is_dir()
    ):
        return _blocked_result("evidence_directory_unavailable")

    evidence_path = evidence_root / f"{hashlib.sha256(tenant_id.encode('utf-8')).hexdigest()}.json"
    try:
        evidence_bytes = _read_bounded_regular_file(
            evidence_path,
            limit=_MAX_EVIDENCE_BYTES,
            error_code="evidence_file_unavailable",
        )
        key_bytes = _read_bounded_regular_file(
            public_key_path,
            limit=_MAX_PUBLIC_KEY_BYTES,
            error_code="evidence_public_key_unavailable",
        )
        raw_bundle = json.loads(evidence_bytes.decode("utf-8"))
        if not isinstance(raw_bundle, dict) or not isinstance(raw_bundle.get("signature"), str):
            raise TypeError("evidence_bundle_invalid")
        public_key = serialization.load_pem_public_key(key_bytes)
        if not isinstance(public_key, Ed25519PublicKey):
            raise TypeError("evidence_public_key_type_invalid")
        public_key.verify(
            _decode_signature(str(raw_bundle["signature"])),
            _canonical_payload(raw_bundle),
        )
        bundle = _ReleaseEvidenceBundle.model_validate(raw_bundle)
    except FileNotFoundError:
        return _blocked_result("evidence_file_unavailable")
    except InvalidSignature:
        return _blocked_result("evidence_signature_invalid")
    except (
        OSError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
    ) as exc:
        error_code = str(exc) if str(exc).startswith("evidence_") else "evidence_bundle_invalid"
        return _blocked_result(error_code)

    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        return _blocked_result("verification_clock_not_timezone_aware")
    if bundle.tenant_id != tenant_id:
        return _blocked_result("evidence_tenant_mismatch")
    if bundle.target_commit != expected_commit:
        return _blocked_result("evidence_target_mismatch")
    if bundle.request_sha256 != expected_request:
        return _blocked_result("evidence_request_mismatch")
    if bundle.key_id != expected_key_id:
        return _blocked_result("evidence_key_id_mismatch")
    if bundle.issued_at > current + _CLOCK_SKEW or bundle.expires_at <= current:
        return _blocked_result("evidence_bundle_expired_or_not_yet_valid")

    gates: list[TikTokReleaseEvidenceGate] = []
    for key, label, expected_status in _CONTROL_DEFINITIONS:
        control = bundle.controls[key]
        expired = control.expires_at is not None and control.expires_at <= current
        not_yet_decided = control.decided_at > current + _CLOCK_SKEW
        passed = control.status == expected_status and not expired and not not_yet_decided
        gates.append(
            TikTokReleaseEvidenceGate(
                key=key,
                label=label,
                status="passed" if passed else "blocked",
                detail=(
                    f"已由 {control.authority} 验证，记录 {control.record_id}"
                    if passed
                    else "外部证据状态、时间或有效期不满足发布要求"
                ),
            )
        )
    return TikTokReleaseEvidenceResult(
        ok=all(gate.status == "passed" for gate in gates),
        error_code=None,
        gates=tuple(gates),
    )


def release_evidence_filename(tenant_id: str) -> str:
    """Return the traversal-safe filename expected for one tenant's evidence bundle."""

    return f"{hashlib.sha256(tenant_id.encode('utf-8')).hexdigest()}.json"
