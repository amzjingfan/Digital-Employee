from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.config import Settings
from app.tiktok.release_evidence import (
    release_evidence_filename,
    verify_tiktok_release_evidence,
    verify_tiktok_runtime_security_config,
)

TARGET_COMMIT = "a" * 40
REQUEST_SHA256 = "b" * 64
KEY_ID = "uat-release-2026-q3"
TENANT_ID = "tenant_demo"


def _canonical_payload(bundle: dict[str, object]) -> bytes:
    payload = dict(bundle)
    payload.pop("signature", None)
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _control(status: str, now: datetime, suffix: str) -> dict[str, object]:
    return {
        "status": status,
        "authority": "ACME protected release controller",
        "record_id": f"ACME-UAT-{suffix}",
        "decided_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(),
    }


def _write_signed_bundle(
    tmp_path: Path,
    *,
    now: datetime,
    tenant_id: str = TENANT_ID,
    target_commit: str = TARGET_COMMIT,
    expires_at: datetime | None = None,
) -> tuple[Settings, Path, Ed25519PrivateKey]:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    private_key = Ed25519PrivateKey.generate()
    public_key_path = tmp_path / "release-evidence.pub.pem"
    public_key_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    bundle: dict[str, object] = {
        "schema_version": 1,
        "tenant_id": tenant_id,
        "target_commit": target_commit,
        "request_sha256": REQUEST_SHA256,
        "key_id": KEY_ID,
        "issued_at": now.isoformat(),
        "expires_at": (expires_at or now + timedelta(days=30)).isoformat(),
        "controls": {
            "identity_mfa": _control("passed", now, "MFA-1"),
            "transport_tls": _control("passed", now, "TLS-1"),
            "credential_rotation": _control("passed", now, "ROTATION-1"),
            "postgres_restore": _control("passed", now, "RESTORE-1"),
            "business_signoff": _control("approved", now, "BUSINESS-1"),
            "security_signoff": _control("approved", now, "SECURITY-1"),
            "product_signoff": _control("approved", now, "PRODUCT-1"),
        },
    }
    bundle["signature"] = base64.urlsafe_b64encode(
        private_key.sign(_canonical_payload(bundle))
    ).decode("ascii").rstrip("=")
    evidence_path = evidence_dir / release_evidence_filename(tenant_id)
    evidence_path.write_text(
        json.dumps(bundle, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return (
        Settings(
            _env_file=None,
            tiktok_release_evidence_dir=str(evidence_dir),
            tiktok_release_evidence_public_key_file=str(public_key_path),
            tiktok_release_evidence_key_id=KEY_ID,
            tiktok_release_target_commit=TARGET_COMMIT,
            tiktok_release_request_sha256=REQUEST_SHA256,
        ),
        evidence_path,
        private_key,
    )


def test_signed_release_evidence_passes_every_external_gate(tmp_path: Path) -> None:
    now = datetime(2026, 9, 9, 3, 0, tzinfo=UTC)
    settings, _evidence_path, _private_key = _write_signed_bundle(tmp_path, now=now)

    result = verify_tiktok_release_evidence(settings, TENANT_ID, now=now)

    assert result.ok is True
    assert result.error_code is None
    assert {gate.key for gate in result.gates} == {
        "identity_mfa",
        "transport_tls",
        "credential_rotation",
        "postgres_restore",
        "business_signoff",
        "security_signoff",
        "product_signoff",
    }
    assert all(gate.status == "passed" for gate in result.gates)


def test_release_evidence_tampering_fails_closed(tmp_path: Path) -> None:
    now = datetime(2026, 9, 9, 3, 0, tzinfo=UTC)
    settings, evidence_path, _private_key = _write_signed_bundle(tmp_path, now=now)
    bundle = json.loads(evidence_path.read_text(encoding="utf-8"))
    bundle["controls"]["security_signoff"]["record_id"] = "ACME-UAT-FORGED"
    evidence_path.write_text(json.dumps(bundle), encoding="utf-8")

    result = verify_tiktok_release_evidence(settings, TENANT_ID, now=now)

    assert result.ok is False
    assert result.error_code == "evidence_signature_invalid"
    assert all(gate.status == "blocked" for gate in result.gates)


def test_release_evidence_is_bound_to_the_configured_target(tmp_path: Path) -> None:
    now = datetime(2026, 9, 9, 3, 0, tzinfo=UTC)
    settings, _evidence_path, _private_key = _write_signed_bundle(
        tmp_path,
        now=now,
        target_commit="c" * 40,
    )

    result = verify_tiktok_release_evidence(settings, TENANT_ID, now=now)

    assert result.error_code == "evidence_target_mismatch"
    assert all(gate.status == "blocked" for gate in result.gates)


def test_expired_release_evidence_fails_closed(tmp_path: Path) -> None:
    issued_at = datetime(2026, 9, 1, 3, 0, tzinfo=UTC)
    settings, _evidence_path, _private_key = _write_signed_bundle(
        tmp_path,
        now=issued_at,
        expires_at=issued_at + timedelta(days=1),
    )

    result = verify_tiktok_release_evidence(
        settings,
        TENANT_ID,
        now=issued_at + timedelta(days=2),
    )

    assert result.error_code == "evidence_bundle_expired_or_not_yet_valid"


def test_signed_bundle_with_unknown_field_fails_closed(tmp_path: Path) -> None:
    now = datetime(2026, 9, 9, 3, 0, tzinfo=UTC)
    settings, evidence_path, private_key = _write_signed_bundle(tmp_path, now=now)
    bundle = json.loads(evidence_path.read_text(encoding="utf-8"))
    bundle["unreviewed_override"] = True
    bundle["signature"] = base64.urlsafe_b64encode(
        private_key.sign(_canonical_payload(bundle))
    ).decode("ascii").rstrip("=")
    evidence_path.write_text(json.dumps(bundle), encoding="utf-8")

    result = verify_tiktok_release_evidence(settings, TENANT_ID, now=now)

    assert result.error_code == "evidence_bundle_invalid"
    assert all(gate.status == "blocked" for gate in result.gates)


def test_missing_release_evidence_configuration_fails_closed() -> None:
    result = verify_tiktok_release_evidence(Settings(_env_file=None), TENANT_ID)

    assert result.error_code == "release_target_configuration_incomplete"
    assert all(gate.status == "blocked" for gate in result.gates)


def test_release_evidence_filename_does_not_embed_tenant_input() -> None:
    filename = release_evidence_filename("../../another-tenant")

    assert filename.endswith(".json")
    assert len(filename) == 69
    assert "/" not in filename
    assert "\\" not in filename


def test_runtime_security_config_requires_production_like_settings(tmp_path: Path) -> None:
    token_store = tmp_path / "tokens.json"
    token_store.write_text('{"credentials":{}}', encoding="utf-8")
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://runtime@db.acme.com/staffdeck",
        database_auto_create=False,
        database_seed_demo_data=False,
        database_rls_enabled=True,
        mock_api_enabled=False,
        app_secret="a-production-secret-with-32-characters",
        oidc_enabled=True,
        oidc_issuer="https://identity.acme.com",
        oidc_authorization_endpoint="https://identity.acme.com/login/oauth/authorize",
        oidc_token_endpoint="https://identity.acme.com/api/login/oauth/access_token",
        oidc_jwks_uri="https://identity.acme.com/.well-known/jwks.json",
        oidc_redirect_uri="https://staffdeck.acme.com/api/oidc/callback",
        oidc_client_id="staffdeck-uat",
        oidc_client_secret="secret",
        oidc_cookie_secure=True,
        oidc_tenant_mapping_json='{"acme-uat":"tenant_demo"}',
        oidc_group_role_mapping_json='{"staffdeck-uat-admins":"tenant_admin"}',
        oidc_require_mapped_group=True,
        casdoor_management_enabled=True,
        casdoor_management_endpoint="https://identity.acme.com",
        casdoor_management_client_id="staffdeck-management-uat",
        casdoor_management_client_secret="secret",
        tiktok_official_enabled=True,
        tiktok_connector_mode="live",
        tiktok_app_key="app-key",
        tiktok_app_secret="app-secret",
        tiktok_service_id="service-id",
        tiktok_redirect_uri="https://staffdeck.acme.com/api/enterprise/tiktok/callback",
        tiktok_token_store_file=str(token_store),
        tiktok_shadow_enabled=True,
        tiktok_shadow_tenant_ids=TENANT_ID,
    )

    result = verify_tiktok_runtime_security_config(settings, TENANT_ID)

    assert result.status == "passed"


def test_runtime_security_config_rejects_insecure_urls_and_default_settings() -> None:
    settings = Settings(
        _env_file=None,
        oidc_enabled=True,
        oidc_issuer="https://user:secret@identity.acme.com",
        oidc_authorization_endpoint="http://identity.acme.com/authorize",
    )

    result = verify_tiktok_runtime_security_config(settings, TENANT_ID)

    assert result.status == "blocked"
    assert "oidc_issuer_not_https" in result.detail
    assert "oidc_authorization_endpoint_not_https" in result.detail
