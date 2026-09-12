[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$OldRepository,
    [string]$ArtifactRoot = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) '.dev\legacy-backend-suite')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$oldBackend = Join-Path $OldRepository 'source\backend'
New-Item -ItemType Directory -Force -Path $ArtifactRoot | Out-Null
$dataDir = Join-Path $ArtifactRoot 'data'
$tempDir = Join-Path $ArtifactRoot 'temp'
New-Item -ItemType Directory -Force -Path $dataDir, $tempDir | Out-Null
$databasePath = (Join-Path $ArtifactRoot 'pytest-old.db').Replace('\', '/')
$logPath = Join-Path $ArtifactRoot 'pytest-old.log'
$junitPath = Join-Path $ArtifactRoot 'pytest-old.xml'
$beforePath = Join-Path $ArtifactRoot 'old-status-before.txt'
$afterPath = Join-Path $ArtifactRoot 'old-status-after.txt'

(& git -c "safe.directory=$OldRepository" -C $OldRepository status --porcelain=v1 -uall) |
    Set-Content -LiteralPath $beforePath -Encoding utf8
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:NO_PROXY = 'localhost,127.0.0.1'
$env:no_proxy = 'localhost,127.0.0.1'
$env:ULTRARAG_DOTENV = Join-Path $ArtifactRoot 'nonexistent-test.env'
$env:DATABASE_URL = "sqlite:///$databasePath"
$env:ULTRARAG_DATA_DIR = $dataDir

Push-Location $oldBackend
try {
    & '.\.venv\Scripts\python.exe' -m pytest -c pyproject.toml tests `
        --basetemp $tempDir --junitxml $junitPath -p no:cacheprovider `
        -q --tb=short --durations=20 *> $logPath
    $testExit = $LASTEXITCODE
}
finally {
    Pop-Location
}

(& git -c "safe.directory=$OldRepository" -C $OldRepository status --porcelain=v1 -uall) |
    Set-Content -LiteralPath $afterPath -Encoding utf8
$before = Get-Content -LiteralPath $beforePath -Raw
$after = Get-Content -LiteralPath $afterPath -Raw
Get-Content -LiteralPath $logPath -Tail 80
"PYTEST_OLD_EXIT=$testExit"
"OLD_STATUS_UNCHANGED=$($before -ceq $after)"
"PYTEST_OLD_LOG=$logPath"
"PYTEST_OLD_JUNIT=$junitPath"
exit $testExit
