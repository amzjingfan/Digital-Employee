# Casdoor Production Authentication Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep Joukir's current standard OIDC and emergency local login paths while adding Casdoor single sign-out, fail-closed production authentication configuration, safe public-URL provisioning, and explicit emergency administrator initialization.

**Architecture:** Preserve the existing FastAPI OIDC implementation and local bearer authentication. Add one pure startup validator, one server-controlled OIDC logout-preparation endpoint, one shared frontend logout helper, pure URL helpers around the Casdoor provisioning script, and one manual database administration command. Do not add a Casdoor SDK, persist Casdoor tokens, change schemas, or rotate any existing credential automatically.

**Tech Stack:** Python 3.11, FastAPI, Pydantic Settings, SQLModel, PyJWT, pytest, React 18, TypeScript, native `fetch`, Vitest, PowerShell deployment tooling.

**Spec:** [`docs/superpowers/specs/2026-09-18-casdoor-production-auth-hardening-design.md`](../specs/2026-09-18-casdoor-production-auth-hardening-design.md)

## Global Constraints

- Append a start and completion record to `docs/DEVELOPMENT_LOG.md` for every task before moving to the next task.
- Read protected runtime configuration only through the existing deployment handoff. Never print or commit password values, tokens, client secrets, database URLs, hashes, or raw external authorization payloads.
- Leave local development compatible with the existing loopback HTTP profile and the current seeded accounts.
- Production validation must run before `init_db()` and must not make network requests.
- All post-logout destinations must come from validated server configuration; never accept a caller-supplied return URL.
- Keep executable tests under `src/tests/` and use red-green TDD for each behavior change.
- Preserve unrelated worktree changes. Commit only the files named by the current task.

---

## Task 1: Add the fail-closed production authentication gate

**Files:**

- Create: `src/backend/app/security/runtime_config.py`
- Create: `src/tests/backend/test_runtime_config.py`
- Modify: `src/backend/app/config.py`
- Modify: `src/backend/app/main.py`
- Modify: `docs/DEVELOPMENT_LOG.md`

- [ ] **Step 1: Record the task start in the development log**

Append the date, objective, file scope, and the fact that no protected values will be read or logged.

- [ ] **Step 2: Write production-gate tests that initially fail**

Create `src/tests/backend/test_runtime_config.py` with a complete secure profile factory and focused mutations:

```python
from __future__ import annotations

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
        "oidc_authorization_endpoint": "https://identity.example.com/login/oauth/authorize",
        "oidc_token_endpoint": "https://identity.example.com/api/login/oauth/access_token",
        "oidc_jwks_uri": "https://identity.example.com/.well-known/jwks",
        "oidc_end_session_endpoint": "https://identity.example.com/api/logout",
        "oidc_client_id": "joukir-client",
        "oidc_client_secret": "client-secret",
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
    "overrides, invalid_key",
    [
        ({"oidc_enabled": False}, "OIDC_ENABLED"),
        ({"oidc_issuer": "http://identity.example.com"}, "OIDC_ISSUER"),
        ({"oidc_cookie_secure": False}, "OIDC_COOKIE_SECURE"),
        ({"app_secret": "change-me-in-development"}, "APP_SECRET"),
        ({"database_seed_demo_data": True}, "DATABASE_SEED_DEMO_DATA"),
        ({"oidc_post_logout_redirect_uri": ""}, "OIDC_POST_LOGOUT_REDIRECT_URI"),
    ],
)
def test_production_profile_rejects_unsafe_values(
    overrides: dict[str, object], invalid_key: str
) -> None:
    with pytest.raises(RuntimeError, match=invalid_key):
        validate_runtime_config(_production_settings(**overrides))
```

Also parametrize every required OIDC URL field so an HTTP value is rejected, and every required string field so a blank value is reported by key. Assert the exception contains setting names only and does not contain `client-secret` or the configured `APP_SECRET` value.

- [ ] **Step 3: Run the focused test and observe the expected failure**

Run:

```powershell
src\backend\.venv\Scripts\python.exe -m pytest -c pytest.ini src\tests\backend\test_runtime_config.py -q
```

Expected: collection fails because `app.security.runtime_config` and the new settings do not exist.

- [ ] **Step 4: Add the settings and pure validator**

In `src/backend/app/config.py`, add:

