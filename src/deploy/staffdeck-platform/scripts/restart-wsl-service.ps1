$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$resultPath = 'D:\saas\runtime\wsl-service-restart-result.json'

if (-not $isAdmin) {
    $powershell = (Get-Process -Id $PID).Path
    $argument = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $PSCommandPath
    $process = Start-Process -FilePath $powershell -Verb RunAs -ArgumentList $argument -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Elevated WSL service restart failed with exit code $($process.ExitCode)."
    }
    Get-Content -LiteralPath $resultPath
    exit 0
}

$resultDirectory = Split-Path $resultPath -Parent
New-Item -ItemType Directory -Path $resultDirectory -Force | Out-Null

Get-Process -Name 'Rancher Desktop' -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process -Name 'wsl' -ErrorAction SilentlyContinue | Stop-Process -Force
Restart-Service -Name WslService -Force
$service = Get-Service -Name WslService

[pscustomobject]@{
    RestartedAt = (Get-Date).ToString('o')
    Service = $service.Name
    Status = [string]$service.Status
} | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding utf8

