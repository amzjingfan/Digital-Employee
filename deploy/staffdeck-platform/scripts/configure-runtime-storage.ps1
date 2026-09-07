$ErrorActionPreference = 'Stop'

$source = Join-Path $env:LOCALAPPDATA 'rancher-desktop'
$destination = 'D:\saas\runtime\rancher-desktop'

New-Item -ItemType Directory -Path $destination -Force | Out-Null

if (Test-Path -LiteralPath $source) {
    $existing = Get-Item -LiteralPath $source -Force
    $targets = @($existing.Target | ForEach-Object { [string]$_ })
    $alreadyConfigured = $existing.LinkType -eq 'Junction' -and
        $targets -contains $destination

    if (-not $alreadyConfigured) {
        throw "Rancher Desktop data path already exists and is not the expected junction: $source"
    }
} else {
    New-Item -ItemType Junction -Path $source -Target $destination | Out-Null
}

$junction = Get-Item -LiteralPath $source -Force
Write-Host 'Rancher Desktop storage redirection is configured.'
Write-Host "Junction: $($junction.FullName)"
Write-Host "Target:   $destination"

