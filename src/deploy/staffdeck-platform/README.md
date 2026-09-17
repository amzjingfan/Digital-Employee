# StaffDeck platform local environment

This directory prepares the first local development baseline for the cross-border e-commerce digital workforce platform.

## Validated workstation status (2026-08-29)

- StaffDeck API health and gallery page are available on port `5173`.
- PostgreSQL/pgvector and Casdoor are running and healthy under Rancher Desktop.
- Rancher Desktop WSL virtual disks and container images are stored under `D:\saas\runtime\rancher-desktop` through a verified directory junction.
- PostgreSQL RLS read isolation passed for two tenants and missing tenant context.
- A spoofed cross-tenant insert was denied.
- The tenant-domain Casbin model passed the administrator/member baseline and seven business-role decisions.
- StaffDeck's targeted backend authorization/database tests passed (`42 passed`), and the frontend production build completed.

## Current boundary

- StaffDeck now uses PostgreSQL `staffdeck_app`; the original SQLite database and timestamped snapshots remain available for rollback.
- Casdoor `admin/app-staffdeck` is connected through OIDC authorization code flow with S256 PKCE, nonce validation, verified organization-to-tenant mapping, and an HttpOnly StaffDeck session cookie.
- The HTTP-facing StaffDeck process runs with the `staffdeck_runtime` role and `STAFFDECK_ROLE=api`; background workers are separated from request handling and use the dedicated `staffdeck_worker` role when enabled.
- Forced PostgreSQL RLS protects the migrated StaffDeck business tables. Demo `mock_orders` is not granted to runtime roles and the Mock API is disabled in the PostgreSQL profile.
- PyCasbin now enforces tenant-domain object/action policies for enterprise APIs. Every allow/deny decision is stored with actor, role, policy version, and request ID; administrators can inspect it from the 权限审计 page.
- Casdoor binds `app-staffdeck` to the configured tenant organization and provisions one uniquely prefixed StaffDeck department group plus seven cross-border e-commerce job groups inside that organization. The verified `groups` claim maps users to operations supervisor, after-sales, Listing compliance, logistics exception, advertising inspection, designer, or procurement roles; unmapped and conflicting non-admin identities are denied at login.
- Seven additional Client-Credentials-only Casdoor applications authenticate the seven role digital employees. StaffDeck binds each application to exactly one tenant, business role and employee; Casdoor authentication never replaces StaffDeck/Casbin/RLS business authorization.
- Every claimed work-task Run owns an append-only launch snapshot covering the employee profile, expanded SOP versions, knowledge-base version IDs, tool digests and M2M identity fingerprint. Tool drift and revoked bindings fail closed.
- Administrators can inspect configured group mappings and each account's last synchronized effective role from the 身份与角色 page.
- All published host ports bind to `127.0.0.1` only.

## Versions

- Casdoor image: `casbin/casdoor:3.161.1`
- PostgreSQL image: `pgvector/pgvector:0.8.6-pg16-bookworm`
- Python: 3.11 or newer
- Node.js: 20 or newer
- Container runtime: Rancher Desktop with the Moby engine is recommended on Windows

## Start infrastructure

Run PowerShell from this directory:

```powershell
.\scripts\install-runtime.ps1
.\scripts\configure-runtime-storage.ps1
.\scripts\setup.ps1
.\scripts\pull-images.ps1
.\scripts\up.ps1
.\scripts\verify.ps1
```

`install-runtime.ps1` verifies the official Rancher Desktop installer hash and requests Windows administrator elevation for WSL and MSI installation. Because this workstation has limited free space on C:, it installs the application under `D:\Apps\Rancher Desktop` and writes MSI temporary files and logs to D:. `configure-runtime-storage.ps1` must be run before Rancher Desktop starts for the first time; it redirects `%LOCALAPPDATA%\rancher-desktop` to `D:\saas\runtime\rancher-desktop`, including both WSL virtual disks, images, cache, and logs. Windows may require a restart before the container engine can start.

`pull-images.ps1` is the pinned-digest fallback for networks where Docker Hub is DNS-poisoned or reset. The two linux/amd64 manifest digests were independently compared through the 1ms and DaoCloud mirrors before being recorded in `SOURCE_MANIFEST.md`; the script pulls those exact digests, verifies them, and tags the images with the names used by Compose.

`restart-wsl-service.ps1` is a recovery-only helper for a stuck WSL service after an in-place WSL update. It requires elevation and terminates active WSL processes, so do not run it during normal startup.

The Casbin model can be checked independently of containers:

```powershell
D:\saas\third_party\StaffDeck\src\backend\.venv\Scripts\python.exe .\scripts\verify_casbin.py
```

Local endpoints:

