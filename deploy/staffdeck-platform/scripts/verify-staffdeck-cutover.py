from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx
import psycopg
from psycopg.errors import InsufficientPrivilege


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def dsn(*, role: str, password: str, port: str, database: str) -> str:
    return (
        f"postgresql://{role}:{quote_plus(password)}@127.0.0.1:{port}/{database}"
        "?sslmode=disable"
    )


def scalar(connection: psycopg.Connection, query: str) -> object:
    return connection.execute(query).fetchone()[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify StaffDeck OIDC/PostgreSQL cutover")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument(
        "--full-oidc",
        action="store_true",
        help="complete a real authorization-code callback using CASDOOR_TEST_ADMIN_PASSWORD",
    )
    args = parser.parse_args()
    env = read_env(args.env_file)
    port = env["POSTGRES_PORT"]

    runtime_dsn = dsn(
        role="staffdeck_runtime",
        password=env["STAFFDECK_RUNTIME_PASSWORD"],
        port=port,
        database="staffdeck_app",
    )
    worker_dsn = dsn(
        role="staffdeck_worker",
        password=env["STAFFDECK_WORKER_PASSWORD"],
        port=port,
        database="staffdeck_app",
    )
    migrator_dsn = dsn(
        role="staffdeck_migrator",
        password=env["STAFFDECK_MIGRATOR_PASSWORD"],
        port=port,
        database="staffdeck_app",
    )
    casdoor_dsn = dsn(
        role="casdoor",
        password=env["CASDOOR_DB_PASSWORD"],
        port=port,
        database="casdoor",
    )

    with psycopg.connect(migrator_dsn) as migrator:
        migration = migrator.execute(
            """
            SELECT source_table_count, source_row_count
            FROM public.staffdeck_schema_migrations
            WHERE migration_id = '20260830_sqlite_to_postgresql_v1'
            """
        ).fetchone()
        assert migration == (71, 1186), migration
        forced_rls_count = int(
            scalar(
                migrator,
                """
                SELECT count(*)
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relforcerowsecurity
                """,
            )
        )
        assert forced_rls_count >= 67, forced_rls_count

    with psycopg.connect(runtime_dsn, autocommit=True) as runtime:
        assert scalar(runtime, "SELECT count(*) FROM public.users") == 0
        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_demo', true)")
        assert scalar(runtime, "SELECT count(*) FROM public.users") == 2
        assert scalar(runtime, "SELECT count(*) FROM public.skills") == 25
        assert scalar(runtime, "SELECT count(*) FROM public.tenants") == 1
        runtime.execute("ROLLBACK")
        assert scalar(runtime, "SELECT count(*) FROM public.users") == 0

        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_other', true)")
        assert scalar(runtime, "SELECT count(*) FROM public.users") == 0
        runtime.execute("ROLLBACK")

        runtime.execute("BEGIN")
        runtime.execute("SELECT set_config('app.tenant_id', 'tenant_demo', true)")
        denied = False
        try:
            runtime.execute(
                """
                INSERT INTO public.users (
                  id, tenant_id, username, role, source, password_hash, created_at, updated_at
                ) VALUES (
                  'verify_cross_tenant', 'tenant_other', 'verify_cross_tenant', 'member',
                  'web', 'disabled', now(), now()
                )
                """
            )
        except InsufficientPrivilege:
            denied = True
        finally:
            runtime.execute("ROLLBACK")
        assert denied, "cross-tenant insert was not denied"

        try:
            runtime.execute("SELECT count(*) FROM public.mock_orders")
        except InsufficientPrivilege:
            pass
        else:
            raise AssertionError("runtime unexpectedly has mock_orders access")

        runtime.execute("DELETE FROM public.oidc_login_states")

    with psycopg.connect(worker_dsn) as worker:
        assert scalar(worker, "SELECT count(*) FROM public.users") == 2

    with psycopg.connect(casdoor_dsn) as casdoor:
        app = casdoor.execute(
            """
            SELECT client_id, redirect_uris, grant_types, organization
            FROM application WHERE owner = 'admin' AND name = 'app-staffdeck'
            """
        ).fetchone()
        assert app is not None
        assert app[0] == env["STAFFDECK_OIDC_CLIENT_ID"]
        assert "http://127.0.0.1:5173/api/auth/oidc/callback" in app[1]
        assert "authorization_code" in app[2]
        assert app[3] == "built-in"

    with httpx.Client(follow_redirects=False, timeout=10) as client:
        health = client.get("http://127.0.0.1:5173/api/health")
        health.raise_for_status()
        oidc_config = client.get("http://127.0.0.1:5173/api/auth/oidc/config")
        oidc_config.raise_for_status()
        assert oidc_config.json()["enabled"] is True
        login = client.get("http://127.0.0.1:5173/api/auth/oidc/login")
        assert login.status_code in {302, 307}
        location = login.headers["location"]
        parsed = urlparse(location)
        assert parsed.hostname == "localhost" and parsed.port == 18000
        assert "code_challenge_method=S256" in location

        if args.full_oidc:
            admin_password = os.environ.get("CASDOOR_TEST_ADMIN_PASSWORD", "")
            if not admin_password:
                raise RuntimeError("CASDOOR_TEST_ADMIN_PASSWORD is required for --full-oidc")
            authorization = parse_qs(parsed.query)
            login_response = client.post(
                "http://localhost:18000/api/login",
                params={
                    "clientId": authorization["client_id"][0],
                    "responseType": authorization["response_type"][0],
                    "redirectUri": authorization["redirect_uri"][0],
                    "scope": authorization["scope"][0],
                    "state": authorization["state"][0],
                    "nonce": authorization["nonce"][0],
                    "code_challenge": authorization["code_challenge"][0],
                    "code_challenge_method": authorization["code_challenge_method"][0],
                },
                json={
                    "type": "code",
                    "signinMethod": "Password",
                    "organization": "built-in",
                    "username": "admin",
                    "password": admin_password,
                    "application": "app-staffdeck",
                },
            )
            login_response.raise_for_status()
            login_payload = login_response.json()
            assert login_payload.get("status") == "ok", login_payload.get("msg")
            code = str(login_payload.get("data") or "")
            assert code
            callback = client.get(
                "http://127.0.0.1:5173/api/auth/oidc/callback",
                params={"code": code, "state": authorization["state"][0]},
            )
            assert callback.status_code == 302, callback.text
            assert "oidc=success" in callback.headers["location"]
            current_user = client.get("http://127.0.0.1:5173/api/auth/me")
            current_user.raise_for_status()
            user_payload = current_user.json()
            assert user_payload["tenant_id"] == "tenant_demo"
            assert user_payload["username"] == "admin"
            logout = client.post("http://127.0.0.1:5173/api/auth/logout")
            assert logout.status_code == 204

    suffix = " and full callback" if args.full_oidc else ""
    print(
        "Cutover verification passed: migration, forced RLS, role separation, "
        f"and OIDC PKCE{suffix}."
    )


if __name__ == "__main__":
    main()
