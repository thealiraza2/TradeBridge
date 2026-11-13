@echo off
setlocal enabledelayedexpansion

:: Navigate to script directory
cd /d "%~dp0"

echo [TradeBridge] Starting 24/7 Service...

:: 1. Check if MetaTrader 5 is running; launch if not
tasklist /fi "imagename eq terminal64.exe" | find /i "terminal64.exe" >nul
if errorlevel 1 (
    echo [TradeBridge] MetaTrader 5 is not running. Attempting to start...
    set "MT5_PATH="
    if exist "%ProgramFiles%\MetaTrader 5\terminal64.exe" (
        set "MT5_PATH=%ProgramFiles%\MetaTrader 5\terminal64.exe"
    ) else if exist "%ProgramFiles(x86)%\MetaTrader 5\terminal64.exe" (
        set "MT5_PATH=%ProgramFiles(x86)%\MetaTrader 5\terminal64.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\MetaTrader 5\terminal64.exe" (
        set "MT5_PATH=%LOCALAPPDATA%\Programs\MetaTrader 5\terminal64.exe"
    )

    if defined MT5_PATH (
        echo [TradeBridge] Launching MT5 from: !MT5_PATH!
        start "" "!MT5_PATH!"
    ) else (
        echo [TradeBridge] MT5 not found in standard paths. Attempting start terminal64.exe...
        start "" terminal64.exe 2>nul
    )
    :: Allow MT5 terminal 5 seconds to initialize IPC connection
    timeout /t 5 /nobreak >nul
) else (
    echo [TradeBridge] MetaTrader 5 terminal is already active.
)

:: 2. Start FastAPI Server via uvicorn
echo [TradeBridge] Starting FastAPI server on 127.0.0.1:8000...
if exist "%~dp0.venv\Scripts\uvicorn.exe" (
    "%~dp0.venv\Scripts\uvicorn.exe" server.main:app --host 127.0.0.1 --port 8000
) else (
    python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
)

endlocal
