$ErrorActionPreference = 'Stop'

$deployRoot = Split-Path $PSScriptRoot -Parent
$envPath = Join-Path $deployRoot '.env'
$composePath = Join-Path $deployRoot 'compose.yml'
$rancherBin = 'D:\Apps\Rancher Desktop\resources\resources\win32\bin'

if (Test-Path -LiteralPath $rancherBin) {
    $env:Path = "$rancherBin;$env:Path"
}

& docker compose --env-file $envPath -f $composePath down
if ($LASTEXITCODE -ne 0) {
    throw 'docker compose down failed.'
}
