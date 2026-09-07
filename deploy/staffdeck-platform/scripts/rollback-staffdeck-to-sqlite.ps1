param(
    [Parameter(Mandatory = $true)][string]$BackupDirectory,
    [string]$StaffDeckRoot = 'D:\saas\third_party\StaffDeck'
)

$ErrorActionPreference = 'Stop'
$resolvedBackup = [IO.Path]::GetFullPath($BackupDirectory)
$allowedRoot = [IO.Path]::GetFullPath('D:\saas\backups')
if (-not $resolvedBackup.StartsWith($allowedRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "BackupDirectory must stay within $allowedRoot"
}
$savedEnv = Join-Path $resolvedBackup 'backend.env.before-postgresql'
if (-not (Test-Path -LiteralPath $savedEnv)) { throw "Missing rollback configuration: $savedEnv" }

& (Join-Path $StaffDeckRoot 'scripts\dev_down.ps1')
if ($LASTEXITCODE -ne 0) { throw 'StaffDeck stop failed.' }
Copy-Item -LiteralPath $savedEnv -Destination (Join-Path $StaffDeckRoot 'backend\.env') -Force
& (Join-Path $StaffDeckRoot 'scripts\dev_up.ps1') --detach
if ($LASTEXITCODE -ne 0) { throw 'StaffDeck restart failed.' }
Write-Host 'StaffDeck is running on the preserved SQLite configuration. PostgreSQL data was left intact.'
