# run-backend.ps1 - Minder backend (FastAPI web server) with auto-restart.
# Usage:  .\run-backend.ps1            -> binds http://127.0.0.1:8080
#         .\run-backend.ps1 -Port 9000 -> custom port
# Loads .env on each (re)start. Ctrl+C to stop.

param(
    [string]$AppHost = '127.0.0.1',
    [int]$Port = 8080
)

$ErrorActionPreference = 'Stop'

# cd to this script's own folder (handles the [ ] wildcard path safely).
Set-Location -LiteralPath $PSScriptRoot

# Load .env into the process environment. The app reads os.environ directly
# (e.g. DATABASE_URL, MINDER_MODEL) and does NOT call load_dotenv itself, so we
# must populate the environment here before launching.
function Import-DotEnv {
    $envFile = Join-Path $PSScriptRoot '.env'
    if (Test-Path -LiteralPath $envFile) {
        $loaded = 0
        Get-Content -LiteralPath $envFile | ForEach-Object {
            $line = $_.Trim()
            if ($line -eq '' -or $line.StartsWith('#')) { return }
            $idx = $line.IndexOf('=')
            if ($idx -lt 1) { return }                       # no '=' or empty key -> skip
            $key = $line.Substring(0, $idx).Trim()
            $val = $line.Substring($idx + 1).Trim()          # split on FIRST '=' (values may contain '=')
            if ($val.Length -ge 2 -and (
                ($val.StartsWith('"') -and $val.EndsWith('"')) -or
                ($val.StartsWith("'") -and $val.EndsWith("'")))) {
                $val = $val.Substring(1, $val.Length - 2)     # strip surrounding quotes
            }
            Set-Item -Path "Env:$key" -Value $val
            $loaded++
        }
        Write-Host "[run-backend] loaded .env ($loaded vars)" -ForegroundColor DarkGray
    } else {
        Write-Host "[run-backend] WARNING: .env not found at $envFile" -ForegroundColor Yellow
    }
}

Write-Host "Minder backend -> http://${AppHost}:${Port}  (Ctrl+C to stop)" -ForegroundColor Cyan

# Preflight the database. minder/web/server.py calls init_schema() unguarded in the
# FastAPI lifespan (unlike Redis, which degrades gracefully), so an unreachable DB
# kills the server thread -> serve.py exits 1 -> the loop below restarts every 2s
# forever. Without this check the only symptom is a silent restart loop, which says
# nothing about the actual cause. Fail once, loudly, with the fix.
function Test-Database {
    $dsn = $env:DATABASE_URL
    if (-not $dsn) {
        Write-Host "[run-backend] DATABASE_URL is not set (is .env present?)" -ForegroundColor Red
        return $false
    }
    # postgresql://user:pass@host:port/db -> host, port (port optional, defaults 5432)
    if ($dsn -notmatch '@([^:/@]+)(?::(\d+))?/') {
        Write-Host "[run-backend] could not parse host from DATABASE_URL; skipping preflight" -ForegroundColor Yellow
        return $true   # don't block on a DSN shape we don't recognise
    }
    $dbHost = $Matches[1]
    $dbPort = if ($Matches[2]) { [int]$Matches[2] } else { 5432 }

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $ok = $client.ConnectAsync($dbHost, $dbPort).Wait(3000)
        if ($ok -and $client.Connected) { return $true }
    } catch { }
    finally { $client.Dispose() }

    Write-Host ""
    Write-Host "[run-backend] cannot reach the database at ${dbHost}:${dbPort}" -ForegroundColor Red
    Write-Host "[run-backend] the backend cannot start without it. Try:" -ForegroundColor Yellow
    Write-Host "                docker start atria-pg" -ForegroundColor Cyan
    Write-Host "[run-backend] or bring up the whole data tier: _local\dev-up.ps1" -ForegroundColor Yellow
    return $false
}

# Free the target port if a stale instance still holds it, so the app always
# binds $Port. Otherwise find_available_port silently bumps to $Port+1 and the
# frontend (which reaches the backend via the :$Port Vite proxy) is stranded.
function Clear-StalePort {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        try {
            Stop-Process -Id $c.OwningProcess -Force -Confirm:$false -ErrorAction Stop
            Write-Host "[run-backend] freed port $Port (killed stale PID $($c.OwningProcess))" -ForegroundColor Yellow
        } catch {}
    }
}

while ($true) {
    # Re-read .env on every (re)start so a model/provider switch only needs
    # the python process killed - not this whole script restarted.
    Import-DotEnv
    if (-not (Test-Database)) { exit 1 }   # exit, don't restart: looping won't fix a down DB
    Clear-StalePort
    Write-Host "`n[run-backend] starting: uv run minder --host $AppHost --port $Port" -ForegroundColor DarkGray
    uv run minder --host $AppHost --port $Port
    $code = $LASTEXITCODE
    if ($code -eq 0) {
        Write-Host "[run-backend] exited cleanly (0). Stopping." -ForegroundColor Green
        break
    }
    Write-Host "[run-backend] exited with code $code - restarting in 2s (Ctrl+C to stop)..." -ForegroundColor Yellow
    Start-Sleep -Seconds 2
}
