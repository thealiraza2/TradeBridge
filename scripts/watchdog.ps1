# watchdog.ps1 - Health monitoring script for TradeBridge
# Checks http://127.0.0.1:8000/health; restarts server if it fails 2 consecutive times.

$ErrorActionPreference = "SilentlyContinue"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = (Get-Item $scriptDir).Parent.FullName
$logFile = Join-Path $rootDir "logs\tradebridge.log"
$counterFile = Join-Path $rootDir "logs\watchdog_failures.txt"
$startScript = Join-Path $rootDir "start_tradebridge.bat"
$healthUrl = "http://127.0.0.1:8000/health"

Function Write-Log {
    param([string]$message, [string]$level = "INFO")
    $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss,fff")
    $logLine = "$timestamp - $level - [WATCHDOG] $message"
    Add-Content -Path $logFile -Value $logLine
    Write-Host $logLine
}

# Read current consecutive failure count
$failures = 0
if (Test-Path $counterFile) {
    $raw = Get-Content $counterFile -ErrorAction SilentlyContinue
    if ($raw -match '^\d+$') {
        $failures = [int]$raw
    }
}

$isHealthy = $false
try {
    $response = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 5 -ErrorAction Stop
    if ($response -and $response.status -eq "ok") {
        $isHealthy = $true
    }
} catch {
    $isHealthy = $false
}

if ($isHealthy) {
    if ($failures -gt 0) {
        Write-Log "Server recovered. Health check passed." "INFO"
        Set-Content -Path $counterFile -Value "0"
    }
} else {
    $failures++
    Set-Content -Path $counterFile -Value "$failures"
    Write-Log "Health check failed (attempt $failures/2)." "WARNING"

    if ($failures -ge 2) {
        Write-Log "Consecutive failure limit reached (2/2). Triggering server restart..." "ERROR"

        # Terminate any orphaned uvicorn process on port 8000
        try {
            $connections = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
            foreach ($conn in $connections) {
                if ($conn.OwningProcess -gt 0) {
                    Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
                    Write-Log "Terminated stale process on port 8000 (PID: $($conn.OwningProcess))" "WARNING"
                }
            }
        } catch {
            # Fallback if Get-NetTCPConnection is unavailable
        }

        # Restart server via start_tradebridge.bat
        if (Test-Path $startScript) {
            Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$startScript`"" -WorkingDirectory $rootDir -WindowStyle Minimized
            Write-Log "Spawned start_tradebridge.bat." "INFO"
        }

        # Reset failure counter
        Set-Content -Path $counterFile -Value "0"
    }
}
