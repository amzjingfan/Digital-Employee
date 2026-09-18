from __future__ import annotations

import argparse
import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote_plus, urlsplit

import psycopg

DEFAULT_PUBLIC_URL = "http://127.0.0.1:5173"


STAFFDECK_GROUPS = (
    ("operations-supervisor", "运营主管"),
    ("after-sales", "跨境售后专员"),
    ("listing-compliance", "Listing 合规专员"),
    ("logistics-exception", "物流异常专员"),
    ("advertising-inspection", "广告巡检专员"),
    ("designer", "美工设计"),
    ("procurement", "采购专员"),
)


def normalize_public_url(value: str) -> str:
    cleaned = value.strip()
    parsed = urlsplit(cleaned)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("public URL must not contain credentials, query, or fragment")
    if parsed.path not in {"", "/"} or not parsed.hostname:
        raise ValueError("public URL must be an origin without a path")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("public URL port is invalid") from exc
    is_loopback = parsed.hostname.lower() in {"127.0.0.1", "localhost"}
    scheme = parsed.scheme.lower()
    if scheme != "https" and not (scheme == "http" and is_loopback):
        raise ValueError("public URL must use HTTPS except on loopback")
    return cleaned.rstrip("/")


def application_redirect_uris(public_url: str) -> list[str]:
    normalized = normalize_public_url(public_url)
    if normalized == DEFAULT_PUBLIC_URL:
        return [
            f"{normalized}/api/auth/oidc/callback",
            "http://localhost:5173/api/auth/oidc/callback",
            f"{normalized}/login",
        ]
    return [
        f"{normalized}/api/auth/oidc/callback",
        f"{normalized}/login",
    ]


