from __future__ import annotations

from urllib.parse import urlsplit

from app.config import Settings

_DEFAULT_APP_SECRET = "change-me-in-development"
_REQUIRED_OIDC_VALUES = {
    "OIDC_ISSUER": "oidc_issuer",
    "OIDC_AUTHORIZATION_ENDPOINT": "oidc_authorization_endpoint",
    "OIDC_TOKEN_ENDPOINT": "oidc_token_endpoint",
    "OIDC_JWKS_URI": "oidc_jwks_uri",
    "OIDC_END_SESSION_ENDPOINT": "oidc_end_session_endpoint",
    "OIDC_CLIENT_ID": "oidc_client_id",
    "OIDC_CLIENT_SECRET": "oidc_client_secret",
    "OIDC_REDIRECT_URI": "oidc_redirect_uri",
    "OIDC_POST_LOGOUT_REDIRECT_URI": "oidc_post_logout_redirect_uri",
}
_REQUIRED_HTTPS_URLS = {
    key: attribute
    for key, attribute in _REQUIRED_OIDC_VALUES.items()
    if attribute
    not in {
        "oidc_client_id",
        "oidc_client_secret",
    }
}


def validate_runtime_config(settings: Settings) -> None:
    """Reject unsafe production authentication configuration without exposing values."""
    if settings.deployment_environment != "production":
        return

    invalid: set[str] = set()
    if not settings.oidc_enabled:
        invalid.add("OIDC_ENABLED")

    for key, attribute in _REQUIRED_OIDC_VALUES.items():
        if not str(getattr(settings, attribute)).strip():
            invalid.add(key)

    for key, attribute in _REQUIRED_HTTPS_URLS.items():
        value = str(getattr(settings, attribute)).strip()
        parsed = urlsplit(value)
        if value and (parsed.scheme.lower() != "https" or not parsed.hostname):
            invalid.add(key)

    if not settings.oidc_cookie_secure:
        invalid.add("OIDC_COOKIE_SECURE")
    if settings.app_secret == _DEFAULT_APP_SECRET or len(settings.app_secret) < 32:
        invalid.add("APP_SECRET")
    if settings.database_seed_demo_data:
        invalid.add("DATABASE_SEED_DEMO_DATA")

    if invalid:
        raise RuntimeError(
            "Unsafe production authentication configuration: "
            + ", ".join(sorted(invalid))
        )