```python
deployment_environment: Literal["development", "production"] = "development"
oidc_post_logout_redirect_uri: str = ""
```

In `src/backend/app/security/runtime_config.py`, implement a function with this interface:

```python
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


def validate_runtime_config(settings: Settings) -> None:
    if settings.deployment_environment != "production":
        return
    invalid: set[str] = set()
    if not settings.oidc_enabled:
        invalid.add("OIDC_ENABLED")
    for key, attribute in _REQUIRED_OIDC_VALUES.items():
        if not str(getattr(settings, attribute)).strip():
            invalid.add(key)
    for key, attribute in {
        "OIDC_ISSUER": "oidc_issuer",
        "OIDC_AUTHORIZATION_ENDPOINT": "oidc_authorization_endpoint",
        "OIDC_TOKEN_ENDPOINT": "oidc_token_endpoint",
        "OIDC_JWKS_URI": "oidc_jwks_uri",
        "OIDC_END_SESSION_ENDPOINT": "oidc_end_session_endpoint",
        "OIDC_REDIRECT_URI": "oidc_redirect_uri",
        "OIDC_POST_LOGOUT_REDIRECT_URI": "oidc_post_logout_redirect_uri",
    }.items():
        value = str(getattr(settings, attribute)).strip()
        if value and urlsplit(value).scheme.lower() != "https":
            invalid.add(key)
    if not settings.oidc_cookie_secure:
        invalid.add("OIDC_COOKIE_SECURE")
    if settings.app_secret == _DEFAULT_APP_SECRET or len(settings.app_secret) < 32:
        invalid.add("APP_SECRET")
    if settings.database_seed_demo_data:
        invalid.add("DATABASE_SEED_DEMO_DATA")
    if invalid:
        raise RuntimeError(
            "Unsafe production authentication configuration: " + ", ".join(sorted(invalid))
        )
```

Keep this module side-effect free and free of log statements.

- [ ] **Step 5: Call validation before any database action**

Import `validate_runtime_config` in `src/backend/app/main.py` and make the startup sequence begin:

```python
def on_startup() -> None:
    acquire_runtime_instance_lock()
    try:
        validate_runtime_config(settings)
        init_db()
```

Add a test using monkeypatches against `app.main` that configures `deployment_environment="production"`, replaces `init_db` with a call recorder, and asserts an invalid profile raises before `init_db` is called.

- [ ] **Step 6: Run focused tests and lint**

Run:

```powershell
src\backend\.venv\Scripts\python.exe -m pytest -c pytest.ini src\tests\backend\test_runtime_config.py -q
src\backend\.venv\Scripts\python.exe -m ruff check src\backend\app\config.py src\backend\app\security\runtime_config.py src\backend\app\main.py src\tests\backend\test_runtime_config.py
```

Expected: all new tests pass and Ruff exits zero.

- [ ] **Step 7: Record evidence and commit**

Append changed files, both command results, remaining rollout risk, and Task 2 as the next step to `docs/DEVELOPMENT_LOG.md`.

```powershell
git add -- src/backend/app/config.py src/backend/app/security/runtime_config.py src/backend/app/main.py src/tests/backend/test_runtime_config.py docs/DEVELOPMENT_LOG.md
git commit -m "feat(auth): enforce production authentication config"
```

---

## Task 2: Add server-controlled Casdoor logout preparation

**Files:**

- Modify: `src/backend/app/api/oidc.py`
- Modify: `src/tests/backend/test_oidc_auth.py`
- Modify: `docs/DEVELOPMENT_LOG.md`

- [ ] **Step 1: Record the task start in the development log**

State that this task adds no token storage and accepts no caller-controlled redirect destination.

- [ ] **Step 2: Add failing URL and endpoint tests**

Extend `_settings()` in `test_oidc_auth.py` with:

```python
"oidc_end_session_endpoint": "https://identity.example.com/api/logout",
"oidc_post_logout_redirect_uri": "https://joukir.example.com/login",
```

Add tests for a pure URL builder:

```python
def test_oidc_logout_url_uses_only_server_configuration() -> None:
    logout_url = oidc._oidc_logout_url(_settings())
    query = parse_qs(urlsplit(logout_url).query)
    assert urlsplit(logout_url)._replace(query="").geturl() == (
        "https://identity.example.com/api/logout"
    )
    assert query == {
        "client_id": ["staffdeck-client"],
        "post_logout_redirect_uri": ["https://joukir.example.com/login"],
    }
```

