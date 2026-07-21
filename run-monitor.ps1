param(
    [int]$Port = 9310,
    [string]$FleetUrl = "http://127.0.0.1:5250",
    [ValidateSet("laundry", "factory")]
    [string]$FleetDomain = "laundry",
    [switch]$Rebuild,
    [switch]$NoSimulator
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$monitorProjectRoot = $PSScriptRoot
$monitorBackend = Join-Path $monitorProjectRoot "modules\monitor\backend"
$monitorFrontend = Join-Path $monitorProjectRoot "modules\monitor\frontend"
$monitorDist = Join-Path $monitorFrontend "dist"
$monitorRemoteEntry = Join-Path $monitorDist "remoteEntry.js"
$monitorIndex = Join-Path $monitorDist "index.html"
$monitorPython = Join-Path $monitorProjectRoot ".venv\Scripts\python.exe"
$simulatorRoot = "D:\[Research]_IIOT\[Project]_IOTMock"
$simulatorWorkingDirectory = [System.Management.Automation.WildcardPattern]::Escape($simulatorRoot)
$simulatorPython = Join-Path $simulatorRoot ".venv\Scripts\python.exe"
$simulatorScript = Join-Path $simulatorRoot "scripts\run_fleet_server.py"
$localLogRoot = Join-Path $monitorProjectRoot "_local"
$monitorBaseUrl = "http://127.0.0.1:$Port"
$monitorPublicBase = "http://localhost:$Port"
$monitorBrowserUrl = "http://localhost:$Port/dashboard/index.html"
$startedSimulator = $null

# Vite bakes the module-federation asset origin into the build. Set it before the
# build check so -Port works for both the standalone dashboard and remote entry.
$env:MONITOR_PUBLIC_BASE = $monitorPublicBase

function Test-HttpEndpoint {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    }
    catch {
        return $false
    }
}

function Get-HttpJson {
    param([string]$Url)

    try {
        return Invoke-RestMethod -Uri $Url -TimeoutSec 3
    }
    catch {
        return $null
    }
}

function Assert-FleetContract {
    param(
        [object]$Health,
        [string]$ExpectedDomain,
        [string]$HealthUrl
    )

    if ($null -eq $Health) {
        throw "Simulator health is unavailable at $HealthUrl."
    }
    if ([string]$Health.domain -ne $ExpectedDomain) {
        throw "Simulator domain mismatch at $HealthUrl. Expected '$ExpectedDomain' but found '$($Health.domain)'. Stop the other simulator or pass -FleetDomain $($Health.domain)."
    }
    if ($ExpectedDomain -eq "laundry") {
        if ([int]$Health.machines -ne 10) {
            throw "Laundry simulator contract mismatch: expected 10 machines but found $($Health.machines)."
        }
        if ([string]$Health.operations_contract -ne "monitor.operations.v1") {
            throw "Laundry simulator is missing monitor.operations.v1. Update and restart IOTMock."
        }
    }
}

