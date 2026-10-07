from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SRC_DIR = Path(__file__).resolve().parents[2]
PROVISION_SCRIPT = (
    SRC_DIR / "deploy" / "staffdeck-platform" / "scripts" / "provision-agent-m2m.py"
)


def _load_provision_script() -> ModuleType:
    module_name = "provision_agent_m2m_under_test"
    spec = importlib.util.spec_from_file_location(module_name, PROVISION_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


provision = _load_provision_script()


def test_read_env_accepts_single_and_double_quoted_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_PORT='55433'\n"
        'ORGANIZATION="example-org"\n'
        "UNQUOTED=value\n",
        encoding="utf-8",
    )

    assert provision.read_env(env_file) == {
        "POSTGRES_PORT": "55433",
        "ORGANIZATION": "example-org",
        "UNQUOTED": "value",
    }


def test_merge_secret_credentials_preserves_unmanaged_entries() -> None:
    existing = {
        "casdoor:admin/app-joukir-tiktok-role": {
            "client_id": "existing-client",
            "client_secret": "existing-secret",
        }
    }
    managed = {
        "casdoor:admin/app-staffdeck-agent-designer": {
            "client_id": "designer-client",
            "client_secret": "designer-secret",
        }
    }

    assert provision.merge_secret_credentials(existing, managed) == {
        **existing,
        **managed,
    }