def read_env(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    values: dict[str, str] = {}
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"')
    return lines, values


def write_env(path: Path, lines: list[str], updates: dict[str, str]) -> None:
    pending = dict(updates)
    rendered: list[str] = []
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            rendered.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in pending:
            rendered.append(f"{key}={pending.pop(key)}")
        else:
            rendered.append(line)
    if pending:
        rendered.append("")
        rendered.append("# StaffDeck OIDC application")
        rendered.extend(f"{key}={value}" for key, value in pending.items())
    path.write_text("\n".join(rendered) + "\n", encoding="utf-8")


def configured_secret(value: str | None, placeholder: str, bytes_count: int) -> str:
    if not value or value == placeholder or value.startswith("CHANGE_ME_"):
        return secrets.token_hex(bytes_count)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision the StaffDeck Casdoor OIDC app")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--public-url", default=DEFAULT_PUBLIC_URL)
    args = parser.parse_args()
    public_url = normalize_public_url(args.public_url)

    lines, env = read_env(args.env_file)
    organization = env.get("STAFFDECK_CASDOOR_ORGANIZATION", "").strip()
    if not organization:
        raise RuntimeError("STAFFDECK_CASDOOR_ORGANIZATION is required")
    if organization == "built-in":
        raise RuntimeError(
            "StaffDeck users must use a tenant organization; built-in users are Casdoor global administrators"
        )
    group_prefix = env.get("STAFFDECK_CASDOOR_GROUP_PREFIX", "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,62}", group_prefix):
        raise RuntimeError(
            "STAFFDECK_CASDOOR_GROUP_PREFIX must be a unique lowercase ASCII slug"
        )
    department_group_name = f"{group_prefix}-department"
    client_id = configured_secret(
        env.get("STAFFDECK_OIDC_CLIENT_ID"), "CHANGE_ME_STAFFDECK_OIDC_CLIENT_ID", 12
    )
    client_secret = configured_secret(
        env.get("STAFFDECK_OIDC_CLIENT_SECRET"),
        "CHANGE_ME_STAFFDECK_OIDC_CLIENT_SECRET",
        32,
    )
    host = "127.0.0.1"
    port = int(env.get("POSTGRES_PORT", "55432"))
    db_password = env["CASDOOR_DB_PASSWORD"]
    dsn = (
        f"postgresql://casdoor:{quote_plus(db_password)}@{host}:{port}/casdoor"
        "?sslmode=disable"
    )

    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM organization WHERE name = %s",
                (organization,),
            )
            if cursor.fetchone() is None:
                raise RuntimeError(
                    f"Casdoor organization {organization!r} does not exist"
                )
            cursor.execute(
                "SELECT to_jsonb(application) FROM application WHERE owner = %s AND name = %s",
                ("admin", "app-built-in"),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("Casdoor built-in application is not initialized")
            application = row[0]
            application.update(
                {
                    "owner": "admin",
                    "name": "app-staffdeck",
                    "display_name": "StaffDeck",
                    "homepage_url": public_url,
                    "description": "StaffDeck enterprise OIDC application",
                    "organization": organization,
                    "enable_sign_up": False,
                    "enable_guest_signin": False,
                    "disable_signin": False,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uris": json.dumps(
                        application_redirect_uris(public_url),
                        separators=(",", ":"),
                    ),
                    "grant_types": json.dumps(["authorization_code"], separators=(",", ":")),
                    # Casdoor reserves the standard OIDC scopes. This column is
                    # for custom ScopeItem objects, not a list of scope names.
                    "scopes": "[]",
                    "expire_in_hours": 8,
                    "refresh_expire_in_hours": 0,
                }
            )
            payload = json.dumps(application, separators=(",", ":"))
            cursor.execute(
                """
                INSERT INTO application
                SELECT (jsonb_populate_record(NULL::application, %s::jsonb)).*
                ON CONFLICT (owner, name) DO UPDATE SET
                  display_name = EXCLUDED.display_name,
                  homepage_url = EXCLUDED.homepage_url,
                  description = EXCLUDED.description,
                  organization = EXCLUDED.organization,
                  enable_sign_up = EXCLUDED.enable_sign_up,
                  enable_guest_signin = EXCLUDED.enable_guest_signin,
                  disable_signin = EXCLUDED.disable_signin,
                  client_id = EXCLUDED.client_id,
                  client_secret = EXCLUDED.client_secret,
                  redirect_uris = EXCLUDED.redirect_uris,
                  grant_types = EXCLUDED.grant_types,
                  scopes = EXCLUDED.scopes,
                  expire_in_hours = EXCLUDED.expire_in_hours,
                  refresh_expire_in_hours = EXCLUDED.refresh_expire_in_hours
                """,
                (payload,),
            )
            now = datetime.now(UTC).isoformat(timespec="seconds")
            cursor.execute(
                """
                INSERT INTO "group" (
                  owner, name, created_time, updated_time, display_name, type,
                  parent_id, is_top_group, title, key, children, is_enabled, properties
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, '[]', TRUE, '{}')
                ON CONFLICT (owner, name) DO UPDATE SET
                  updated_time = EXCLUDED.updated_time,
                  display_name = EXCLUDED.display_name,
                  is_enabled = TRUE
                """,
                (
                    organization,
                    department_group_name,
                    now,
                    now,
                    "StaffDeck 跨境电商部门",
                    "Virtual",
                    "",
                    "StaffDeck 跨境电商部门",
                    department_group_name,
                ),
            )
            for group_suffix, display_name in STAFFDECK_GROUPS:
                group_name = f"{group_prefix}-{group_suffix}"
                cursor.execute(
                    """
                    INSERT INTO "group" (
                      owner, name, created_time, updated_time, display_name, type,
                      parent_id, is_top_group, title, key, children, is_enabled, properties
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s, '[]', TRUE, '{}')
                    ON CONFLICT (owner, name) DO UPDATE SET
                      updated_time = EXCLUDED.updated_time,
                      display_name = EXCLUDED.display_name,
                      parent_id = EXCLUDED.parent_id,
                      is_enabled = TRUE
                    """,
                    (
                        organization,
                        group_name,
                        now,
                        now,
                        display_name,
                        "Virtual",
                        f"{organization}/{department_group_name}",
                        display_name,
                        group_name,
                    ),
                )
        connection.commit()

    write_env(
        args.env_file,
        lines,
        {
            "STAFFDECK_OIDC_CLIENT_ID": client_id,
            "STAFFDECK_OIDC_CLIENT_SECRET": client_secret,
        },
    )
    print(
        f"Casdoor application admin/app-staffdeck and seven StaffDeck business groups "
        f"are configured for organization {organization!r}; credentials were not printed."
    )


if __name__ == "__main__":
    main()
