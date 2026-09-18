from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.config import Settings
from app.security.runtime_config import validate_runtime_config


def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "deployment_environment": "production",
        "database_seed_demo_data": False,
        "app_secret": "a-production-secret-with-at-least-32-characters",
        "oidc_enabled": True,
        "oidc_issuer": "https://identity.example.com",
        "oidc_authorization_endpoint": (
            "https://identity.example.com/login/oauth/authorize"
        ),
        "oidc_token_endpoint": (
            "https://identity.example.com/api/login/oauth/access_token"
        ),
        "oidc_jwks_uri": "https://identity.example.com/.well-known/jwks",
        "oidc_end_session_endpoint": "https://identity.example.com/api/logout",
        "oidc_client_id": "joukir-client",
        "oidc_client_secret": "client-secret-must-not-leak",
        "oidc_redirect_uri": "https://joukir.example.com/api/auth/oidc/callback",
        "oidc_post_logout_redirect_uri": "https://joukir.example.com/login",
        "oidc_cookie_secure": True,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_development_profile_preserves_current_loopback_defaults() -> None:
    validate_runtime_config(Settings(_env_file=None))


def test_complete_production_profile_is_accepted() -> None:
    validate_runtime_config(_production_settings())


@pytest.mark.parametrize(
    ("overrides", "invalid_key"),
    [
        ({"oidc_enabled": False}, "OIDC_ENABLED"),
        ({"oidc_cookie_secure": False}, "OIDC_COOKIE_SECURE"),
        ({"app_secret": "change-me-in-development"}, "APP_SECRET"),
        ({"app_secret": "too-short"}, "APP_SECRET"),
        ({"database_seed_demo_data": True}, "DATABASE_SEED_DEMO_DATA"),
    ],
)
def test_production_profile_rejects_unsafe_flags_and_secrets(
    overrides: dict[str, object],
    invalid_key: str,
) -> None:
    with pytest.raises(RuntimeError, match=invalid_key):
        validate_runtime_config(_production_settings(**overrides))


@pytest.mark.parametrize(
    ("attribute", "setting_key"),
    [
        ("oidc_issuer", "OIDC_ISSUER"),
        ("oidc_authorization_endpoint", "OIDC_AUTHORIZATION_ENDPOINT"),
        ("oidc_token_endpoint", "OIDC_TOKEN_ENDPOINT"),
        ("oidc_jwks_uri", "OIDC_JWKS_URI"),
        ("oidc_end_session_endpoint", "OIDC_END_SESSION_ENDPOINT"),
        ("oidc_redirect_uri", "OIDC_REDIRECT_URI"),
        ("oidc_post_logout_redirect_uri", "OIDC_POST_LOGOUT_REDIRECT_URI"),
    ],
)
def test_production_profile_requires_https_oidc_urls(
    attribute: str,
    setting_key: str,
) -> None:
    with pytest.raises(RuntimeError, match=setting_key):
        validate_runtime_config(_production_settings(**{attribute: "http://example.com"}))


@pytest.mark.parametrize(
    ("attribute", "setting_key"),
    [
        ("oidc_issuer", "OIDC_ISSUER"),
        ("oidc_authorization_endpoint", "OIDC_AUTHORIZATION_ENDPOINT"),
        ("oidc_token_endpoint", "OIDC_TOKEN_ENDPOINT"),
        ("oidc_jwks_uri", "OIDC_JWKS_URI"),
        ("oidc_end_session_endpoint", "OIDC_END_SESSION_ENDPOINT"),
        ("oidc_client_id", "OIDC_CLIENT_ID"),
        ("oidc_client_secret", "OIDC_CLIENT_SECRET"),
        ("oidc_redirect_uri", "OIDC_REDIRECT_URI"),
        ("oidc_post_logout_redirect_uri", "OIDC_POST_LOGOUT_REDIRECT_URI"),
    ],
)
def test_production_profile_requires_all_oidc_values(
    attribute: str,
    setting_key: str,
) -> None:
    with pytest.raises(RuntimeError, match=setting_key):
        validate_runtime_config(_production_settings(**{attribute: "  "}))


def test_production_error_never_contains_secret_values() -> None:
    settings = _production_settings(
        oidc_issuer="http://identity.example.com",
        app_secret="short-secret-value",
    )

    with pytest.raises(RuntimeError) as error:
        validate_runtime_config(settings)

    message = str(error.value)
    assert "client-secret-must-not-leak" not in message
    assert "short-secret-value" not in message


@pytest.fixture
def imported_main() -> Iterator[object]:
    from app import main

    yield main


def test_startup_rejects_unsafe_config_before_database_initialization(
    monkeypatch: pytest.MonkeyPatch,
    imported_main: object,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(imported_main, "settings", _production_settings(oidc_enabled=False))
    monkeypatch.setattr(imported_main, "acquire_runtime_instance_lock", lambda: None)
    monkeypatch.setattr(
        imported_main,
        "release_runtime_instance_lock",
        lambda: calls.append("release"),
    )
    monkeypatch.setattr(imported_main, "init_db", lambda: calls.append("init_db"))

    with pytest.raises(RuntimeError, match="OIDC_ENABLED"):
        imported_main.on_startup()

    assert calls == ["release"]
