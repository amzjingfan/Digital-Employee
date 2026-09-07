param(
    [string]$StaffDeckRoot = 'D:\saas\third_party\StaffDeck',
    [string]$BackupRoot = 'D:\saas\backups',
    [switch]$SkipDataMigration
)

$ErrorActionPreference = 'Stop'

$deployRoot = Split-Path $PSScriptRoot -Parent
$deployEnvPath = Join-Path $deployRoot '.env'
$composePath = Join-Path $deployRoot 'compose.yml'
$backendRoot = Join-Path $StaffDeckRoot 'backend'
$backendEnvPath = Join-Path $backendRoot '.env'
$frontendEnvPath = Join-Path $StaffDeckRoot 'frontend-enterprise\.env.local'
$sqlitePath = Join-Path $backendRoot 'skill_agent_loop.db'
$python = Join-Path $backendRoot '.venv\Scripts\python.exe'
$docker = 'D:\Apps\Rancher Desktop\resources\resources\win32\bin\docker.exe'
$m2mSecretDirectory = 'D:\saas\runtime\staffdeck-secrets'
$m2mSecretFile = Join-Path $m2mSecretDirectory 'agent-m2m.json'

function Set-EnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Key,
        [Parameter(Mandatory = $true)][string]$Value
    )
    $lines = [Collections.Generic.List[string]]::new()
    if (Test-Path -LiteralPath $Path) {
        $lines.AddRange([string[]](Get-Content -LiteralPath $Path))
    }
    $found = $false
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match ('^' + [Regex]::Escape($Key) + '=')) {
            $lines[$index] = "$Key=$Value"
            $found = $true
            break
        }
    }
    if (-not $found) { $lines.Add("$Key=$Value") }
    [IO.File]::WriteAllLines($Path, $lines, (New-Object Text.UTF8Encoding($false)))
}

