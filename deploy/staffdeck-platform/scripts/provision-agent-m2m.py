from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote_plus

import psycopg


ROLE_APPS = (
    ("operations_supervisor", "operations-supervisor", "运营主管"),
    ("after_sales_specialist", "after-sales", "跨境售后专员"),
    ("listing_compliance_specialist", "listing-compliance", "Listing 合规专员"),
    ("logistics_exception_specialist", "logistics-exception", "物流异常专员"),
    ("advertising_inspection_specialist", "advertising-inspection", "广告巡检专员"),
    ("designer", "designer", "美工设计"),
    ("procurement_specialist", "procurement", "采购专员"),
)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def fingerprint(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def deterministic_id(tenant_id: str, role: str) -> str:
    digest = hashlib.sha256(f"{tenant_id}:{role}:casdoor-m2m".encode()).hexdigest()[:24]
    return f"agent_identity_{digest}"


def secure_atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name == "nt":
            domain = os.environ.get("USERDOMAIN", "").strip()
            username = os.environ.get("USERNAME", "").strip()
            principal = f"{domain}\\{username}" if domain and username else username
            if not principal:
                raise RuntimeError("Could not resolve current Windows principal for secret ACL")
            result = subprocess.run(
                [
                    "icacls",
                    str(path),
                    "/inheritance:r",
                    "/grant:r",
                    f"{principal}:(F)",
                    "/grant:r",
                    "SYSTEM:(F)",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError("Failed to restrict the M2M secret-store ACL")
        else:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision seven Casdoor M2M workload identities")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--secret-file", type=Path, required=True)
    parser.add_argument("--tenant-id", default="tenant_demo")
    args = parser.parse_args()

    env = read_env(args.env_file)
    organization = env.get("STAFFDECK_CASDOOR_ORGANIZATION", "").strip()
    if not organization or organization == "built-in":
        raise RuntimeError("A non-built-in Casdoor tenant organization is required")
    if not re.fullmatch(r"[A-Za-z0-9_.\-\u4e00-\u9fff]{1,100}", organization):
        raise RuntimeError("Casdoor organization contains unsupported characters")
    port = int(env.get("POSTGRES_PORT", "55432"))
    casdoor_dsn = (
        f"postgresql://casdoor:{quote_plus(env['CASDOOR_DB_PASSWORD'])}"
        f"@127.0.0.1:{port}/casdoor?sslmode=disable"
    )
    staffdeck_dsn = (
        f"postgresql://staffdeck_migrator:{quote_plus(env['STAFFDECK_MIGRATOR_PASSWORD'])}"
        f"@127.0.0.1:{port}/staffdeck_app?sslmode=disable"
    )
    staffdeck_read_dsn = (
        f"postgresql://staffdeck_worker:{quote_plus(env['STAFFDECK_WORKER_PASSWORD'])}"
        f"@127.0.0.1:{port}/staffdeck_app?sslmode=disable"
    )
    existing_store: dict[str, object] = {}
    if args.secret_file.exists():
        try:
            loaded = json.loads(args.secret_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing_store = loaded
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Existing M2M secret store is unreadable") from exc
    existing_credentials = existing_store.get("credentials")
    if not isinstance(existing_credentials, dict):
        existing_credentials = {}

    provisioned: list[dict[str, str]] = []
    new_credentials: dict[str, dict[str, str]] = {}
    with psycopg.connect(casdoor_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_jsonb(application) FROM application WHERE owner = %s AND name = %s",
                ("admin", "app-built-in"),
            )
            base_row = cursor.fetchone()
            if base_row is None:
                raise RuntimeError("Casdoor built-in application is not initialized")
            base = base_row[0]
            for role, slug, label in ROLE_APPS:
                app_name = f"app-staffdeck-agent-{slug}"
                credential_ref = f"casdoor:admin/{app_name}"
                cursor.execute(
                    "SELECT client_id, client_secret FROM application WHERE owner = %s AND name = %s",
                    ("admin", app_name),
                )
                current = cursor.fetchone()
                saved = existing_credentials.get(credential_ref)
                saved = saved if isinstance(saved, dict) else {}
                client_id = str(current[0] if current else saved.get("client_id") or secrets.token_hex(12))
                client_secret = str(
                    current[1] if current else saved.get("client_secret") or secrets.token_hex(32)
                )
                application = dict(base)
                application.update(
                    {
                        "owner": "admin",
                        "name": app_name,
                        "display_name": f"StaffDeck {label} M2M",
                        "homepage_url": "http://127.0.0.1:5173/enterprise/work-tasks",
                        "description": f"StaffDeck {label} workload identity; client credentials only",
                        "organization": organization,
                        "enable_sign_up": False,
                        "enable_guest_signin": False,
                        "disable_signin": False,
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "redirect_uris": "[]",
                        "grant_types": json.dumps(["client_credentials"], separators=(",", ":")),
                        "scopes": "[]",
                        "expire_in_hours": 0.25,
                        "refresh_expire_in_hours": 0,
                    }
                )
                cursor.execute(
                    """
                    INSERT INTO application
                    SELECT (jsonb_populate_record(NULL::application, %s::jsonb)).*
                    ON CONFLICT (owner, name) DO UPDATE SET
                      display_name = EXCLUDED.display_name,
                      homepage_url = EXCLUDED.homepage_url,
                      description = EXCLUDED.description,
                      organization = EXCLUDED.organization,
                      enable_sign_up = FALSE,
                      enable_guest_signin = FALSE,
                      disable_signin = EXCLUDED.disable_signin,
                      client_id = EXCLUDED.client_id,
                      client_secret = EXCLUDED.client_secret,
                      redirect_uris = '[]',
                      grant_types = EXCLUDED.grant_types,
                      scopes = '[]',
                      expire_in_hours = EXCLUDED.expire_in_hours,
                      refresh_expire_in_hours = 0
                    """,
                    (json.dumps(application, separators=(",", ":")),),
                )
                new_credentials[credential_ref] = {
                    "client_id": client_id,
                    "client_secret": client_secret,
                }
                provisioned.append(
                    {
                        "role": role,
                        "label": label,
                        "application_name": app_name,
                        "credential_ref": credential_ref,
                        "client_id": client_id,
                    }
                )
        connection.commit()

    secret_payload: dict[str, object] = {
        "version": 1,
        "provider": "casdoor",
        "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "credentials": new_credentials,
    }
    secure_atomic_json(args.secret_file.resolve(), secret_payload)

    agent_by_role: dict[str, str] = {}
    with psycopg.connect(staffdeck_read_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (args.tenant_id,))
            cursor.execute(
                """
                SELECT id, metadata_json ->> 'business_role'
                FROM agent_profiles
                WHERE tenant_id = %s AND status = 'active'
                  AND metadata_json ->> 'business_role' = ANY(%s)
                ORDER BY created_at
                """,
                (args.tenant_id, [item[0] for item in ROLE_APPS]),
            )
            for agent_id, business_role in cursor.fetchall():
                agent_by_role.setdefault(str(business_role), str(agent_id))
    missing_roles = [item[0] for item in ROLE_APPS if item[0] not in agent_by_role]
    if missing_roles:
        raise RuntimeError(f"No active digital employee exists for roles: {', '.join(missing_roles)}")

    now = datetime.now(UTC).replace(tzinfo=None)
    with psycopg.connect(staffdeck_dsn) as connection:
        with connection.cursor() as cursor:
            for item in provisioned:
                identity_id = deterministic_id(args.tenant_id, item["role"])
                cursor.execute(
                    """
                    INSERT INTO agent_service_identities (
                      id, tenant_id, agent_id, business_role, provider, issuer,
                      token_endpoint, jwks_uri, application_owner, application_name,
                      client_id, client_id_fingerprint, credential_ref, status,
                      token_ttl_seconds, metadata_json, created_at, updated_at
                    ) VALUES (
                      %s, %s, %s, %s, 'casdoor', 'http://localhost:18000',
                      'http://localhost:18000/api/login/oauth/access_token',
                      'http://localhost:18000/.well-known/jwks', 'admin', %s,
                      %s, %s, %s, 'active', 900, %s::json, %s, %s
                    )
                    ON CONFLICT (tenant_id, agent_id) DO UPDATE SET
                      business_role = EXCLUDED.business_role,
                      issuer = EXCLUDED.issuer,
                      token_endpoint = EXCLUDED.token_endpoint,
                      jwks_uri = EXCLUDED.jwks_uri,
                      application_owner = EXCLUDED.application_owner,
                      application_name = EXCLUDED.application_name,
                      client_id = EXCLUDED.client_id,
                      client_id_fingerprint = EXCLUDED.client_id_fingerprint,
                      credential_ref = EXCLUDED.credential_ref,
                      status = 'active',
                      token_ttl_seconds = 900,
                      metadata_json = EXCLUDED.metadata_json,
                      updated_at = EXCLUDED.updated_at
                    """,
                    (
                        identity_id,
                        args.tenant_id,
                        agent_by_role[item["role"]],
                        item["role"],
                        item["application_name"],
                        item["client_id"],
                        fingerprint(item["client_id"]),
                        item["credential_ref"],
                        json.dumps({"managed_by": "provision-agent-m2m.py", "label": item["label"]}),
                        now,
                        now,
                    ),
                )
        connection.commit()

    print(
        f"Provisioned {len(provisioned)} role-isolated Casdoor M2M applications for "
        f"tenant {args.tenant_id}; no client IDs, secrets, or tokens were printed."
    )


if __name__ == "__main__":
    main()
