from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SRC_DIR = Path(__file__).resolve().parents[2]
CONFIGURE_SCRIPT = (
    SRC_DIR / "deploy" / "staffdeck-platform" / "scripts" / "configure-casdoor-oidc.py"
)
MIGRATION_SCRIPT = (
    SRC_DIR / "deploy" / "staffdeck-platform" / "scripts" / "migrate-staffdeck.ps1"
)


def _load_configure_script() -> ModuleType:
    module_name = "configure_casdoor_oidc_under_test"
    spec = importlib.util.spec_from_file_location(module_name, CONFIGURE_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


configure = _load_configure_script()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://127.0.0.1:5173/", "http://127.0.0.1:5173"),
        ("http://localhost:5173", "http://localhost:5173"),
        ("https://joukir.example.com/", "https://joukir.example.com"),
    ],
)
def test_normalize_public_url_accepts_safe_origins(value: str, expected: str) -> None:
    assert configure.normalize_public_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "http://joukir.example.com",
        "https://user:password@joukir.example.com",
        "https://joukir.example.com/path",
        "https://joukir.example.com?tenant=demo",
        "https://joukir.example.com/#fragment",
        "https://joukir.example.com:invalid",
    ],
)
def test_normalize_public_url_rejects_unsafe_origins(value: str) -> None:
    with pytest.raises(ValueError):
        configure.normalize_public_url(value)


def test_default_public_url_preserves_both_loopback_callbacks() -> None:
    assert configure.application_redirect_uris("http://127.0.0.1:5173") == [
        "http://127.0.0.1:5173/api/auth/oidc/callback",
        "http://localhost:5173/api/auth/oidc/callback",
        "http://127.0.0.1:5173/login",
    ]


def test_public_url_registers_callback_and_post_logout_login() -> None:
    assert configure.application_redirect_uris("https://joukir.example.com/") == [
        "https://joukir.example.com/api/auth/oidc/callback",
        "https://joukir.example.com/login",
    ]


def test_migration_script_validates_and_writes_public_urls() -> None:
    script = MIGRATION_SCRIPT.read_text(encoding="utf-8")

    assert "[string]$PublicUrl = 'http://127.0.0.1:5173'" in script
    assert "[Uri]::TryCreate($PublicUrl" in script
    assert "$normalizedPublicUrl" in script
    assert "'OIDC_REDIRECT_URI' \"$normalizedPublicUrl/api/auth/oidc/callback\"" in script
    assert (
        "'OIDC_POST_LOGOUT_REDIRECT_URI' \"$normalizedPublicUrl/login\"" in script
    )
