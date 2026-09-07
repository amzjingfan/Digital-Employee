from __future__ import annotations

import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.api import oidc
from app.config import Settings
from app.db.models import OIDCLoginState


def _settings(**overrides) -> Settings:
    values = {
        "oidc_enabled": True,
        "oidc_issuer": "http://issuer.example",
        "oidc_authorization_endpoint": "http://issuer.example/authorize",
        "oidc_token_endpoint": "http://issuer.example/token",
        "oidc_jwks_uri": "http://issuer.example/jwks",
        "oidc_client_id": "staffdeck-client",
        "oidc_client_secret": "test-secret",
        "oidc_redirect_uri": "http://staffdeck.example/api/auth/oidc/callback",
        "oidc_tenant_mapping_json": '{"acme":"tenant_acme"}',
        "oidc_group_role_mapping_json": (
            '{"acme/staffdeck-designer":"designer",'
            '"acme/staffdeck-procurement":"procurement_specialist"}'
        ),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_oidc_login_persists_hashed_state_and_pkce(monkeypatch) -> None:
    settings = _settings()
    monkeypatch.setattr(oidc, "get_settings", lambda: settings)
    with _session() as db:
        response = oidc.oidc_login(db=db, return_to="/workspace/gallery")
        query = parse_qs(urlsplit(response.headers["location"]).query)
        assert query["code_challenge_method"] == ["S256"]
        assert query["nonce"][0]
        assert query["state"][0]
        assert query["code_challenge"][0]
        rows = db.exec(select(OIDCLoginState)).all()
        assert len(rows) == 1
        assert rows[0].state_hash == oidc._state_hash(query["state"][0])
        assert rows[0].state_hash != query["state"][0]
        assert rows[0].return_to == "/workspace/gallery"


def test_oidc_id_token_requires_matching_issuer_and_audience(monkeypatch) -> None:
    settings = _settings()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    claims = {
        "iss": settings.oidc_issuer,
        "sub": "subject-1",
        "aud": settings.oidc_client_id,
        "iat": now,
        "exp": now + 300,
        "nonce": "nonce-1",
    }
    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test"})
    fake_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=private_key.public_key())
    )
    monkeypatch.setattr(oidc, "_jwks_client", lambda _uri: fake_client)

    assert oidc._validate_id_token(settings, token)["sub"] == "subject-1"

    wrong_audience = _settings(oidc_client_id="other-client")
    with pytest.raises(HTTPException) as error:
        oidc._validate_id_token(wrong_audience, token)
    assert error.value.status_code == 401


def test_oidc_organization_mapping_is_server_controlled() -> None:
    settings = _settings()
    mapped = oidc._mapped_identity(
        settings,
        {
            "sub": "subject-1",
            "owner": "acme",
            "name": "operator",
            "displayName": "Operator",
            "isAdmin": True,
        },
    )
    assert mapped == ("tenant_acme", "operator", "Operator", "admin", "platform_admin", [])

    with pytest.raises(HTTPException) as error:
        oidc._mapped_identity(
            settings,
            {"sub": "subject-2", "owner": "unmapped", "name": "attacker"},
        )
    assert error.value.status_code == 403


def test_oidc_group_maps_to_business_role() -> None:
    settings = _settings(oidc_require_mapped_group=True)
    mapped = oidc._mapped_identity(
        settings,
        {
            "sub": "subject-designer",
            "owner": "acme",
            "name": "designer-one",
            "groups": ["acme/staffdeck-designer"],
        },
    )
    assert mapped == (
        "tenant_acme",
        "designer-one",
        "designer-one",
        "member",
        "designer",
        ["acme/staffdeck-designer"],
    )


def test_oidc_conflicting_business_groups_are_rejected() -> None:
    settings = _settings(oidc_require_mapped_group=True)
    with pytest.raises(HTTPException) as error:
        oidc._mapped_identity(
            settings,
            {
                "sub": "subject-conflict",
                "owner": "acme",
                "name": "conflict",
                "groups": [
                    "acme/staffdeck-designer",
                    "acme/staffdeck-procurement",
                ],
            },
        )
    assert error.value.status_code == 403
    assert "conflicting" in str(error.value.detail)


def test_oidc_unmapped_identity_is_rejected_in_strict_mode() -> None:
    settings = _settings(oidc_require_mapped_group=True)
    with pytest.raises(HTTPException) as error:
        oidc._mapped_identity(
            settings,
            {"sub": "subject-unmapped", "owner": "acme", "name": "unmapped"},
        )
    assert error.value.status_code == 403


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://evil.example/steal", "/workspace/gallery"),
        ("//evil.example/steal", "/workspace/gallery"),
        ("/workspace/gallery?tab=mine", "/workspace/gallery?tab=mine"),
    ],
)
def test_oidc_return_target_rejects_open_redirects(value: str, expected: str) -> None:
    assert oidc._safe_return_to(value) == expected
