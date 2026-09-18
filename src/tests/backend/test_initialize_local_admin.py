from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import Tenant, User
from app.security.auth import hash_password, verify_password

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "scripts"
    / "initialize_local_admin.py"
)


def _load_script() -> ModuleType:
    module_name = "initialize_local_admin_under_test"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


admin_script = _load_script()


def _engine(*, tenant_status: str = "active"):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Tenant(id="tenant_demo", name="Demo", status=tenant_status))
        db.commit()
    return engine


def test_initialize_local_admin_creates_required_admin_account() -> None:
    engine = _engine()
    password = "Strong-Emergency-Password-2026"

    with Session(engine) as db:
        action = admin_script.initialize_local_admin(
            db,
            tenant_id="tenant_demo",
            username="emergency-admin",
            display_name="Emergency Administrator",
            password=password,
            rotate_existing=False,
        )
        user = db.exec(select(User).where(User.username == "emergency-admin")).one()

    assert action == "created"
    assert user.display_name == "Emergency Administrator"
    assert user.role == "admin"
    assert user.business_role == "platform_admin"
    assert user.authorization_source == "local"
    assert user.source == "web"
    assert user.status == "active"
    assert verify_password(password, user.password_hash)


@pytest.mark.parametrize("tenant_status", ["missing", "suspended"])
def test_initialize_local_admin_requires_active_existing_tenant(
    tenant_status: str,
) -> None:
    engine = _engine(tenant_status="active" if tenant_status == "missing" else tenant_status)
    tenant_id = "missing_tenant" if tenant_status == "missing" else "tenant_demo"

    with Session(engine) as db, pytest.raises(ValueError, match="active tenant"):
        admin_script.initialize_local_admin(
            db,
            tenant_id=tenant_id,
            username="emergency-admin",
            display_name=None,
            password="Strong-Emergency-Password-2026",
            rotate_existing=False,
        )
    with Session(engine) as db:
        assert db.exec(select(User)).all() == []


@pytest.mark.parametrize(
    "username,password",
    [
        ("emergency-admin", "too-short"),
        ("emergency-operator", "EMERGENCY-OPERATOR"),
        ("emergency-admin", "admin"),
        ("emergency-admin", "demo"),
        ("emergency-admin", "password"),
    ],
)
def test_initialize_local_admin_rejects_weak_passwords(
    username: str,
    password: str,
) -> None:
    engine = _engine()

    with Session(engine) as db, pytest.raises(ValueError, match="password policy"):
        admin_script.initialize_local_admin(
            db,
            tenant_id="tenant_demo",
            username=username,
            display_name=None,
            password=password,
            rotate_existing=False,
        )


def test_initialize_local_admin_refuses_implicit_overwrite() -> None:
    engine = _engine()
    original_hash = hash_password("Original-Emergency-Password")
    with Session(engine) as db:
        db.add(
            User(
                tenant_id="tenant_demo",
                username="emergency-admin",
                password_hash=original_hash,
            )
        )
        db.commit()

    with Session(engine) as db, pytest.raises(ValueError, match="rotate-existing"):
        admin_script.initialize_local_admin(
            db,
            tenant_id="tenant_demo",
            username="emergency-admin",
            display_name=None,
            password="Replacement-Emergency-Password",
            rotate_existing=False,
        )
    with Session(engine) as db:
        user = db.exec(select(User).where(User.username == "emergency-admin")).one()
        assert user.password_hash == original_hash
        assert user.session_version == 1


def test_initialize_local_admin_rotates_explicitly_and_revokes_sessions() -> None:
    engine = _engine()
    original_hash = hash_password("Original-Emergency-Password")
    with Session(engine) as db:
        db.add(
            User(
                tenant_id="tenant_demo",
                username="emergency-admin",
                password_hash=original_hash,
                role="member",
                business_role="member",
                authorization_source="oidc_groups",
                source="channel",
                status="suspended",
                session_version=3,
            )
        )
        db.commit()

    replacement = "Replacement-Emergency-Password"
    with Session(engine) as db:
        action = admin_script.initialize_local_admin(
            db,
            tenant_id="tenant_demo",
            username="emergency-admin",
            display_name="Emergency Administrator",
            password=replacement,
            rotate_existing=True,
        )
        user = db.exec(select(User).where(User.username == "emergency-admin")).one()

    assert action == "rotated"
    assert user.password_hash != original_hash
    assert verify_password(replacement, user.password_hash)
    assert user.session_version == 4
    assert (user.role, user.business_role) == ("admin", "platform_admin")
    assert (user.authorization_source, user.source, user.status) == (
        "local",
        "web",
        "active",
    )


def test_main_never_prints_password_hash_or_database_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    engine = _engine()
    password = "Strong-Emergency-Password-2026"
    monkeypatch.setattr(admin_script, "engine", engine)
    monkeypatch.setenv(admin_script.PASSWORD_ENV, password)

    result = admin_script.main(
        ["--tenant-id", "tenant_demo", "--username", "emergency-admin"]
    )

    captured = capsys.readouterr()
    with Session(engine) as db:
        user = db.exec(select(User).where(User.username == "emergency-admin")).one()
    output = captured.out + captured.err
    assert result == 0
    assert password not in output
    assert user.password_hash not in output
    assert "sqlite://" not in output


def test_main_rejects_password_argument_without_echoing_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    password = "Command-Line-Secret-Value"

    result = admin_script.main(
        [
            "--tenant-id",
            "tenant_demo",
            "--username",
            "emergency-admin",
            "--password",
            password,
        ]
    )

    captured = capsys.readouterr()
    assert result != 0
    assert password not in captured.out + captured.err
