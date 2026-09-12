[CmdletBinding()]
param(
    [string]$NewRepo = 'E:\develop\数字员工\joukir',
    [string]$OldBackend = 'E:\develop\数字员工\joukir-enterprise\source\backend',
    [string]$RuntimeRoot = 'E:\develop\数字员工\joukir-runtime'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-ListenerPid {
    $listeners = @(
        Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
    if ($listeners.Count -eq 0) {
        return $null
    }
    if ($listeners.Count -ne 1) {
        throw "Expected one listener on port 5173, found $($listeners.Count)"
    }
    return [int]$listeners[0]
}

function Get-CimProcess([int]$ProcessId) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId"
    if ($null -eq $process) {
        throw "Process $ProcessId is missing"
    }
    return $process
}

function Test-SamePath([string]$Actual, [string]$Expected) {
    if ([string]::IsNullOrWhiteSpace($Actual) -or [string]::IsNullOrWhiteSpace($Expected)) {
        return $false
    }
    try {
        $actualFullPath = [IO.Path]::GetFullPath($Actual).TrimEnd('\')
        $expectedFullPath = [IO.Path]::GetFullPath($Expected).TrimEnd('\')
    }
    catch {
        return $false
    }
    return [string]::Equals(
        $actualFullPath,
        $expectedFullPath,
        [StringComparison]::OrdinalIgnoreCase
    )
}

function Assert-ExactWebCommand([object]$Process, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace([string]$Process.ExecutablePath)) {
        throw "$Label has no executable path"
    }
    if ([string]::IsNullOrWhiteSpace([string]$Process.CommandLine)) {
        throw "$Label has no command line"
    }

    $executablePattern = [Regex]::Escape([string]$Process.ExecutablePath)
    $pattern = ('^\s*(?:"{0}"|{0})\s+-m\s+uvicorn\s+single_port_app:app\s+' +
        '--host\s+127\.0\.0\.1\s+--port\s+5173\s+--no-access-log\s*$') -f $executablePattern
    if (-not [Regex]::IsMatch(
        [string]$Process.CommandLine,
        $pattern,
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )) {
        throw "$Label command is not the exact single-port uvicorn command"
    }
}

function Get-VerifiedWebIdentity {
    param(
        [Parameter(Mandatory)]
        [string]$Backend,
        [int]$ExpectedRootPid = 0,
        [int]$ExpectedListenerPid = 0
    )

    $listenerPid = Get-ListenerPid
    if ($null -eq $listenerPid) {
        throw 'The Web listener is missing'
    }
    if ($ExpectedListenerPid -gt 0 -and $listenerPid -ne $ExpectedListenerPid) {
        throw "Listener PID changed from $ExpectedListenerPid to $listenerPid"
    }

    $listener = Get-CimProcess $listenerPid
    Assert-ExactWebCommand $listener 'Listener'
    $rootPid = [int]$listener.ParentProcessId
    if ($ExpectedRootPid -gt 0 -and $rootPid -ne $ExpectedRootPid) {
        throw "Listener parent PID changed from $ExpectedRootPid to $rootPid"
    }

    $root = Get-CimProcess $rootPid
    $expectedLauncher = Join-Path $Backend '.venv\Scripts\python.exe'
    if (-not (Test-SamePath ([string]$root.ExecutablePath) $expectedLauncher)) {
        throw 'Web launcher executable path does not match the expected virtual environment'
    }
    Assert-ExactWebCommand $root 'Web launcher'

    return [pscustomobject]@{
        RootPid = [int]$root.ProcessId
        ListenerPid = [int]$listener.ProcessId
    }
}

function Stop-VerifiedWebTree {
    param(
        [Parameter(Mandatory)]
        [string]$Backend,
        [Parameter(Mandatory)]
        [int]$RootPid,
        [Parameter(Mandatory)]
        [int]$ListenerPid
    )

    # Re-read every identity field directly before the destructive operation.
    $confirmed = Get-VerifiedWebIdentity `
        -Backend $Backend `
        -ExpectedRootPid $RootPid `
        -ExpectedListenerPid $ListenerPid
    & taskkill.exe /PID $confirmed.RootPid /T /F *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to stop verified process tree $($confirmed.RootPid)"
    }
}

function Stop-StartedWeb([int]$RootPid, [string]$Backend) {
    $root = Get-CimInstance Win32_Process -Filter "ProcessId = $RootPid" -ErrorAction SilentlyContinue
    $listenerPid = Get-ListenerPid

    if ($null -ne $root) {
        $expectedLauncher = Join-Path $Backend '.venv\Scripts\python.exe'
        if (-not (Test-SamePath ([string]$root.ExecutablePath) $expectedLauncher)) {
            throw "Cleanup refused: launcher $RootPid no longer has the expected executable path"
        }
        Assert-ExactWebCommand $root 'Cleanup launcher'

        if ($null -ne $listenerPid) {
            $listener = Get-CimProcess $listenerPid
            if ([int]$listener.ParentProcessId -eq $RootPid) {
                $null = Get-VerifiedWebIdentity `
                    -Backend $Backend `
                    -ExpectedRootPid $RootPid `
                    -ExpectedListenerPid $listenerPid
            }
        }

        # The launcher may not have bound the port yet. Revalidate it anyway.
        $root = Get-CimProcess $RootPid
        if (-not (Test-SamePath ([string]$root.ExecutablePath) $expectedLauncher)) {
            throw "Cleanup refused: launcher $RootPid identity changed"
        }
        Assert-ExactWebCommand $root 'Cleanup launcher'
        & taskkill.exe /PID $RootPid /T /F *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to clean up new Web process tree $RootPid"
        }
        return
    }

    if ($null -eq $listenerPid) {
        return
    }

    # The launcher can exit while its uvicorn child still owns the port.
    $listener = Get-CimProcess $listenerPid
    if ([int]$listener.ParentProcessId -ne $RootPid) {
        throw "Cleanup refused: listener $listenerPid is not descended from launcher $RootPid"
    }
    Assert-ExactWebCommand $listener 'Orphaned cleanup listener'
    $listener = Get-CimProcess $listenerPid
    if ([int]$listener.ParentProcessId -ne $RootPid) {
        throw "Cleanup refused: listener $listenerPid parent identity changed"
    }
    Assert-ExactWebCommand $listener 'Orphaned cleanup listener'
    & taskkill.exe /PID $listenerPid /T /F *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to clean up orphaned Web listener $listenerPid"
    }
}

