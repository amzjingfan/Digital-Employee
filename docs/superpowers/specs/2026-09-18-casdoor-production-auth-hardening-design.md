# Casdoor Production Authentication Hardening Design

Date: 2026-09-18

## Status

Approved in chat for design documentation. Production implementation remains gated on review of this written specification.

## Goal

Keep Joukir's existing standards-based OIDC integration and local emergency-login capability while adding reliable Casdoor single sign-out, fail-closed production HTTPS validation, and a secret-safe way to initialize or rotate a local emergency administrator.

## Non-goals

- Do not add the Casdoor React SDK or Python SDK.
- Do not replace OIDC with SAML, CAS, LDAP, or SCIM.
- Do not persist Casdoor access or ID tokens in Joukir.
- Do not remove local authentication.
- Do not change the current development `admin / admin` credential automatically.
- Do not place production domains, passwords, client secrets, tokens, or raw authorization payloads in tracked files or logs.

## Context

Joukir currently implements OIDC Authorization Code flow with PKCE in `app/api/oidc.py`. It validates Casdoor JWTs through JWKS, maps Casdoor organizations to Joukir tenants, maps groups to business roles, stores the stable external subject in `user_identities`, and then issues its own `staffdeck_session` cookie. A separate Casdoor Management API client synchronizes group membership and account suspension state.

The existing logout route deletes the Joukir cookie but does not navigate the browser through Casdoor's RP-Initiated Logout endpoint. Consequently, the Casdoor browser session can remain active after Joukir logout. Production OIDC URLs and cookie security are also configured independently, so an accidental HTTP or insecure-cookie deployment is not rejected centrally. Demo seeding always creates local `admin / admin` when enabled, which is acceptable for the retained local development profile but not for production.

## Considered approaches

### 1. Front-channel RP-Initiated Logout, explicit production gate, and bootstrap command

This is the selected approach. The browser is redirected through Casdoor's configured `/api/logout` endpoint, which can use the existing Casdoor session cookie and then return to a pre-registered Joukir URL. Joukir stores no additional Casdoor token. Production safety is enforced through an explicit deployment environment and startup validation. A separate command initializes or rotates the emergency local administrator from a process environment secret.

Advantages: minimal new state, compatible with the existing architecture, no new SDK or schema, and easy to test. Limitation: logout depends on the browser reaching Casdoor; Joukir still clears its local session if that navigation later fails.

### 2. Persist Casdoor tokens and call `/api/sso-logout` server-to-server

This would support all-session logout without relying on a browser cookie, but it requires encrypted per-session token storage, token/session correlation, revocation cleanup, and a migration. It materially expands the secret-handling surface and is not justified by the current single-application requirement.

### 3. Replace the integration with Casdoor frontend/backend SDKs

The SDKs wrap capabilities that Joukir already implements. Replacing the current tested OIDC and management clients would increase dependency and migration risk without closing the production gaps by itself.

## Configuration contract

Add the following backend settings:

- `DEPLOYMENT_ENVIRONMENT`: `development` or `production`; default `development`.
- `OIDC_POST_LOGOUT_REDIRECT_URI`: the exact URL Casdoor may redirect to after logout.

In `development`, current behavior remains compatible: loopback HTTP endpoints, `OIDC_COOKIE_SECURE=false`, demo seeding, and the existing `admin / admin` seed remain allowed.

In `production`, startup validation must reject the process before database initialization when any of these conditions is true:

- OIDC is disabled or any required OIDC value is missing.
- `OIDC_ISSUER`, authorization endpoint, token endpoint, JWKS URI, end-session endpoint, redirect URI, or post-logout redirect URI does not use HTTPS.
- `OIDC_COOKIE_SECURE` is false.
- `APP_SECRET` is the development default or has fewer than 32 characters.
- `DATABASE_SEED_DEMO_DATA` is true.

The production gate validates configuration only. It does not make external network requests during application startup.

## Single sign-out flow

1. The frontend determines whether the current session uses the OIDC cookie (`auth_mode === "cookie"`) or a local bearer token.
2. A local bearer session continues to call `POST /api/auth/logout`, clear browser state, and return to the login page.
3. An OIDC session calls a new `POST /api/auth/oidc/logout` route.
4. The route records the Joukir logout event when the local session is valid, deletes `staffdeck_session`, and returns a JSON response containing either a validated Casdoor logout URL or the local post-logout URL as a safe fallback.
5. The frontend clears its local cached session and performs a top-level browser navigation to the returned URL.
6. The Casdoor logout URL contains only `client_id` and the configured `post_logout_redirect_uri`. It never accepts a caller-supplied return URL and never includes a Casdoor token.
7. Casdoor clears its browser session and redirects to the pre-registered Joukir login URL.

Both the enterprise console and chat UI must call one shared frontend logout helper so their behavior cannot diverge. If the logout preparation request fails, the helper still clears Joukir browser state and returns to the local login page.

## Casdoor application provisioning

Extend `configure-casdoor-oidc.py` with `--public-url`, defaulting to `http://127.0.0.1:5173` for local development.

- Strip a trailing slash and reject credentials, query strings, and fragments.
- Permit HTTP only for loopback hosts (`127.0.0.1` and `localhost`).
- Require HTTPS for every other host.
- Set the application homepage to the normalized public URL.
- Register `<public-url>/api/auth/oidc/callback` and `<public-url>/login` as allowed redirect URIs.
- Preserve both current loopback callback aliases when using the default local profile, so existing local startup remains compatible.

The migration script writes `OIDC_POST_LOGOUT_REDIRECT_URI=<public-url>/login`. Production operators must run the same provisioning logic against the intended Casdoor application before starting Joukir with the new URL.