Add endpoint tests with a temporary SQLModel session and `TestClient` or a direct route call:

- OIDC cookie logout deletes `staffdeck_session`, returns `{"redirect_url": <Casdoor URL>}`, and creates one `AccountLifecycleEvent` with `event_type="logout"` for a valid user.
- Missing end-session/post-logout configuration in development returns `{"redirect_url": "/login"}` and still deletes the cookie.
- Existing `POST /api/auth/logout` remains 204-compatible for bearer/local sessions.
- An invalid or expired cookie does not expose token data and still clears the cookie.

- [ ] **Step 3: Run the focused test and observe the expected failure**

```powershell
src\backend\.venv\Scripts\python.exe -m pytest -c pytest.ini src\tests\backend\test_oidc_auth.py -q
```

Expected: tests fail because `_oidc_logout_url` and `POST /api/auth/oidc/logout` do not exist.

- [ ] **Step 4: Extract shared local-session cleanup**

Refactor the current route without changing its response contract:

```python
def _record_logout(request: Request, db: Session) -> None:
    # Decode bearer first, then the OIDC cookie; record only a valid tenant/user match.
    # Catch HTTPException from token decoding, roll back, and never echo token content.


def _delete_session_cookie(response: Response) -> None:
    response.delete_cookie(OIDC_SESSION_COOKIE, path="/", samesite="lax")
```

Keep `POST /api/auth/logout` as status 204 and call these helpers.

- [ ] **Step 5: Implement the configured logout URL and endpoint**

Add:

```python
class OIDCLogoutRead(BaseModel):
    redirect_url: str


def _oidc_logout_url(settings: Settings) -> str:
    endpoint = settings.oidc_end_session_endpoint.strip()
    redirect_uri = settings.oidc_post_logout_redirect_uri.strip()
    if not endpoint or not redirect_uri or not settings.oidc_client_id.strip():
        return "/login"
    query = urlencode(
        {
            "client_id": settings.oidc_client_id,
            "post_logout_redirect_uri": redirect_uri,
        }
    )
    separator = "&" if urlsplit(endpoint).query else "?"
    return f"{endpoint}{separator}{query}"


@router.post("/oidc/logout", response_model=OIDCLogoutRead)
def oidc_logout(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
) -> Response:
    _record_logout(request, db)
    payload = OIDCLogoutRead(redirect_url=_oidc_logout_url(get_settings()))
    response = Response(
        content=payload.model_dump_json(),
        media_type="application/json",
    )
    _delete_session_cookie(response)
    return response
```

The startup gate from Task 1 is the production trust boundary for these configured URLs. Development deliberately falls back to the same-origin `/login` path.

- [ ] **Step 6: Run regression tests and lint**

```powershell
src\backend\.venv\Scripts\python.exe -m pytest -c pytest.ini src\tests\backend\test_oidc_auth.py src\tests\backend\test_auth_roles.py src\tests\backend\test_auth_password_hashing.py -q
src\backend\.venv\Scripts\python.exe -m ruff check src\backend\app\api\oidc.py src\tests\backend\test_oidc_auth.py
```

Expected: OIDC and existing local-auth tests pass; Ruff exits zero.

- [ ] **Step 7: Record evidence and commit**

```powershell
git add -- src/backend/app/api/oidc.py src/tests/backend/test_oidc_auth.py docs/DEVELOPMENT_LOG.md
git commit -m "feat(auth): prepare Casdoor single sign-out"
```

---

## Task 3: Route both frontend logout surfaces through one helper

**Files:**

- Create: `src/frontend-enterprise/src/authLogout.ts`
- Create: `src/tests/frontend/authLogout.test.ts`
- Modify: `src/frontend-enterprise/src/App.tsx`
- Modify: `src/frontend-enterprise/src/pages/chat/useChatSession.ts`
- Modify: `docs/DEVELOPMENT_LOG.md`

- [ ] **Step 1: Record the task start in the development log**

Note that the helper always clears local browser state, even when the network request fails.

- [ ] **Step 2: Write failing Vitest coverage for the shared helper**

Design the helper with injected navigation so it is deterministic in jsdom:

