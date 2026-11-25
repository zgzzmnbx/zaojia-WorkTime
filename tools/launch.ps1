param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$url = 'http://127.0.0.1:8791'
$health = $null
try { $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2 } catch {}
if ($health -and $health.app -ne 'expert-hours-review') { throw 'Port 8791 is occupied by another application.' }
if (-not $health) {
    if (Get-NetTCPConnection -LocalPort 8791 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8791 is occupied.' }
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'dist\index.html'))) { throw 'Run npm install and npm run build first.' }
    $logs = Join-Path $projectRoot 'Codex-Temp'
    New-Item -ItemType Directory -Force -Path $logs | Out-Null
    # Explorer does not inherit the extra PATH supplied to Codex terminals.
    # WindowsApps cannot reliably be enumerated; use registered package paths.
    $candidates = @((Join-Path $projectRoot '.venv\Scripts\python.exe'))
    $systemPython = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if ($systemPython -and $systemPython -notlike '*\Microsoft\WindowsApps\python.exe') { $candidates += $systemPython }
    $nodeExe = (Get-Command node -ErrorAction SilentlyContinue).Source
    if ($nodeExe) { $candidates += Join-Path (Split-Path $nodeExe -Parent) '..\..\python\python.exe' }
    $packages = @(Get-AppxPackage -Name 'OpenAI.CodexPrimaryRuntime*' -ErrorAction SilentlyContinue | Sort-Object Version -Descending)
    foreach ($package in $packages) {
        if ($package.InstallLocation) { $candidates += Join-Path $package.InstallLocation 'dependencies\python\python.exe' }
    }
    $pythonLauncher = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
    if ($pythonLauncher) {
        try {
            $located = & $pythonLauncher -3 -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $located) { $candidates += [string]$located }
        } catch {}
    }
    $pythonExe = $null
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        try {
            & $candidate -c 'import sys, sqlite3; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { $pythonExe = $candidate; break }
        } catch {}
    }
    if (-not $pythonExe) { throw 'No working Python 3.10+ runtime found. Install Python or repair the installed Codex runtime.' }
    $process = Start-Process -FilePath $pythonExe -ArgumentList '-X','utf8','server.py' -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'server.stdout.log') -RedirectStandardError (Join-Path $logs 'server.stderr.log')
    $process.Id | Set-Content -LiteralPath (Join-Path $logs 'server.pid')
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 300
        try { $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 1; break } catch {}
    }
    if (-not $health -or $health.app -ne 'expert-hours-review') { throw 'Startup failed. See Codex-Temp/server.stderr.log.' }
}
if (-not $NoBrowser) { Start-Process "$url/" }
Write-Output "$url/"
