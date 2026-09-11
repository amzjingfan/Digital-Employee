from __future__ import annotations

import json

import pytest

from app.config import Settings
from app.db.models import AgentServiceIdentity
from app.work_tasks.m2m import (
    ServiceIdentityError,
    _load_client_secret,
    authenticate_service_identity,
)


def _identity(**updates: str) -> AgentServiceIdentity:
    values = {
        "id": "identity-1",
        "tenant_id": "tenant-a",
        "agent_id": "agent-a",
        "business_role": "logistics_exception_specialist",
        "issuer": "https://casdoor.example.test",
        "token_endpoint": "https://casdoor.example.test/api/login/oauth/access_token",
        "jwks_uri": "https://casdoor.example.test/.well-known/jwks",
        "application_owner": "admin",
        "application_name": "app-agent-logistics",
        "client_id": "client-logistics",
        "client_id_fingerprint": "sha256:client",
        "credential_ref": "casdoor:admin/app-agent-logistics",
    }
    values.update(updates)
    return AgentServiceIdentity(**values)


def _settings(secret_file: str) -> Settings:
    return Settings(
        oidc_issuer="https://casdoor.example.test",
        oidc_token_endpoint="https://casdoor.example.test/api/login/oauth/access_token",
        oidc_jwks_uri="https://casdoor.example.test/.well-known/jwks",
        work_task_m2m_secret_file=secret_file,
    )


def test_provider_endpoint_is_pinned_before_secret_exchange(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_file = tmp_path / "m2m.json"
    secret_file.write_text(
        json.dumps(
            {
                "credentials": {
                    "casdoor:admin/app-agent-logistics": {
                        "client_id": "client-logistics",
                        "client_secret": "never-send-to-attacker",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    posted = False

    def fake_post(*args, **kwargs):
        nonlocal posted
        posted = True
        raise AssertionError("untrusted endpoint must not receive a request")

    monkeypatch.setattr("app.work_tasks.m2m.httpx.post", fake_post)
    with pytest.raises(ServiceIdentityError) as exc_info:
        authenticate_service_identity(
            _identity(token_endpoint="https://attacker.example.test/collect"),
            _settings(str(secret_file)),
        )
    assert exc_info.value.code == "service_identity_provider_mismatch"
    assert posted is False


def test_secret_reference_must_match_expected_client_id(tmp_path) -> None:
    secret_file = tmp_path / "m2m.json"
    secret_file.write_text(
        json.dumps(
            {
                "credentials": {
                    "casdoor:admin/app-agent-logistics": {
                        "client_id": "different-client",
                        "client_secret": "wrong-role-secret",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ServiceIdentityError) as exc_info:
        _load_client_secret(
            str(secret_file),
            "casdoor:admin/app-agent-logistics",
            "client-logistics",
        )
    assert exc_info.value.code == "service_credential_binding_mismatch"