```typescript
export type LogoutNavigation = (url: string) => void;

export async function logoutEnterpriseSession(
  session: EnterpriseAuthSession | null,
  navigate: LogoutNavigation = (url) => window.location.assign(url),
): Promise<void>;
```

In `src/tests/frontend/authLogout.test.ts`, mock `globalThis.fetch`, seed `localStorage`, and assert:

- A cookie session posts `/api/auth/oidc/logout`, includes credentials, clears storage, then navigates to the returned Casdoor URL.
- A bearer session posts `/api/auth/logout` with its Authorization header, clears storage, then navigates to `/login`.
- A rejected request or non-2xx response still clears storage and navigates to `/login`.
- A malicious non-HTTP absolute redirect returned by the API is ignored in favor of `/login`; allow only same-origin relative paths, HTTPS URLs such as `https://identity.example.com/api/logout`, and loopback HTTP URLs such as `http://localhost:18000/api/logout` or `http://127.0.0.1:18000/api/logout` in development.

Use explicit assertions such as:

```typescript
expect(fetch).toHaveBeenCalledWith('/api/auth/oidc/logout', expect.objectContaining({
  method: 'POST',
  credentials: 'include',
}));
expect(localStorage.getItem(ENTERPRISE_AUTH_STORAGE_KEY)).toBeNull();
expect(navigate).toHaveBeenCalledWith('https://identity.example.com/api/logout?client_id=joukir');
```

- [ ] **Step 3: Run the focused frontend test and observe the expected failure**

```powershell
npm --prefix src/frontend-enterprise test -- authLogout.test.ts
```

Expected: the test fails because `@/authLogout` does not exist.

- [ ] **Step 4: Implement the helper with `fetch` and a finally-style cleanup**

Keep the dependency direction `authLogout.ts -> auth.ts`; do not import the shared API client because it imports `auth.ts` and would make the logout primitive harder to isolate.

The implementation must:

1. Select `/api/auth/oidc/logout` only for `auth_mode === 'cookie'`, otherwise `/api/auth/logout`.
2. Send `credentials: 'include'`; add Authorization only for a bearer token.
3. Parse `redirect_url` only for cookie sessions and only after a successful response.
4. Sanitize the navigation target using `new URL(value, window.location.origin)` and the allowed schemes/loopback exception.
5. Call `clearEnterpriseAuthSession()` before navigation on both success and failure.
6. Use `/login` as the stable local fallback.

- [ ] **Step 5: Replace both current logout implementations**

In `App.tsx`, replace the direct API call and clear with:

```typescript
function logout() {
  const currentSession = getEnterpriseAuthSession();
  setAuth(null);
  setAuthChecked(true);
  void logoutEnterpriseSession(currentSession);
}
```

In `useChatSession.ts`, separate authentication-expiry redirection from user-requested logout:

- Keep a local `redirectToLogin` for 401/session-expiry paths; it clears storage and assigns `/login` without attempting remote logout.
- Add a `logout` callback that calls `logoutEnterpriseSession(getEnterpriseAuthSession())`.
- Export the new `logout` callback in the hook result instead of aliasing `redirectToLogin`.

This prevents every incidental 401 from triggering Casdoor logout while making the explicit chat logout button use SSO logout.

- [ ] **Step 6: Run frontend verification**

```powershell
npm --prefix src/frontend-enterprise test -- authLogout.test.ts App.test.tsx
npm --prefix src/frontend-enterprise run test:typecheck
npm --prefix src/frontend-enterprise run config:check
npm --prefix src/frontend-enterprise run build
```

Expected: all commands exit zero. `i18n:check` is not required because no user-facing string changes in this task.

- [ ] **Step 7: Record evidence and commit**

```powershell
git add -- src/frontend-enterprise/src/authLogout.ts src/frontend-enterprise/src/App.tsx src/frontend-enterprise/src/pages/chat/useChatSession.ts src/tests/frontend/authLogout.test.ts docs/DEVELOPMENT_LOG.md
git commit -m "feat(auth): unify browser logout behavior"
```

---

## Task 4: Make Casdoor provisioning public-URL aware

**Files:**