$resolvedBackupRoot = [IO.Path]::GetFullPath($BackupRoot)
$allowedBackupRoot = [IO.Path]::GetFullPath('D:\saas\backups')
if (-not $resolvedBackupRoot.StartsWith($allowedBackupRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "BackupRoot must stay within $allowedBackupRoot"
}
foreach ($required in @($deployEnvPath, $backendEnvPath, $sqlitePath, $python, $docker)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing required path: $required" }
}

$deployEnv = Get-Content -LiteralPath $deployEnvPath -Raw | ConvertFrom-StringData
foreach ($key in @('POSTGRES_PORT', 'STAFFDECK_MIGRATOR_PASSWORD', 'STAFFDECK_RUNTIME_PASSWORD', 'STAFFDECK_OIDC_CLIENT_ID', 'STAFFDECK_OIDC_CLIENT_SECRET', 'STAFFDECK_CASDOOR_ORGANIZATION', 'STAFFDECK_CASDOOR_GROUP_PREFIX')) {
    if (-not $deployEnv[$key]) { throw "Missing $key in $deployEnvPath" }
}
$oidcOrganization = $deployEnv.STAFFDECK_CASDOOR_ORGANIZATION
$oidcGroupPrefix = $deployEnv.STAFFDECK_CASDOOR_GROUP_PREFIX
$tenantMapping = [ordered]@{}
$tenantMapping[$oidcOrganization] = 'tenant_demo'
$groupRoleMapping = [ordered]@{}
$groupRoleMapping["$oidcOrganization/$oidcGroupPrefix-operations-supervisor"] = 'operations_supervisor'
$groupRoleMapping["$oidcOrganization/$oidcGroupPrefix-after-sales"] = 'after_sales_specialist'
$groupRoleMapping["$oidcOrganization/$oidcGroupPrefix-listing-compliance"] = 'listing_compliance_specialist'
$groupRoleMapping["$oidcOrganization/$oidcGroupPrefix-logistics-exception"] = 'logistics_exception_specialist'
$groupRoleMapping["$oidcOrganization/$oidcGroupPrefix-advertising-inspection"] = 'advertising_inspection_specialist'
$groupRoleMapping["$oidcOrganization/$oidcGroupPrefix-designer"] = 'designer'
$groupRoleMapping["$oidcOrganization/$oidcGroupPrefix-procurement"] = 'procurement_specialist'

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDirectory = Join-Path $resolvedBackupRoot "staffdeck-sqlite-$timestamp"
New-Item -ItemType Directory -Path $backupDirectory | Out-Null

Write-Host 'Stopping StaffDeck for a consistent SQLite snapshot...'
& (Join-Path $StaffDeckRoot 'scripts\dev_down.ps1')
if ($LASTEXITCODE -ne 0) { throw 'StaffDeck stop failed.' }

try {
    Copy-Item -LiteralPath $sqlitePath -Destination (Join-Path $backupDirectory 'skill_agent_loop.db')
    foreach ($suffix in @('-wal', '-shm')) {
        $sidecar = "$sqlitePath$suffix"
        if (Test-Path -LiteralPath $sidecar) {
            Copy-Item -LiteralPath $sidecar -Destination (Join-Path $backupDirectory "skill_agent_loop.db$suffix")
        }
    }
    Copy-Item -LiteralPath $backendEnvPath -Destination (Join-Path $backupDirectory 'backend.env.before-postgresql')
    if (Test-Path -LiteralPath $frontendEnvPath) {
        Copy-Item -LiteralPath $frontendEnvPath -Destination (Join-Path $backupDirectory 'frontend.env.local.before-postgresql')
    }

    $migratorPassword = [Uri]::EscapeDataString($deployEnv.STAFFDECK_MIGRATOR_PASSWORD)
    $runtimePassword = [Uri]::EscapeDataString($deployEnv.STAFFDECK_RUNTIME_PASSWORD)
    $backupDb = (Join-Path $backupDirectory 'skill_agent_loop.db').Replace('\', '/')
    $env:STAFFDECK_SQLITE_URL = "sqlite:///$backupDb"
    $env:STAFFDECK_POSTGRES_MIGRATOR_URL = "postgresql+psycopg://staffdeck_migrator:$migratorPassword@127.0.0.1:$($deployEnv.POSTGRES_PORT)/staffdeck_app"

    $dataMigrationMarker = & $docker compose --env-file $deployEnvPath -f $composePath exec -T postgres sh -c 'PGPASSWORD="$STAFFDECK_MIGRATOR_PASSWORD" psql -At -U staffdeck_migrator -d staffdeck_app -c "SELECT 1 FROM staffdeck_schema_migrations WHERE migration_id = ''20260830_sqlite_to_postgresql_v1''"'
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect PostgreSQL migration state.' }
    $dataMigrationCommitted = @($dataMigrationMarker) -contains '1'

    if (-not $SkipDataMigration -and -not $dataMigrationCommitted) {
        Write-Host 'Copying SQLite business data to PostgreSQL in one transaction...'
        Push-Location $backendRoot
        try {
            & $python '.\scripts\migrate_sqlite_to_postgres.py' --apply
            if ($LASTEXITCODE -ne 0) { throw 'SQLite to PostgreSQL migration failed.' }
        } finally {
            Pop-Location
        }
    } else {
        Write-Host 'Skipping data copy because PostgreSQL already contains the committed initial migration.'
    }

    Write-Host 'Applying PostgreSQL grants, forced tenant RLS, and authorization audit schema...'
    foreach ($migrationFile in @(
        '20260830_postgresql_tenant_rls.sql',
        '20260830_authorization_decisions_v1.sql',
        '20260831_business_roles_v1.sql',
        '20260901_business_resource_approvals_v1.sql',
        '20260901_business_action_execution_v1.sql',
        '20260901_operations_reports_v1.sql',
        '20260901_work_tasks_v1.sql',
        '20260901_work_task_execution_v1.sql',
        '20260902_work_task_snapshots_m2m_v1.sql'
    )) {
        Get-Content -LiteralPath (Join-Path $backendRoot "migrations\$migrationFile") -Raw |
            & $docker compose --env-file $deployEnvPath -f $composePath exec -T postgres sh -c 'PGPASSWORD="$STAFFDECK_MIGRATOR_PASSWORD" psql -q -v ON_ERROR_STOP=1 -U staffdeck_migrator -d staffdeck_app'
        if ($LASTEXITCODE -ne 0) { throw "Database migration failed: $migrationFile" }
    }

    Set-EnvValue $backendEnvPath 'DATABASE_URL' "postgresql+psycopg://staffdeck_runtime:$runtimePassword@127.0.0.1:$($deployEnv.POSTGRES_PORT)/staffdeck_app"
    Set-EnvValue $backendEnvPath 'DATABASE_AUTO_CREATE' 'false'
    Set-EnvValue $backendEnvPath 'DATABASE_SEED_DEMO_DATA' 'false'
    Set-EnvValue $backendEnvPath 'DATABASE_RLS_ENABLED' 'true'
    Set-EnvValue $backendEnvPath 'MOCK_API_ENABLED' 'false'
    Set-EnvValue $backendEnvPath 'CASBIN_ENABLED' 'true'
    Set-EnvValue $backendEnvPath 'PUBLIC_API_ENABLED' 'false'
    Set-EnvValue $backendEnvPath 'STAFFDECK_ROLE' 'api'
    Set-EnvValue $backendEnvPath 'BUSINESS_EXECUTION_ENABLED' 'true'
    Set-EnvValue $backendEnvPath 'BUSINESS_EXECUTION_MODE' 'sandbox'
    Set-EnvValue $backendEnvPath 'BUSINESS_EXECUTION_TENANT_IDS' 'tenant_demo'
    Set-EnvValue $backendEnvPath 'WORK_TASK_EXECUTION_ENABLED' 'true'
    Set-EnvValue $backendEnvPath 'WORK_TASK_EXECUTION_MODE' 'sandbox'
    Set-EnvValue $backendEnvPath 'WORK_TASK_EXECUTION_TENANT_IDS' 'tenant_demo'
    Set-EnvValue $backendEnvPath 'WORK_TASK_M2M_SECRET_FILE' $m2mSecretFile
    Set-EnvValue $backendEnvPath 'WORK_TASK_M2M_TIMEOUT_SECONDS' '10'
    Set-EnvValue $backendEnvPath 'OIDC_ENABLED' 'true'
    Set-EnvValue $backendEnvPath 'OIDC_ISSUER' 'http://localhost:18000'
    Set-EnvValue $backendEnvPath 'OIDC_AUTHORIZATION_ENDPOINT' 'http://localhost:18000/login/oauth/authorize'
    Set-EnvValue $backendEnvPath 'OIDC_TOKEN_ENDPOINT' 'http://localhost:18000/api/login/oauth/access_token'
    Set-EnvValue $backendEnvPath 'OIDC_JWKS_URI' 'http://localhost:18000/.well-known/jwks'
    Set-EnvValue $backendEnvPath 'OIDC_END_SESSION_ENDPOINT' 'http://localhost:18000/api/logout'
    Set-EnvValue $backendEnvPath 'OIDC_CLIENT_ID' $deployEnv.STAFFDECK_OIDC_CLIENT_ID
    Set-EnvValue $backendEnvPath 'OIDC_CLIENT_SECRET' $deployEnv.STAFFDECK_OIDC_CLIENT_SECRET
    Set-EnvValue $backendEnvPath 'OIDC_REDIRECT_URI' 'http://127.0.0.1:5173/api/auth/oidc/callback'
    Set-EnvValue $backendEnvPath 'OIDC_SCOPES' 'openid profile email'
    Set-EnvValue $backendEnvPath 'OIDC_TENANT_MAPPING_JSON' ($tenantMapping | ConvertTo-Json -Compress)
    Set-EnvValue $backendEnvPath 'OIDC_GROUP_CLAIM' 'groups'
    Set-EnvValue $backendEnvPath 'OIDC_GROUP_ROLE_MAPPING_JSON' ($groupRoleMapping | ConvertTo-Json -Compress)
    Set-EnvValue $backendEnvPath 'OIDC_REQUIRE_MAPPED_GROUP' 'true'
    Set-EnvValue $backendEnvPath 'OIDC_SESSION_TTL_SECONDS' '28800'
    Set-EnvValue $backendEnvPath 'OIDC_COOKIE_SECURE' 'false'
    Set-EnvValue $frontendEnvPath 'VITE_OIDC_ENABLED' 'true'

    Write-Host 'Provisioning seven role digital employees and isolated Casdoor M2M identities...'
    New-Item -ItemType Directory -Path $m2mSecretDirectory -Force | Out-Null
    Push-Location $backendRoot
    try {
        & $python '.\scripts\provision_crossborder_role_agents.py' --tenant-id tenant_demo
        if ($LASTEXITCODE -ne 0) { throw 'Cross-border role-agent provisioning failed.' }
        & $python (Join-Path $PSScriptRoot 'provision-agent-m2m.py') `
            --env-file $deployEnvPath `
            --secret-file $m2mSecretFile `
            --tenant-id tenant_demo
        if ($LASTEXITCODE -ne 0) { throw 'Casdoor M2M service-identity provisioning failed.' }
    } finally {
        Pop-Location
    }

    Write-Host 'Starting StaffDeck on PostgreSQL...'
    & (Join-Path $StaffDeckRoot 'scripts\dev_up.ps1') --detach
    if ($LASTEXITCODE -ne 0) { throw 'StaffDeck restart failed.' }
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:5173/api/health' -TimeoutSec 30
    if ($health.status -ne 'ok') { throw 'StaffDeck health check failed after cutover.' }
    Write-Host "Cutover complete. Rollback snapshot: $backupDirectory"
} catch {
    Write-Warning 'Cutover did not complete. Restoring the original SQLite configuration.'
    $savedEnv = Join-Path $backupDirectory 'backend.env.before-postgresql'
    if (Test-Path -LiteralPath $savedEnv) {
        Copy-Item -LiteralPath $savedEnv -Destination $backendEnvPath -Force
    }
    & (Join-Path $StaffDeckRoot 'scripts\dev_up.ps1') --detach
    throw
} finally {
    Remove-Item Env:STAFFDECK_SQLITE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:STAFFDECK_POSTGRES_MIGRATOR_URL -ErrorAction SilentlyContinue
}