- Casdoor: `http://127.0.0.1:18000`
- PostgreSQL: `127.0.0.1:55432`

Casdoor sample data commonly provides the `built-in/admin` account with password `123`. Change it immediately after first login and never expose this development instance to the public network.

`built-in` is reserved for Casdoor global administrators. StaffDeck human users must be created in `STAFFDECK_CASDOOR_ORGANIZATION`; never enable privileged consent merely to create a business user under `built-in`.

## OIDC and PostgreSQL cutover

The repeatable local workflow is:

```powershell
Set-Location D:\saas\deploy\staffdeck-platform
D:\saas\third_party\StaffDeck\src\backend\.venv\Scripts\python.exe `
  .\scripts\configure-casdoor-oidc.py --env-file .\.env
.\scripts\migrate-staffdeck.ps1
D:\saas\third_party\StaffDeck\src\backend\.venv\Scripts\python.exe `
  .\scripts\verify-staffdeck-cutover.py --env-file .\.env
```

迁移脚本同时启用统一任务执行 Worker 的安全演示配置：`WORK_TASK_EXECUTION_ENABLED=true`、`WORK_TASK_EXECUTION_MODE=sandbox`、`WORK_TASK_EXECUTION_TENANT_IDS=tenant_demo`。它还创建七个岗位数字员工、七个独立 Casdoor M2M 应用和对应服务身份，并将 Client Secret 写入 `D:\saas\runtime\staffdeck-secrets\agent-m2m.json`。该文件继承被移除，仅当前 Windows 运行用户和 `SYSTEM` 有权限；仓库和 StaffDeck 业务库只保存引用与指纹。Sandbox 会真实完成 M2M Token 换取/验签并创建 Run、不可变启动快照、独立会话、租约和 Trace，但不会调用外部模型或业务工具。

可重复执行以下无密钥输出的验证：

```powershell
Set-Location D:\saas\third_party\StaffDeck\backend
.\.venv\Scripts\python.exe .\scripts\verify_agent_m2m.py --tenant-id tenant_demo
.\.venv\Scripts\python.exe .\scripts\verify_work_task_snapshot_m2m.py --tenant-id tenant_demo
```

第二条命令会复用幂等沙箱任务，验证 Run/快照摘要、M2M Trace、无 Secret 持久化和 PostgreSQL 只追加触发器。

For a controlled end-to-end test only, set `CASDOOR_TEST_ADMIN_PASSWORD` in the current process and add `--full-oidc` to the verification command. The verifier does not print credentials or tokens.

The migration stops StaffDeck, takes a timestamped SQLite and environment snapshot under `D:\saas\backups`, copies all modelled data transactionally, verifies table counts, applies forced RLS, and only then switches the runtime configuration. To roll back the application connection while preserving PostgreSQL data:

```powershell
.\scripts\rollback-staffdeck-to-sqlite.ps1 `
  -BackupDirectory D:\saas\backups\staffdeck-sqlite-YYYYMMDD-HHMMSS
```

## Start StaffDeck

The source and dependencies are prepared separately:

```powershell
Set-Location D:\saas\third_party\StaffDeck
.\src\scripts\dev_up.ps1 --detach
curl.exe http://127.0.0.1:5173/api/health
```

Open `http://127.0.0.1:5173/workspace/gallery`. The local model API key is intentionally unset, so chat generation will remain unavailable until a compatible model endpoint is configured in `src\backend\.env`.

## Tenant isolation contract

The runtime and worker database roles have all of these properties:

- `NOSUPERUSER`
- `NOCREATEDB`
- `NOCREATEROLE`
- `NOINHERIT`
- `NOBYPASSRLS`

Every tenant business table enables and forces RLS. Request handlers must open a transaction and set tenant context from the validated server-side identity:

```sql
BEGIN;
SELECT set_config('app.tenant_id', :validated_tenant_id, true);
-- business queries
COMMIT;
```

Never derive `app.tenant_id` from an unverified request header or body field.

## Next integration phase

1. Provision named Casdoor organizations and non-default administrator accounts for each production tenant.
2. Assign real Casdoor users to exactly one StaffDeck business group and run joiner/mover/leaver acceptance tests.
3. Bind reviewed role-specific SOPs, knowledge bases and read-only tools to the seven production-role employees; the launch snapshot mechanism is active, but the current demo role employees intentionally have zero production capability bindings.
4. Run the worker as a separate, non-public service with the dedicated database role, then add workload-specific Casbin decisions at every tool invocation before enabling scheduled jobs.
5. Correlate human authorization decisions with agent/tool Trace records for a single end-to-end case timeline.
6. Terminate TLS at the local gateway, then set `OIDC_COOKIE_SECURE=true` before any non-local deployment.
