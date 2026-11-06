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
    $pythonExe = (Get-Command python -ErrorAction Stop).Source
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
