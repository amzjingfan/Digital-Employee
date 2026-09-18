# Authentication and agent endpoints

## Common headers

```http
Authorization: Bearer ${STAFFDECK_API_KEY}
Content-Type: application/json
```

Add `Idempotency-Key` to creates and other retryable writes. Never reuse a key with different request content.

## Browser session logout

Joukir exposes two logout contracts for its two retained authentication paths:

```text
POST  /api/auth/logout       Local bearer session; returns 204
POST  /api/auth/oidc/logout  OIDC cookie session; returns a redirect target
```

The OIDC response has this shape:

```json
{"redirect_url":"https://identity.example.com/api/logout?client_id=joukir-client&post_logout_redirect_uri=https%3A%2F%2Fjoukir.example.com%2Flogin"}
```

Both endpoints clear the Joukir `staffdeck_session` cookie and record a logout event when the
Joukir session is valid. A browser using OIDC must perform a top-level navigation to the returned
URL so Casdoor can clear its own browser session. The target is built exclusively from validated
server configuration; clients must never replace it with a user-supplied return address. If logout
preparation fails, clear local browser state and return to `/login`.

## Agents and gallery

```text
GET        /agents
POST       /agents
GET        /agents/{agent_id}
PATCH      /agents/{agent_id}             If-Match required
POST       /agents/{agent_id}:archive
GET        /agents/{agent_id}/capabilities
GET/PUT    /agents/{agent_id}/models
GET/PUT    /agents/{agent_id}/resources
GET        /gallery/agents
GET        /gallery/agents/{agent_id}
POST       /gallery/agents/{agent_id}:add
```

Create a blank agent:

```json
{"name":"Finance assistant","source_mode":"blank","metadata":{}}
```

Create an editable gallery copy:

```json
{"name":"Finance assistant copy","source_mode":"copy","copy_from_agent_id":"agent_xxx"}
```

## API client bootstrap

These routes require a tenant-admin login JWT, not an `sd_live_` key:

```text
GET/POST  /api-clients
PATCH     /api-clients/{client_id}
GET/POST  /api-clients/{client_id}/credentials
POST      /credentials/{credential_id}:rotate
POST      /credentials/{credential_id}:revoke
```

Credential bodies accept `name`, `scopes`, optional `agent_id`, and optional UTC RFC3339 `expires_at`. The plaintext `api_key` is returned only on create or rotate.
