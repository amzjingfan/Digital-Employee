from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from typing import Literal

from sqlmodel import Session, select

from app.db.database import engine
from app.db.models import Tenant, User, utc_now
from app.security.auth import hash_password

PASSWORD_ENV = "JOUKIR_BOOTSTRAP_ADMIN_PASSWORD"
FORBIDDEN_PASSWORDS = {"admin", "demo", "password"}


def validate_password(password: str, username: str) -> None:
    normalized = password.casefold()
    if (
        len(password) < 16
        or normalized == username.casefold()
        or normalized in FORBIDDEN_PASSWORDS
    ):
        raise ValueError("bootstrap administrator password policy was not satisfied")


def initialize_local_admin(
    db: Session,
    *,
    tenant_id: str,
    username: str,
    display_name: str | None,
    password: str,
    rotate_existing: bool,
) -> Literal["created", "rotated"]:
    normalized_tenant_id = tenant_id.strip()
    normalized_username = username.strip()
    if not normalized_tenant_id or not normalized_username:
        raise ValueError("tenant and username are required")
    validate_password(password, normalized_username)

    tenant = db.get(Tenant, normalized_tenant_id)
    if not tenant or tenant.status != "active":
        raise ValueError("an active tenant is required")

    existing = db.exec(
        select(User).where(
            User.tenant_id == normalized_tenant_id,
            User.username == normalized_username,
        )
    ).first()
    normalized_display_name = (display_name or "").strip()
    if existing:
        if not rotate_existing:
            raise ValueError("existing account requires --rotate-existing")
        existing.password_hash = hash_password(password)
        existing.display_name = normalized_display_name or existing.display_name or normalized_username
        existing.role = "admin"
        existing.business_role = "platform_admin"
        existing.authorization_source = "local"
        existing.identity_groups_json = []
        existing.role_synced_at = None
        existing.source = "web"
        existing.status = "active"
        existing.session_version += 1
        existing.failed_login_attempts = 0
        existing.locked_until = None
        existing.updated_at = utc_now()
        db.add(existing)
        action: Literal["created", "rotated"] = "rotated"
    else:
        db.add(
            User(
                tenant_id=normalized_tenant_id,
                username=normalized_username,
                display_name=normalized_display_name or normalized_username,
                role="admin",
                business_role="platform_admin",
                authorization_source="local",
                source="web",
                password_hash=hash_password(password),
                status="active",
            )
        )
        action = "created"

    db.commit()
    return action


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or explicitly rotate a Joukir emergency local administrator"
    )
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name")
    parser.add_argument("--rotate-existing", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if any(value == "--password" or value.startswith("--password=") for value in arguments):
        print(
            "error: password command-line arguments are not supported; use " + PASSWORD_ENV,
            file=sys.stderr,
        )
        return 2

    args = _parser().parse_args(arguments)
    password = os.environ.get(PASSWORD_ENV, "")
    if not password:
        print(f"error: {PASSWORD_ENV} is required", file=sys.stderr)
        return 1

    try:
        with Session(engine) as db:
            try:
                action = initialize_local_admin(
                    db,
                    tenant_id=args.tenant_id,
                    username=args.username,
                    display_name=args.display_name,
                    password=password,
                    rotate_existing=args.rotate_existing,
                )
            except Exception:
                db.rollback()
                raise
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception:  # noqa: BLE001 - CLI errors must not expose database connection details.
        print("error: emergency administrator initialization failed", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "tenant_id": args.tenant_id.strip(),
                "username": args.username.strip(),
                "action": action,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
