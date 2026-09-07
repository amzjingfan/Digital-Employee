\set ON_ERROR_STOP on

BEGIN;

DO $block$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM organization WHERE name = '九头蛇') THEN
    RAISE EXCEPTION 'Casdoor organization 九头蛇 does not exist';
  END IF;

  IF EXISTS (
    SELECT 1
      FROM application
     WHERE client_id = 'partner-core'
       AND NOT (owner = 'admin' AND name = 'partner-core')
  ) THEN
    RAISE EXCEPTION 'Casdoor client ID partner-core is already in use';
  END IF;
END
$block$;

WITH template AS (
  SELECT to_jsonb(application) AS value
    FROM application
   WHERE owner = 'admin' AND name = 'app-built-in'
), configured AS (
  SELECT value || jsonb_build_object(
    'owner', 'admin',
    'name', 'partner-core',
    'display_name', 'Partner Core',
    'homepage_url', 'http://127.0.0.1:5174',
    'description', 'Partner Core OIDC application',
    'organization', '九头蛇',
    'enable_sign_up', false,
    'enable_guest_signin', false,
    'disable_signin', false,
    'client_id', 'partner-core',
    'client_secret', replace(gen_random_uuid()::text, '-', '') || replace(gen_random_uuid()::text, '-', ''),
    'redirect_uris', '["http://127.0.0.1:5174/auth/callback","http://localhost:5174/auth/callback"]',
    'grant_types', '["authorization_code","refresh_token"]',
    'scopes', '[]',
    'expire_in_hours', 8,
    'refresh_expire_in_hours', 168
  ) AS value
  FROM template
)
INSERT INTO application
SELECT (jsonb_populate_record(NULL::application, value)).*
  FROM configured
ON CONFLICT (owner, name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  homepage_url = EXCLUDED.homepage_url,
  description = EXCLUDED.description,
  organization = EXCLUDED.organization,
  enable_sign_up = EXCLUDED.enable_sign_up,
  enable_guest_signin = EXCLUDED.enable_guest_signin,
  disable_signin = EXCLUDED.disable_signin,
  client_id = EXCLUDED.client_id,
  redirect_uris = EXCLUDED.redirect_uris,
  grant_types = EXCLUDED.grant_types,
  scopes = EXCLUDED.scopes,
  expire_in_hours = EXCLUDED.expire_in_hours,
  refresh_expire_in_hours = EXCLUDED.refresh_expire_in_hours;

DO $block$
BEGIN
  IF NOT FOUND AND NOT EXISTS (
    SELECT 1 FROM application WHERE owner = 'admin' AND name = 'partner-core'
  ) THEN
    RAISE EXCEPTION 'Casdoor built-in application template was not found';
  END IF;
END
$block$;

COMMIT;