function Wait-PortFree([int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        if ($null -eq (Get-ListenerPid)) {
            return
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    throw 'Port 5173 did not become free'
}

function Start-Web([string]$Backend, [string]$LogPrefix) {
    $logDir = Join-Path $RuntimeRoot 'logs'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $stdout = Join-Path $logDir "$LogPrefix-$stamp.log"
    $stderr = Join-Path $logDir "$LogPrefix-$stamp.err.log"
    $env:ULTRARAG_DOTENV = Join-Path $Backend '.env'
    $env:ULTRARAG_DATA_DIR = Join-Path $RuntimeRoot 'data'
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:NO_PROXY = 'localhost,127.0.0.1'
    $env:no_proxy = 'localhost,127.0.0.1'
    $executable = Join-Path $Backend '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $executable)) {
        throw "Python launcher is missing under $Backend"
    }
    $process = Start-Process `
        -FilePath $executable `
        -ArgumentList @(
            '-m', 'uvicorn', 'single_port_app:app',
            '--host', '127.0.0.1', '--port', '5173', '--no-access-log'
        ) `
        -WorkingDirectory $Backend `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -PassThru
    return [pscustomobject]@{
        Process = $process
        Stdout = $stdout
        Stderr = $stderr
    }
}

function Wait-Healthy([int]$RootPid, [string]$ExpectedBackend, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    $lastError = $null
    do {
        if (-not (Get-Process -Id $RootPid -ErrorAction SilentlyContinue)) {
            throw "Web launcher $RootPid exited before becoming healthy"
        }
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:5173/api/health' -TimeoutSec 3
            if ($health.status -eq 'ok' -and $health.app -eq '九骥 Joukir') {
                $identity = Get-VerifiedWebIdentity `
                    -Backend $ExpectedBackend `
                    -ExpectedRootPid $RootPid
                return [pscustomobject]@{
                    RootPid = $RootPid
                    ListenerPid = $identity.ListenerPid
                    Status = [string]$health.status
                    App = [string]$health.app
                }
            }
        }
        catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Web health check timed out: $lastError"
}

$newBackend = Join-Path $NewRepo 'backend'
$oldRootPid = $null
$oldListenerPid = $null
$oldStopInitiated = $false
$newRun = $null
try {
    $oldIdentity = Get-VerifiedWebIdentity -Backend $OldBackend
    $oldRootPid = [int]$oldIdentity.RootPid
    $oldListenerPid = [int]$oldIdentity.ListenerPid

    $oldStopInitiated = $true
    Stop-VerifiedWebTree `
        -Backend $OldBackend `
        -RootPid $oldRootPid `
        -ListenerPid $oldListenerPid
    Wait-PortFree 20

    $newRun = Start-Web $newBackend 'web-joukir'
    $newHealth = Wait-Healthy ([int]$newRun.Process.Id) $newBackend 60
    $pidFile = Join-Path $NewRepo '.dev\local-web.pid'
    Set-Content -LiteralPath $pidFile -Value ([string]$newHealth.RootPid) -Encoding ascii

    [pscustomobject]@{
        Ok = $true
        OldRootPid = $oldRootPid
        OldListenerPid = $oldListenerPid
        NewRootPid = $newHealth.RootPid
        NewListenerPid = $newHealth.ListenerPid
        HealthStatus = $newHealth.Status
        App = $newHealth.App
        StdoutLog = $newRun.Stdout
        StderrLog = $newRun.Stderr
        RollbackPerformed = $false
    } | ConvertTo-Json -Compress
}
catch {
    $cutoverError = $_.Exception.Message
    $cleanupError = $null
    $rollbackError = $null
    $rollbackPerformed = $false
    $recoveryFailed = $false
    $recoveryState = 'NotRequired'

    if ($null -ne $newRun) {
        try {
            Stop-StartedWeb ([int]$newRun.Process.Id) $newBackend
        }
        catch {
            $cleanupError = $_.Exception.Message
        }
        try {
            Wait-PortFree 20
        }
        catch {
            $portCleanupError = $_.Exception.Message
            $cleanupError = if ($null -eq $cleanupError) {
                $portCleanupError
            }
            else {
                "$cleanupError; $portCleanupError"
            }
        }
    }

    if ($oldStopInitiated) {
        $remainingListenerPid = $null
        try {
            $remainingListenerPid = Get-ListenerPid
        }
        catch {
            $rollbackError = "Cannot inspect port 5173 during recovery: $($_.Exception.Message)"
        }

        if ($null -eq $rollbackError -and $null -ne $remainingListenerPid) {
            try {
                $null = Get-VerifiedWebIdentity `
                    -Backend $OldBackend `
                    -ExpectedRootPid $oldRootPid `
                    -ExpectedListenerPid $oldListenerPid
                $recoveryState = 'OldServiceStillRunning'
            }
            catch {
                $rollbackError = "Port 5173 remains occupied and the old service cannot be verified: $($_.Exception.Message)"
            }
        }
        elseif ($null -eq $rollbackError) {
            try {
                $rollback = Start-Web $OldBackend 'web-rollback'
                $rollbackHealth = Wait-Healthy ([int]$rollback.Process.Id) $OldBackend 60
                $rollbackPerformed = $true
                $recoveryState = 'RollbackHealthy'
            }
            catch {
                $rollbackError = $_.Exception.Message
            }
        }

        if ($recoveryState -notin @('OldServiceStillRunning', 'RollbackHealthy')) {
            $recoveryFailed = $true
            $recoveryState = 'Failed'
        }
    }

    [pscustomobject]@{
        Ok = $false
        Error = $cutoverError
        CleanupError = $cleanupError
        RollbackPerformed = $rollbackPerformed
        RollbackError = $rollbackError
        RecoveryFailed = $recoveryFailed
        RecoveryState = $recoveryState
        RollbackRootPid = if ($rollbackPerformed) { $rollbackHealth.RootPid } else { $null }
        RollbackListenerPid = if ($rollbackPerformed) { $rollbackHealth.ListenerPid } else { $null }
        RollbackHealthStatus = if ($rollbackPerformed) { $rollbackHealth.Status } else { $null }
    } | ConvertTo-Json -Compress
    exit 1
}
