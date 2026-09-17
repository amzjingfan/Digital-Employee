BEGIN;

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS business_role VARCHAR NOT NULL DEFAULT 'member',
  ADD COLUMN IF NOT EXISTS authorization_source VARCHAR NOT NULL DEFAULT 'local',
  ADD COLUMN IF NOT EXISTS identity_groups_json JSON NOT NULL DEFAULT '[]'::json,
  ADD COLUMN IF NOT EXISTS role_synced_at TIMESTAMP;

DROP POLICY IF EXISTS business_role_migration_access ON users;
CREATE POLICY business_role_migration_access ON users
  FOR ALL TO staffdeck_migrator USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS business_role_identity_migration_access ON user_identities;
CREATE POLICY business_role_identity_migration_access ON user_identities
  FOR SELECT TO staffdeck_migrator USING (true);

UPDATE users
SET business_role = CASE WHEN role = 'admin' THEN 'platform_admin' ELSE 'member' END
WHERE business_role IS NULL OR business_role = '' OR business_role = 'member';

UPDATE users AS target
SET authorization_source = CASE
      WHEN target.role = 'admin' THEN 'oidc_admin'
      ELSE 'oidc_groups'
    END,
    role_synced_at = COALESCE(target.role_synced_at, CURRENT_TIMESTAMP)
WHERE EXISTS (
  SELECT 1
  FROM user_identities AS identity
  WHERE identity.tenant_id = target.tenant_id
    AND identity.user_id = target.id
    AND identity.provider = 'oidc'
);

CREATE INDEX IF NOT EXISTS ix_users_business_role ON users (business_role);
CREATE INDEX IF NOT EXISTS ix_users_authorization_source ON users (authorization_source);
CREATE INDEX IF NOT EXISTS ix_users_role_synced_at ON users (role_synced_at);

DROP POLICY business_role_identity_migration_access ON user_identities;
DROP POLICY business_role_migration_access ON users;

COMMIT;
