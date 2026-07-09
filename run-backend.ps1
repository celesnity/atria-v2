# run-backend.ps1 - Atria backend (FastAPI web server) with auto-restart.
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
# (e.g. DATABASE_URL, ATRIA_MODEL) and does NOT call load_dotenv itself, so we
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

Write-Host "Atria backend -> http://${AppHost}:${Port}  (Ctrl+C to stop)" -ForegroundColor Cyan

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
    Clear-StalePort
    Write-Host "`n[run-backend] starting: uv run atria --host $AppHost --port $Port" -ForegroundColor DarkGray
    uv run atria --host $AppHost --port $Port
    $code = $LASTEXITCODE
    if ($code -eq 0) {
        Write-Host "[run-backend] exited cleanly (0). Stopping." -ForegroundColor Green
        break
    }
    Write-Host "[run-backend] exited with code $code - restarting in 2s (Ctrl+C to stop)..." -ForegroundColor Yellow
    Start-Sleep -Seconds 2
}
