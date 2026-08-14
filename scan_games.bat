@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ============================================================
echo  Steam API Games Scanner - Starter
echo ============================================================
echo Current Directory: %CD%
echo.

set "PS_SCRIPT=scan_games.ps1"

if not exist "%PS_SCRIPT%" (
    echo [ERROR] %PS_SCRIPT% not found in current directory!
    goto END
)

set /p "TARGET_PATH=Enter the target games directory path (e.g., F:\1.games): "

if "%TARGET_PATH%"=="" (
    echo [ERROR] No path entered! Exiting...
    goto END
)

if not exist "%TARGET_PATH%" (
    echo [ERROR] Target path does not exist: %TARGET_PATH%
    goto END
)

echo.
echo Launching PowerShell Scanner...
echo Target Directory: %TARGET_PATH%
echo Script File: %PS_SCRIPT%
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -GamesPath "%TARGET_PATH%"

set "PS_EXIT_CODE=%ERRORLEVEL%"

echo.
echo ============================================================
echo  SCAN REPORT
echo ============================================================

if %PS_EXIT_CODE% EQU 0 (
    echo [SUCCESS] Scan operation completed successfully.
) else (
    echo [FAILED] Scan operation terminated with error code: %PS_EXIT_CODE%
)

:END
echo ============================================================
echo Batch script finished.
echo Press ANY KEY to close this window...
echo ============================================================
pause > nul