- Modify: `src/deploy/staffdeck-platform/scripts/configure-casdoor-oidc.py`
- Create: `src/tests/backend/test_casdoor_oidc_provisioning.py`
- Modify: `src/deploy/staffdeck-platform/scripts/migrate-staffdeck.ps1`
- Modify: `docs/DEVELOPMENT_LOG.md`

- [ ] **Step 1: Record the task start in the development log**

State that tests exercise URL normalization and configuration rendering without connecting to Casdoor or reading a protected environment file.

- [ ] **Step 2: Add failing pure-function tests for public URL handling**

Load the hyphenated provisioning script with `importlib.util.spec_from_file_location` and test this contract:

```python
@pytest.mark.parametrize(
    "value, expected",
    [
        ("http://127.0.0.1:5173/", "http://127.0.0.1:5173"),
        ("http://localhost:5173", "http://localhost:5173"),
        ("https://joukir.example.com/", "https://joukir.example.com"),
    ],
)
def test_normalize_public_url_accepts_safe_origins(value: str, expected: str) -> None:
    assert module.normalize_public_url(value) == expected
```

Reject:

- `http://joukir.example.com`
- `https://user:password@joukir.example.com`
- `https://joukir.example.com/path`
- `https://joukir.example.com?tenant=demo`
- `https://joukir.example.com/#fragment`

Test `application_redirect_uris()`:

- Default `http://127.0.0.1:5173` produces both current loopback callback aliases plus `http://127.0.0.1:5173/login`.
- `https://joukir.example.com` produces exactly its callback and login URI.

- [ ] **Step 3: Run the focused test and observe the expected failure**

```powershell
src\backend\.venv\Scripts\python.exe -m pytest -c pytest.ini src\tests\backend\test_casdoor_oidc_provisioning.py -q
```

Expected: tests fail because the pure URL helpers do not exist.

- [ ] **Step 4: Implement URL helpers and the CLI argument**

Add:

```python
from urllib.parse import urlsplit

DEFAULT_PUBLIC_URL = "http://127.0.0.1:5173"


def normalize_public_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("public URL must not contain credentials, query, or fragment")
    if parsed.path not in {"", "/"} or not parsed.hostname:
        raise ValueError("public URL must be an origin without a path")
    is_loopback = parsed.hostname in {"127.0.0.1", "localhost"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and is_loopback):
        raise ValueError("public URL must use HTTPS except on loopback")
    return value.strip().rstrip("/")


def application_redirect_uris(public_url: str) -> list[str]:
    if public_url == DEFAULT_PUBLIC_URL:
        return [
            f"{public_url}/api/auth/oidc/callback",
            "http://localhost:5173/api/auth/oidc/callback",
            f"{public_url}/login",
        ]
    return [f"{public_url}/api/auth/oidc/callback", f"{public_url}/login"]
```

Add `--public-url` with `default=DEFAULT_PUBLIC_URL`, normalize it before opening the database, set `homepage_url` from it, and serialize `application_redirect_uris(public_url)` into `redirect_uris`.

- [ ] **Step 5: Make the migration script write the post-logout URI**

Add a `PublicUrl` parameter to `migrate-staffdeck.ps1` with the same local default. Validate it before stopping the service using `[Uri]`, the same origin-only and HTTPS-or-loopback rules, normalize it with `TrimEnd('/')`, and write:

```powershell
Set-EnvValue $backendEnvPath 'OIDC_REDIRECT_URI' "$normalizedPublicUrl/api/auth/oidc/callback"
Set-EnvValue $backendEnvPath 'OIDC_POST_LOGOUT_REDIRECT_URI' "$normalizedPublicUrl/login"
```

Do not change the Casdoor issuer endpoints; they remain independently configured for the current local platform deployment.

Add a source-level assertion to the provisioning test that the PowerShell script contains the new key, validates `$PublicUrl`, and derives both Joukir redirect values from `$normalizedPublicUrl`. This is intentionally a narrow regression check, not a PowerShell integration test with secrets.

- [ ] **Step 6: Run focused tests and lint**

```powershell
src\backend\.venv\Scripts\python.exe -m pytest -c pytest.ini src\tests\backend\test_casdoor_oidc_provisioning.py -q
src\backend\.venv\Scripts\python.exe -m ruff check src\deploy\staffdeck-platform\scripts\configure-casdoor-oidc.py src\tests\backend\test_casdoor_oidc_provisioning.py
```

