$ErrorActionPreference = 'Stop'

$deployRoot = Split-Path $PSScriptRoot -Parent
$envPath = Join-Path $deployRoot '.env'
$composePath = Join-Path $deployRoot 'compose.yml'
$rancherBin = 'D:\Apps\Rancher Desktop\resources\resources\win32\bin'

if (Test-Path -LiteralPath $rancherBin) {
    $env:Path = "$rancherBin;$env:Path"
}

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$docker = if ($dockerCommand) {
    $dockerCommand.Source
} else {
    Join-Path $rancherBin 'docker.exe'
}

if (-not (Test-Path -LiteralPath $docker)) {
    throw 'Docker-compatible CLI not found. Install and start Rancher Desktop first.'
}

if (-not (Test-Path -LiteralPath $envPath)) {
    & (Join-Path $PSScriptRoot 'setup.ps1')
}

& $docker compose --env-file $envPath -f $composePath up -d
if ($LASTEXITCODE -ne 0) {
    throw 'docker compose up failed.'
}

& $docker compose --env-file $envPath -f $composePath ps
