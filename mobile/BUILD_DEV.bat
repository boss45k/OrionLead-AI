@echo off
setlocal
title OrionLead AI - Dev Build
cd /d "%~dp0"

echo.
echo ====================================================
echo   OrionLead AI - Development Build (Android APK)
echo ====================================================
echo.

:: ── 1. EAS CLI ────────────────────────────────────────────────────────────
where eas >nul 2>nul
if errorlevel 1 (
    echo [1/5] Installing EAS CLI...
    call npm install -g eas-cli
) else (
    echo [1/5] EAS CLI ready.
)

:: ── 2. Show logged-in user (info only, no exit on failure) ────────────────
echo.
echo [2/5] Expo account:
call eas whoami
echo.

:: ── 3. Git setup ──────────────────────────────────────────────────────────
echo [3/5] Git setup...
git rev-parse --git-dir >nul 2>nul
if errorlevel 1 (
    echo   Initializing git...
    git init
    git add -A
    git commit -m "Initial EAS build commit"
) else (
    git add -A
    git commit -m "Pre-build update"
    if errorlevel 1 echo   (nothing new to commit - OK)
)
echo   Git done.

:: ── 4. Link to EAS ────────────────────────────────────────────────────────
echo.
echo [4/5] Linking to EAS project...
call eas init --id ccbf9b32-8f44-400f-adfa-875f443b5586 --non-interactive
echo.

:: ── 5. Build APK ──────────────────────────────────────────────────────────
echo [5/5] Building Android APK on EAS servers...
echo (This takes 10-15 min. A download link appears when done.)
echo.
call eas build --platform android --profile development --non-interactive

echo.
echo ====================================================
echo   DONE - Download APK from the link above
echo   Then: START_MOBILE.bat option [2] Dev Build
echo ====================================================
pause