Expected: all tests pass; Ruff exits zero. Do not execute provisioning against the live Casdoor database in this task.

- [ ] **Step 7: Record evidence and commit**

```powershell
git add -- src/deploy/staffdeck-platform/scripts/configure-casdoor-oidc.py src/deploy/staffdeck-platform/scripts/migrate-staffdeck.ps1 src/tests/backend/test_casdoor_oidc_provisioning.py docs/DEVELOPMENT_LOG.md
git commit -m "feat(deploy): provision Casdoor logout redirects"
```

---

## Task 5: Add explicit emergency local administrator initialization

**Files:**

- Create: `src/backend/scripts/initialize_local_admin.py`
- Create: `src/tests/backend/test_initialize_local_admin.py`
- Modify: `docs/DEVELOPMENT_LOG.md`

- [ ] **Step 1: Record the task start in the development log**

State that the command is manual, never reads a password argument, and never emits the password, hash, or database URL.

- [ ] **Step 2: Write failing service-level tests**

Keep business behavior in a testable function instead of testing only subprocess parsing:

```python
def initialize_local_admin(
    db: Session,
    *,
    tenant_id: str,
    username: str,
    display_name: str | None,
    password: str,
    rotate_existing: bool,
) -> Literal["created", "rotated"]:
```

Create an in-memory SQLModel database with one active tenant and cover:

- A strong password creates `role="admin"`, `business_role="platform_admin"`, `authorization_source="local"`, `source="web"`, `status="active"`, and a verifiable password hash.
- A missing/inactive tenant raises without creating a user.
- Passwords shorter than 16 or equal case-insensitively to username, `admin`, `demo`, or `password` are rejected.
- An existing username raises without changing its hash when `rotate_existing=False`.
- `rotate_existing=True` changes the hash, increments `session_version` exactly once, restores the required admin fields, and commits atomically.
- Captured stdout/stderr from `main()` does not contain the supplied password, resulting hash, or database URL.
- `argparse` rejects `--password` because no such argument exists.

- [ ] **Step 3: Run the focused test and observe the expected failure**

```powershell
src\backend\.venv\Scripts\python.exe -m pytest -c pytest.ini src\tests\backend\test_initialize_local_admin.py -q
```

Expected: collection fails because `src/backend/scripts/initialize_local_admin.py` does not exist.

- [ ] **Step 4: Implement validation and transactional initialization**

The script must:

```python
PASSWORD_ENV = "JOUKIR_BOOTSTRAP_ADMIN_PASSWORD"
FORBIDDEN_PASSWORDS = {"admin", "demo", "password"}


def validate_password(password: str, username: str) -> None:
    normalized = password.casefold()
    if len(password) < 16 or normalized == username.casefold() or normalized in FORBIDDEN_PASSWORDS:
        raise ValueError("bootstrap administrator password does not satisfy policy")
```

Use `select(Tenant)`/`select(User)` scoped by `tenant_id`, call `hash_password`, set `updated_at=utc_now()` on rotation, increment `session_version`, and call `db.commit()` only after all validation succeeds. On an exception, `main()` must roll back, print a generic non-secret error to stderr, and exit non-zero.

The CLI contract is exactly:

```python
parser.add_argument("--tenant-id", required=True)
parser.add_argument("--username", required=True)
parser.add_argument("--display-name")
parser.add_argument("--rotate-existing", action="store_true")
```

Read the password with `os.environ.get(PASSWORD_ENV, "")`; if absent, fail with a message naming the environment variable only. On success, print JSON containing only `tenant_id`, `username`, and `action`.

- [ ] **Step 5: Run focused tests and lint**

```powershell
src\backend\.venv\Scripts\python.exe -m pytest -c pytest.ini src\tests\backend\test_initialize_local_admin.py -q
src\backend\.venv\Scripts\python.exe -m ruff check src\backend\scripts\initialize_local_admin.py src\tests\backend\test_initialize_local_admin.py
```

Expected: all tests pass; Ruff exits zero. Do not run the command against the live database during automated verification.

- [ ] **Step 6: Record evidence and commit**

```powershell
git add -- src/backend/scripts/initialize_local_admin.py src/tests/backend/test_initialize_local_admin.py docs/DEVELOPMENT_LOG.md
git commit -m "feat(auth): add emergency admin initializer"
```

