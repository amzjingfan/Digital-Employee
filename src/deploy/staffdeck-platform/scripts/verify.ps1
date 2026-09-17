$ErrorActionPreference = 'Stop'

$deployRoot = Split-Path $PSScriptRoot -Parent
$envPath = Join-Path $deployRoot '.env'
$composePath = Join-Path $deployRoot 'compose.yml'
$envValues = Get-Content -LiteralPath $envPath | ConvertFrom-StringData
$rancherBin = 'D:\Apps\Rancher Desktop\resources\resources\win32\bin'

if (Test-Path -LiteralPath $rancherBin) {
    $env:Path = "$rancherBin;$env:Path"
}

function Invoke-RuntimeSql {
    param([Parameter(Mandatory = $true)][string]$Sql)

    $result = $Sql | & docker compose --env-file $envPath -f $composePath exec -T postgres sh -c 'PGPASSWORD="$STAFFDECK_RUNTIME_PASSWORD" psql -qAt -v ON_ERROR_STOP=1 -U staffdeck_runtime -d staffdeck_app'
    if ($LASTEXITCODE -ne 0) {
        throw "Runtime SQL failed: $result"
    }
    return ($result -join "`n").Trim()
}

$health = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/api/health" -f $envValues.CASDOOR_PORT) -TimeoutSec 10
if ($null -eq $health) {
    throw 'Casdoor health endpoint returned no data.'
}

$tenantA = Invoke-RuntimeSql @'
BEGIN;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
SELECT payload FROM app.tenant_access_probes ORDER BY payload;
ROLLBACK;
'@

$tenantB = Invoke-RuntimeSql @'
BEGIN;
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
SELECT payload FROM app.tenant_access_probes ORDER BY payload;
ROLLBACK;
'@

$noTenant = Invoke-RuntimeSql 'SELECT payload FROM app.tenant_access_probes ORDER BY payload;'

if ($tenantA -ne 'tenant-a-only') {
    throw "Tenant A isolation failed. Received: $tenantA"
}
if ($tenantB -ne 'tenant-b-only') {
    throw "Tenant B isolation failed. Received: $tenantB"
}
if ($noTenant -ne '') {
    throw "Missing tenant context must return zero rows. Received: $noTenant"
}

$spoofSql = @'
BEGIN;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
INSERT INTO app.tenant_access_probes (tenant_id, payload)
VALUES ('22222222-2222-4222-8222-222222222222', 'must-be-denied');
ROLLBACK;
'@

$null = $spoofSql | & docker compose --env-file $envPath -f $composePath exec -T postgres sh -c 'PGPASSWORD="$STAFFDECK_RUNTIME_PASSWORD" psql -qAt -v ON_ERROR_STOP=1 -U staffdeck_runtime -d staffdeck_app' 2>&1
if ($LASTEXITCODE -eq 0) {
    throw 'Cross-tenant INSERT unexpectedly succeeded.'
}

Write-Host 'Casdoor health check passed.'
Write-Host 'PostgreSQL RLS read isolation passed for tenant A, tenant B, and missing context.'
Write-Host 'PostgreSQL RLS cross-tenant write denial passed.'
