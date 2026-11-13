# setup_scheduled_tasks.ps1 - Registers TradeBridge AutoStart and Watchdog in Windows Task Scheduler
# Run in Administrator PowerShell on the VPS.

param(
    [string]$RunAsUser = "SYSTEM" # Use "SYSTEM" or your specific Windows VPS username
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = (Get-Item $scriptDir).Parent.FullName
$startBat = Join-Path $rootDir "start_tradebridge.bat"
$watchdogBat = Join-Path $rootDir "scripts\run_watchdog.bat"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " TradeBridge VPS Task Scheduler Setup" -ForegroundColor Cyan
Write-Host " Root Directory: $rootDir" -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Register AutoStart Task (Trigger: At Startup, Restart on failure every 1 min)
$taskNameAutoStart = "TradeBridge-AutoStart"
Write-Host "`n[1/2] Configuring $taskNameAutoStart..." -ForegroundColor Yellow

$actionAutoStart = New-ScheduledTaskAction -Execute $startBat -WorkingDirectory $rootDir
$triggerAutoStart = New-ScheduledTaskTrigger -AtStartup

$settingsAutoStart = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

if ($RunAsUser -eq "SYSTEM") {
    $principalAutoStart = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
} else {
    $principalAutoStart = New-ScheduledTaskPrincipal -UserId $RunAsUser -LogonType InteractiveOrPassword -RunLevel Highest
}

# Unregister if already exists
Unregister-ScheduledTask -TaskName $taskNameAutoStart -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName $taskNameAutoStart `
    -Action $actionAutoStart `
    -Trigger $triggerAutoStart `
    -Settings $settingsAutoStart `
    -Principal $principalAutoStart `
    -Description "Starts TradeBridge FastAPI server and MT5 terminal on VPS boot." | Out-Null

Write-Host "✔ $taskNameAutoStart registered successfully." -ForegroundColor Green

# 2. Register Watchdog Task (Trigger: Every 5 minutes)
$taskNameWatchdog = "TradeBridge-Watchdog"
Write-Host "`n[2/2] Configuring $taskNameWatchdog..." -ForegroundColor Yellow

$actionWatchdog = New-ScheduledTaskAction -Execute $watchdogBat -WorkingDirectory (Join-Path $rootDir "scripts")
$triggerWatchdog = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)

$settingsWatchdog = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2)

if ($RunAsUser -eq "SYSTEM") {
    $principalWatchdog = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
} else {
    $principalWatchdog = New-ScheduledTaskPrincipal -UserId $RunAsUser -LogonType InteractiveOrPassword -RunLevel Highest
}

# Unregister if already exists
Unregister-ScheduledTask -TaskName $taskNameWatchdog -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName $taskNameWatchdog `
    -Action $actionWatchdog `
    -Trigger $triggerWatchdog `
    -Settings $settingsWatchdog `
    -Principal $principalWatchdog `
    -Description "Monitors TradeBridge /health endpoint every 5 minutes and restarts if down." | Out-Null

Write-Host "✔ $taskNameWatchdog registered successfully." -ForegroundColor Green

Write-Host "`nSetup completed successfully!" -ForegroundColor Cyan