function Test-TcpEndpoint {
    param(
        [string]$HostName,
        [int]$TcpPort
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connected = $client.ConnectAsync($HostName, $TcpPort).Wait(500)
        return $connected -and $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Test-FrontendBuildRequired {
    if ($Rebuild -or -not (Test-Path -LiteralPath $monitorRemoteEntry) -or -not (Test-Path -LiteralPath $monitorIndex)) {
        return $true
    }

    $indexHtml = Get-Content -LiteralPath $monitorIndex -Raw
    if (-not $indexHtml.Contains("$monitorPublicBase/dashboard/")) {
        return $true
    }

    $buildTime = (Get-Item -LiteralPath $monitorRemoteEntry).LastWriteTimeUtc
    $inputs = @(
        Get-ChildItem -LiteralPath (Join-Path $monitorFrontend "src") -File -Recurse
        Get-Item -LiteralPath (Join-Path $monitorFrontend "package.json")
        Get-Item -LiteralPath (Join-Path $monitorFrontend "package-lock.json")
        Get-Item -LiteralPath (Join-Path $monitorFrontend "vite.config.ts")
    )

    return ($inputs | Where-Object { $_.LastWriteTimeUtc -gt $buildTime }).Count -gt 0
}

function Invoke-CheckedCommand {
    param(
        [string]$Label,
        [scriptblock]$Command
    )

    Write-Host "==> $Label"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed (exit $LASTEXITCODE)"
    }
}

Set-Location -LiteralPath $monitorProjectRoot

if (Test-HttpEndpoint "$monitorBaseUrl/connector/health") {
    Write-Host "Monitor is already running."
    Write-Host "Open: $monitorBrowserUrl"
    exit 0
}

if (Test-TcpEndpoint "127.0.0.1" $Port) {
    throw "Port $Port is already in use by another service. Run .\run-monitor.ps1 -Port <free-port>."
}

if (-not (Test-Path -LiteralPath $monitorPython)) {
    throw "The project environment is missing. Stop running Minder services, then run .\init.ps1 once."
}

if (Test-FrontendBuildRequired) {
    if (-not (Test-Path -LiteralPath (Join-Path $monitorFrontend "node_modules"))) {
        Invoke-CheckedCommand "Installing Monitor dashboard packages" {
            & npm.cmd install --prefix $monitorFrontend
        }
    }

    Invoke-CheckedCommand "Building Monitor dashboard" {
        & npm.cmd run build --prefix $monitorFrontend
    }
}
else {
    Write-Host "==> Monitor dashboard is already built"
}

$fleetUri = [System.Uri]$FleetUrl
$fleetIsLocal = $fleetUri.Host -in @("127.0.0.1", "localhost", "::1")
$fleetHealthUrl = "$($fleetUri.Scheme)://$($fleetUri.Authority)/health"

$fleetHealth = Get-HttpJson $fleetHealthUrl
if ($null -eq $fleetHealth) {
    if ($NoSimulator -or -not $fleetIsLocal) {
        Write-Warning "Simulator is unavailable at $fleetHealthUrl. Monitor will start with disconnected data."
    }
    else {
        if (Test-TcpEndpoint $fleetUri.Host $fleetUri.Port) {
            throw "Port $($fleetUri.Port) accepts TCP connections but does not expose the expected IOTMock health endpoint. Stop that process or use another -FleetUrl."
        }
        if (-not (Test-Path -LiteralPath $simulatorPython)) {
            throw "IOTMock is not initialized. Run D:\[Research]_IIOT\[Project]_IOTMock\init.ps1 once."
        }
        if (-not (Test-Path -LiteralPath $simulatorScript)) {
            throw "IOTMock runner was not found at $simulatorScript."
        }

        New-Item -ItemType Directory -Path $localLogRoot -Force | Out-Null
        $logStamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $simulatorOutLog = Join-Path $localLogRoot "monitor-simulator-$logStamp.out.log"
        $simulatorErrorLog = Join-Path $localLogRoot "monitor-simulator-$logStamp.err.log"
        $simulatorOutLogProcess = [System.Management.Automation.WildcardPattern]::Escape($simulatorOutLog)
        $simulatorErrorLogProcess = [System.Management.Automation.WildcardPattern]::Escape($simulatorErrorLog)

        $env:IIOT_FLEET_DOMAIN = $FleetDomain
        $env:IIOT_FLEET_PORT = [string]$fleetUri.Port
        if ($FleetDomain -eq "factory") {
            $env:IIOT_FLEET_SCENARIO = "Monitor Produce Optimize V1"
        }
        else {
            Remove-Item Env:IIOT_FLEET_SCENARIO -ErrorAction SilentlyContinue
        }

        Write-Host "==> Starting IOTMock $FleetDomain simulator on port $($fleetUri.Port)"
        $startedSimulator = Start-Process `
            -FilePath $simulatorPython `
            -ArgumentList @($simulatorScript) `
            -WorkingDirectory $simulatorWorkingDirectory `
            -RedirectStandardOutput $simulatorOutLogProcess `
            -RedirectStandardError $simulatorErrorLogProcess `
            -WindowStyle Hidden `
            -PassThru

        $simulatorReady = $false
        for ($attempt = 1; $attempt -le 20; $attempt++) {
            $fleetHealth = Get-HttpJson $fleetHealthUrl
            if ($null -ne $fleetHealth) {
                $simulatorReady = $true
                break
            }
            if ($startedSimulator.HasExited) {
                break
            }
            Start-Sleep -Milliseconds 500
        }

        if (-not $simulatorReady) {
            throw "IOTMock did not become ready. See $simulatorErrorLog."
        }
        Assert-FleetContract $fleetHealth $FleetDomain $fleetHealthUrl
    }
}
else {
    Assert-FleetContract $fleetHealth $FleetDomain $fleetHealthUrl
    Write-Host "==> Reusing IOTMock at $FleetUrl"
}

$env:IIOT_FLEET_URL = $FleetUrl
$env:MONITOR_DASHBOARD_DIST = $monitorDist
$env:MONITOR_PUBLIC_BASE = $monitorPublicBase
$env:MONITOR_EVENT_POLL_SEC = "4"

Write-Host ""
Write-Host "Monitor is starting."
Write-Host "Open: $monitorBrowserUrl"
Write-Host "Press Ctrl+C to stop Monitor."
Write-Host ""

$monitorExitCode = 0
try {
    & $monitorPython -m uvicorn app:app --app-dir $monitorBackend --host 127.0.0.1 --port $Port
    $monitorExitCode = $LASTEXITCODE
}
finally {
    if ($null -ne $startedSimulator -and -not $startedSimulator.HasExited) {
        Write-Host "==> Stopping the IOTMock simulator started by this launcher"
        Stop-Process -Id $startedSimulator.Id -Force
        $startedSimulator.WaitForExit()
    }
}

exit $monitorExitCode