---

## Task 6: Document operator workflow and durable security decisions

**Files:**

- Modify: `src/deploy/staffdeck-platform/README.md`
- Modify: `src/skills/staffdeck-api-auth/references/endpoints.md`
- Modify: `docs/PROJECT_MEMORY.md`
- Modify: `docs/README.md`
- Modify: `docs/DEVELOPMENT_LOG.md`

- [ ] **Step 1: Record the task start in the development log**

Define scope as documentation only and state that all examples use synthetic values.

- [ ] **Step 2: Update the authentication endpoint reference**

Document both logout contracts:

- `POST /api/auth/logout`: local/bearer-compatible logout, 204.
- `POST /api/auth/oidc/logout`: clears the Joukir cookie and returns `{"redirect_url":"https://identity.example.com/api/logout"}` for top-level browser navigation.

State that clients must not accept arbitrary logout destinations from user input.

- [ ] **Step 3: Add a production rollout runbook section**

In `src/deploy/staffdeck-platform/README.md`, document this sequence without real credentials:

1. Provision Casdoor with `--public-url https://joukir.example.com`.
2. Register/verify the Casdoor production administrator.
3. Set `DEPLOYMENT_ENVIRONMENT=production`, every required HTTPS OIDC URL, `OIDC_COOKIE_SECURE=true`, a strong `APP_SECRET`, `DATABASE_SEED_DEMO_DATA=false`, and the post-logout redirect through the protected handoff.
4. Optionally set `JOUKIR_BOOTSTRAP_ADMIN_PASSWORD` in the process environment and run:

```powershell
src\backend\.venv\Scripts\python.exe src\backend\scripts\initialize_local_admin.py --tenant-id tenant_demo --username emergency-admin --display-name "Emergency Administrator"
```

5. Remove the bootstrap password from the process environment.
6. Start Joukir and perform local login/logout, OIDC login/logout/re-login, role, page, and cookie-security acceptance checks.

Explicitly warn that `--rotate-existing` invalidates existing Joukir sessions and must be deliberate.

- [ ] **Step 4: Record the lasting architecture rule**

Add a concise item to `docs/PROJECT_MEMORY.md`: Joukir uses standard OIDC for Casdoor, retains an explicit emergency local path, performs front-channel single sign-out without token persistence, and production must pass the fail-closed authentication gate.

- [ ] **Step 5: Update the docs index**

Add the implementation plan beside its approved design under `Current designs`, and ensure the deployment guide and endpoint reference remain discoverable from existing index sections.

- [ ] **Step 6: Verify documentation hygiene**

```powershell
git diff --check
git grep -n -E "(JOUKIR_BOOTSTRAP_ADMIN_PASSWORD[=]|OIDC_CLIENT_SECRET[=]|APP_SECRET[=])" -- docs src/deploy/staffdeck-platform/README.md src/skills/staffdeck-api-auth/references/endpoints.md
```

Expected: `git diff --check` exits zero. The secret-pattern scan returns no assignments containing credential values; setting names in prose are acceptable only without `=<value>`.

- [ ] **Step 7: Record evidence and commit**

```powershell
git add -- src/deploy/staffdeck-platform/README.md src/skills/staffdeck-api-auth/references/endpoints.md docs/PROJECT_MEMORY.md docs/README.md docs/DEVELOPMENT_LOG.md
git commit -m "docs(auth): add Casdoor production runbook"
```

---

## Task 7: Run integrated regression and acceptance probes

**Files:**

- Modify: `docs/DEVELOPMENT_LOG.md`
- Modify only if work remains unfinished: `docs/SESSION_HANDOFF.md`

- [ ] **Step 1: Record the verification start in the development log**

List the exact suites below and state that the production-negative probe will use an isolated process environment, not the protected `.env`.

- [ ] **Step 2: Run focused and neighboring backend tests**

