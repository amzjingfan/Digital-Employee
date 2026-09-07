$ErrorActionPreference = 'Stop'

$deployRoot = Split-Path $PSScriptRoot -Parent
$examplePath = Join-Path $deployRoot '.env.example'
$envPath = Join-Path $deployRoot '.env'

function New-Secret {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToHexString($bytes).ToLowerInvariant()
}

if (-not (Test-Path -LiteralPath $examplePath)) {
    throw "Missing environment template: $examplePath"
}

if (-not (Test-Path -LiteralPath $envPath)) {
    Copy-Item -LiteralPath $examplePath -Destination $envPath
    $content = Get-Content -LiteralPath $envPath -Raw
    $replacements = @{
        'CHANGE_ME_POSTGRES_ADMIN' = New-Secret
        'CHANGE_ME_CASDOOR_DB' = New-Secret
        'CHANGE_ME_STAFFDECK_MIGRATOR' = New-Secret
        'CHANGE_ME_STAFFDECK_RUNTIME' = New-Secret
        'CHANGE_ME_STAFFDECK_WORKER' = New-Secret
        'CHANGE_ME_STAFFDECK_OIDC_CLIENT_ID' = (New-Secret).Substring(0, 24)
        'CHANGE_ME_STAFFDECK_OIDC_CLIENT_SECRET' = New-Secret
    }

    foreach ($entry in $replacements.GetEnumerator()) {
        $content = $content.Replace($entry.Key, $entry.Value)
    }

    [IO.File]::WriteAllText($envPath, $content, (New-Object Text.UTF8Encoding($false)))
    Write-Host "Created $envPath with random local-development secrets."
} else {
    Write-Host "Keeping existing $envPath."
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Warning 'A Docker-compatible CLI is not available yet. Install and start Rancher Desktop before running up.ps1.'
}