## Emergency local administrator initialization

Add `src/backend/scripts/initialize_local_admin.py` with this contract:

- Required arguments: `--tenant-id` and `--username`.
- Optional argument: `--display-name`.
- Destructive opt-in: `--rotate-existing` is required to change an existing account password.
- Password source: `JOUKIR_BOOTSTRAP_ADMIN_PASSWORD` in the process environment only; no password command-line argument is supported.
- Password rules: at least 16 characters and not equal to the username or the known development defaults `admin`, `demo`, or `password`.
- The tenant must already exist and be active.
- A new account is created as an active local `platform_admin` with `role=admin`.
- Without `--rotate-existing`, an existing username causes a non-zero exit without modification.
- With `--rotate-existing`, the password hash is replaced and `session_version` is incremented to revoke existing Joukir sessions.
- Output may identify the tenant and username and state whether the account was created or rotated; it must never print the password, hash, database URL, or secrets.

This command is not invoked automatically. Local development seeding remains unchanged. Production deployments set `DATABASE_SEED_DEMO_DATA=false`, provision the tenant, create and verify a Casdoor administrator, and then optionally run this command to create the emergency local administrator.

## Failure handling

- Missing or unsafe production configuration: fail application startup with a message naming only the invalid setting keys.
- Missing optional logout configuration in development: clear the Joukir session and return the local login URL instead of stranding the user.
- Unreachable Casdoor during browser logout: the Joukir session is already cleared; the user can navigate back to Joukir manually.
- Invalid post-logout URL: reject it during startup/provisioning rather than accepting a runtime redirect.
- Existing emergency administrator without explicit rotation: exit without modifying the account.

## Security properties

- No open redirect: post-logout destinations come exclusively from validated server configuration.
- No new token store: Casdoor browser cookies remain owned by Casdoor.
- No production default password: production demo seeding is rejected.
- No implicit credential overwrite: rotation requires an explicit flag.
- No session survival after password rotation: `session_version` invalidates existing Joukir tokens.
- No secret output: tests must assert that command output excludes the supplied password and password hash.

## Files expected to change

- `src/backend/app/config.py`: deployment and post-logout settings.
- `src/backend/app/security/runtime_config.py`: production configuration validation.
- `src/backend/app/main.py`: invoke validation before database initialization.
- `src/backend/app/api/oidc.py`: OIDC logout preparation and shared local logout cleanup.
- `src/frontend-enterprise/src/authLogout.ts`: shared logout behavior.
- `src/frontend-enterprise/src/App.tsx`: use the shared helper.
- `src/frontend-enterprise/src/pages/chat/useChatSession.ts`: use the shared helper.
- `src/deploy/staffdeck-platform/scripts/configure-casdoor-oidc.py`: validated public URL and post-logout redirect registration.
- `src/deploy/staffdeck-platform/scripts/migrate-staffdeck.ps1`: write the post-logout setting.
- `src/backend/scripts/initialize_local_admin.py`: explicit local emergency administrator initialization/rotation.
- Focused backend, frontend, and deployment tests under `src/tests/`.
- Deployment documentation, this index, development log, project memory if a durable rule changes, and session handoff if implementation remains unfinished.

## Test strategy

Follow red-green TDD for every behavior change.

Backend tests must cover:

- Production rejects HTTP OIDC URLs, insecure cookies, weak/default `APP_SECRET`, enabled demo seeding, and missing post-logout configuration.
- Development accepts the current loopback profile.
- OIDC logout URL construction uses only configured values and URL-encodes them.
- OIDC logout deletes the local cookie and records a valid user's logout.
- Missing logout configuration in development returns the local fallback.
- Local logout behavior remains compatible.
- Administrator initialization creates the requested admin, rejects weak passwords, refuses implicit overwrite, rotates only with the flag, increments `session_version`, and does not expose the password.
- Casdoor provisioning rejects unsafe public URLs and produces the expected callback/post-logout redirect list.

Frontend tests must cover:

- OIDC sessions call the OIDC logout route, clear local state, and navigate to the returned URL.
- Local sessions call the existing local logout route and return to login.
- API failure still clears local state and returns to login.
- Console and chat logout paths both use the shared helper.

Verification commands must include focused pytest, Vitest, frontend typecheck, configuration check, i18n check if UI text changes, production build, Ruff on changed Python paths, and a development-profile startup/health check. A production-profile negative probe must demonstrate fail-closed behavior without changing the live protected `.env`.

## Rollout and rollback

1. Deploy code while leaving `DEPLOYMENT_ENVIRONMENT=development`; existing local behavior remains available.
2. Provision the Casdoor application with the intended production public URL and both redirect URIs.
3. Create and verify the Casdoor production administrator.
4. Set production secrets and OIDC URLs through the protected deployment handoff, run the emergency-admin command if desired, and set `DATABASE_SEED_DEMO_DATA=false`.
5. Switch to `DEPLOYMENT_ENVIRONMENT=production` and start the application; the startup gate either accepts the complete profile or fails before database initialization.
6. Perform human login, role/page, local logout, SSO logout, and re-login acceptance.

Rollback consists of returning `DEPLOYMENT_ENVIRONMENT` to `development` only in a controlled non-production environment or deploying the prior application version. Never weaken individual production checks to make a deployment start.

## Acceptance criteria

- Existing development `admin / admin` remains usable and no current credential is changed automatically.
- An OIDC user who logs out is sent through Casdoor and returns to the configured Joukir login page.
- Local users can still log out without contacting Casdoor.
- An unsafe production profile cannot start the application.
- A production local administrator can be created or explicitly rotated without exposing its password.
- No Casdoor SDK or new Casdoor token persistence is introduced.
