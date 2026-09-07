$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    $powershell = (Get-Process -Id $PID).Path
    $argument = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $PSCommandPath
    Start-Process -FilePath $powershell -Verb RunAs -ArgumentList $argument
    Write-Host 'Administrator installation was opened in a separate window.'
    exit 0
}

$installer = 'D:\saas\third_party_archives\Rancher.Desktop.Setup.1.24.0.msi'
$expectedHash = '5FC4E795A1C3BF72A2DAC9144D55DAAB181F30D1A3049D96A4C025985769960B'
$installDirectory = 'D:\Apps\Rancher Desktop'
$installerTemp = 'D:\saas\third_party_archives\rancher-msi-temp'
$installerLog = 'D:\saas\third_party_archives\rancher-desktop-install.log'

if (-not (Test-Path -LiteralPath $installer)) {
    throw "Rancher Desktop installer is missing: $installer"
}

$actualHash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash
if ($actualHash -ne $expectedHash) {
    throw "Rancher Desktop installer hash mismatch. Expected $expectedHash, received $actualHash"
}

$wslStatus = & wsl.exe --status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installing Windows Subsystem for Linux. A restart may be required.'
    & wsl.exe --install --no-distribution
    if ($LASTEXITCODE -ne 0) {
        throw 'WSL installation failed. Review the Windows message above.'
    }
}

$uninstallPaths = @(
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
    'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$installed = Get-ItemProperty -Path $uninstallPaths -ErrorAction SilentlyContinue |
    Where-Object DisplayName -Like 'Rancher Desktop*' |
    Select-Object -First 1

if (-not $installed) {
    New-Item -ItemType Directory -Path $installDirectory -Force | Out-Null
    New-Item -ItemType Directory -Path $installerTemp -Force | Out-Null
    $env:TEMP = $installerTemp
    $env:TMP = $installerTemp

    $arguments = '/i "{0}" APPLICATIONFOLDER="{1}" /qn /norestart /L*v "{2}"' -f `
        $installer, $installDirectory, $installerLog
    $startArguments = @{
        FilePath = 'msiexec.exe'
        ArgumentList = $arguments
        Wait = $true
        PassThru = $true
    }
    $process = Start-Process @startArguments
    if ($process.ExitCode -notin @(0, 3010)) {
        throw "Rancher Desktop installation failed with exit code $($process.ExitCode)."
    }
}

Write-Host 'Rancher Desktop is installed. Restart Windows if WSL requested it.'
Write-Host "Application directory: $installDirectory"
Write-Host 'After restart, launch Rancher Desktop and select the Moby container engine.'