```powershell
src\backend\.venv\Scripts\python.exe -m pytest -c pytest.ini src\tests\backend\test_runtime_config.py src\tests\backend\test_oidc_auth.py src\tests\backend\test_auth_roles.py src\tests\backend\test_auth_password_hashing.py src\tests\backend\test_initialize_local_admin.py src\tests\backend\test_casdoor_oidc_provisioning.py -q
src\backend\.venv\Scripts\python.exe src\tests\check_test_layout.py
src\backend\.venv\Scripts\python.exe -m ruff check src\backend\app\config.py src\backend\app\main.py src\backend\app\security\runtime_config.py src\backend\app\api\oidc.py src\backend\scripts\initialize_local_admin.py src\deploy\staffdeck-platform\scripts\configure-casdoor-oidc.py src\tests\backend\test_runtime_config.py src\tests\backend\test_oidc_auth.py src\tests\backend\test_initialize_local_admin.py src\tests\backend\test_casdoor_oidc_provisioning.py
```

Expected: all tests pass, layout validation passes, Ruff exits zero.

- [ ] **Step 3: Run the frontend suite and production build**

```powershell
npm --prefix src/frontend-enterprise test
npm --prefix src/frontend-enterprise run test:typecheck
npm --prefix src/frontend-enterprise run config:check
npm --prefix src/frontend-enterprise run i18n:check
npm --prefix src/frontend-enterprise run build
```

Expected: all commands exit zero.

- [ ] **Step 4: Prove the production gate fails before database initialization**

Run only the pure validator in an isolated one-shot process with synthetic values:

```powershell
Push-Location src/backend
try {
    $env:DEPLOYMENT_ENVIRONMENT='production'
    $env:DATABASE_SEED_DEMO_DATA='true'
    $env:OIDC_ENABLED='false'
    .\.venv\Scripts\python.exe -c "from app.config import Settings; from app.security.runtime_config import validate_runtime_config; validate_runtime_config(Settings(_env_file=None))"
    if ($LASTEXITCODE -eq 0) {
        throw 'production gate unexpectedly accepted unsafe configuration'
    }
} finally {
    Remove-Item Env:DEPLOYMENT_ENVIRONMENT -ErrorAction SilentlyContinue
    Remove-Item Env:DATABASE_SEED_DEMO_DATA -ErrorAction SilentlyContinue
    Remove-Item Env:OIDC_ENABLED -ErrorAction SilentlyContinue
    Pop-Location
}
```

Expected: non-zero exit naming invalid configuration keys and containing no secret values.

- [ ] **Step 5: Verify the development profile and health endpoint**

If the existing local service is already running, call `http://127.0.0.1:5173/api/health` without restarting it. Otherwise use the documented development lifecycle:

```powershell
src\scripts\dev_up.ps1 -Detach
src\scripts\dev_status.ps1
```

Then verify:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:5173/api/health'
```

Expected: `status` is `ok`. Do not exercise the live Casdoor administrator password. Human OIDC logout acceptance remains a rollout step because it requires an operator-owned Casdoor browser session.

- [ ] **Step 6: Review the aggregate diff and repository state**

```powershell
git diff --check
git status --short
git log -7 --oneline
```

Expected: no whitespace errors, only intended uncommitted verification-log changes before the final documentation commit, and one focused commit per preceding task.

- [ ] **Step 7: Record final evidence and commit**

Append command results, the deferred human OIDC browser acceptance, and the exact production rollout sequence to `docs/DEVELOPMENT_LOG.md`. If every code and automated verification step is complete, do not rewrite `docs/SESSION_HANDOFF.md`; if work is incomplete, update it with the branch, verified state, blocker, and exact next commands.

```powershell
git add -- docs/DEVELOPMENT_LOG.md docs/SESSION_HANDOFF.md
git commit -m "test(auth): verify Casdoor production hardening"
```

If `docs/SESSION_HANDOFF.md` was unchanged, omit it from `git add`.

## Completion Criteria

- Existing development local accounts remain unchanged and usable.
- Production cannot reach database initialization with an incomplete or unsafe authentication profile.
- Cookie/OIDC logout clears the Joukir session and navigates through the configured Casdoor logout endpoint.
- Bearer/local logout remains independent from Casdoor.
- Console and chat explicit logout actions share one tested implementation.
- Casdoor application provisioning registers the public callback and post-logout login URI without accepting unsafe origins.
- Emergency administrator creation and explicit rotation never expose credential material and rotation revokes existing Joukir sessions.
- Focused backend tests, frontend tests, typecheck, config check, i18n check, build, Ruff, layout validation, development health, and production-negative probe all pass.
- Human production acceptance for Casdoor login, logout, role access, and re-login is documented for the deployment operator.
