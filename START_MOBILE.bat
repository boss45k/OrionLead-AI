@echo off
setlocal enabledelayedexpansion

echo ================================================
echo   OrionLead AI - Mobile Dev Startup
echo ================================================
echo.

:: Accept mode as first argument so this works non-interactively:
::   START_MOBILE.bat 1   (Expo Go)
::   START_MOBILE.bat 2   (Dev Build)
set MODE=%1

if "%MODE%"=="1" goto :expogo
if "%MODE%"=="2" goto :devbuild

echo   [1] Expo Go       - fast start, NO push notifications
echo   [2] Dev Build     - full features incl. push notifications
echo             (requires APK installed - run BUILD_DEV.bat first)
echo.
set /p MODE="Select mode [1/2]: "

if "%MODE%"=="2" goto :devbuild
goto :expogo

:devbuild
set EXPO_FLAGS=--dev-client --localhost --clear
set LAUNCH_SCHEME=orionlead-ai
echo.
echo [Mode] Development Build (ADB tunnel - no ngrok needed)
goto :start

:expogo
set EXPO_FLAGS=--clear --lan
set LAUNCH_SCHEME=exp://127.0.0.1:8081
echo.
echo [Mode] Expo Go (push notifications unavailable in SDK 53+)
goto :start

:start

REM ── 0. Set backend URL ────────────────────────────────────
echo.
echo [0/4] Configuring backend URL...
if "%MODE%"=="2" (
    REM Dev Build + tunnel: backend reaches PC via ADB reverse USB tunnel.
    REM 127.0.0.1 on the phone is forwarded to 127.0.0.1 on this PC by ADB.
    REM This bypasses Windows Firewall entirely — no LAN IP needed.
    set EXPO_API_BASE_URL=http://127.0.0.1:5000
    echo      Mode: ADB reverse tunnel
    echo      Backend URL: http://127.0.0.1:5000  ^(forwarded over USB^)
) else (
    REM Expo Go + LAN: need the PC's real LAN IP so the phone can reach Flask over WiFi.
    for /f "tokens=2 delims=:" %%I in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "127.0.0.1"') do (
        set RAW_IP=%%I
        set RAW_IP=!RAW_IP: =!
        if not "!RAW_IP!"=="" (set PC_LAN_IP=!RAW_IP!)
    )
    if defined PC_LAN_IP (
        set EXPO_API_BASE_URL=http://!PC_LAN_IP!:5000
        echo      PC LAN IP: !PC_LAN_IP!
        echo      Backend URL: http://!PC_LAN_IP!:5000  ^(WiFi — same network required^)
    ) else (
        echo      WARNING: Could not detect LAN IP. Backend may not be reachable from phone.
    )
)

REM ── 1. Start Backend (if not already running) ──────────────
echo.
echo [1/4] Checking backend on port 5000...
curl -s http://localhost:5000/api/v1/health >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo      Starting backend...
    start "Backend API" cmd /k "cd /d %~dp0 && call venv\Scripts\activate && cd backend && python run.py"
    echo      Waiting for backend to boot...
    ping -n 6 127.0.0.1 >nul
) else (
    echo      Backend already running.
)

REM ── 1b. Open firewall ports (silently — only works if running as admin) ─
netsh advfirewall firewall add rule name="Expo Metro 8081" dir=in action=allow protocol=TCP localport=8081 >nul 2>&1
netsh advfirewall firewall add rule name="Flask Backend 5000" dir=in action=allow protocol=TCP localport=5000 >nul 2>&1

REM ── 2. ADB reverse tunnels ─────────────────────────────────
echo.
echo [2/4] Setting up ADB reverse tunnels...
adb reverse tcp:5000 tcp:5000 >nul 2>&1
adb reverse tcp:8081 tcp:8081 >nul 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo      WARNING: ADB failed. Make sure:
    echo        - Phone is plugged in via USB
    echo        - USB Debugging is enabled
    echo        - You approved the USB debugging prompt on your phone
    echo      Re-run this script after connecting the phone.
) else (
    echo      ADB tunnels active ^(phone localhost = this PC^)
)

REM ── 3. Start Metro bundler ─────────────────────────────────
echo.
echo [3/4] Starting Metro bundler...
start "Metro Bundler" cmd /k "cd /d %~dp0mobile && npx expo start %EXPO_FLAGS%"

REM ── 4. Open app on phone ───────────────────────────────────
ping -n 5 127.0.0.1 >nul
echo.
echo [4/4] Opening app on phone...

if "%MODE%"=="2" (
    REM Dev build: open via deep link to the custom scheme
    adb shell am start -a android.intent.action.VIEW -d "orionlead-ai://" com.orionlead.ai >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo      Could not auto-open dev build.
        echo      Open the OrionLead AI app on your phone manually.
        echo      It will connect to Metro automatically.
    ) else (
        echo      Dev build opened on phone.
    )
) else (
    REM Expo Go: open via exp:// scheme
    adb shell am start -a android.intent.action.VIEW -d "exp://127.0.0.1:8081" host.exp.exponent >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo      Could not auto-open Expo Go. Open it manually and scan the QR code.
    ) else (
        echo      Expo Go opened on phone.
    )
)

echo.
echo ================================================
echo   DONE — App loading on your phone
echo ================================================
echo.
echo   Backend : http://localhost:5000
echo   Metro   : http://localhost:8081
if "%MODE%"=="2" (
    echo   Mode    : Development Build ^(push notifications ACTIVE^)
) else (
    echo   Mode    : Expo Go ^(push notifications unavailable^)
    echo.
    echo   To enable push notifications: run BUILD_DEV.bat
)
echo.

REM ── 5. Tunnel watchdog — keeps ADB alive ──────────────────
:watchdog
ping -n 6 127.0.0.1 >nul
adb devices 2>nul | findstr /C:"device" | findstr /V /C:"List" >nul
if %ERRORLEVEL% EQU 0 (
    adb reverse tcp:5000 tcp:5000 >nul 2>&1
    adb reverse tcp:8081 tcp:8081 >nul 2>&1
)
goto watchdog
