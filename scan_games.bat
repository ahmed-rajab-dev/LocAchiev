@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ============================================================
echo  Steam API Games Scanner - Starter
echo ============================================================
echo Current Directory: %CD%
echo.

set /p TARGET_PATH="Enter the target games directory path (e.g., F:\1.games): "

if "%TARGET_PATH%"=="" (
    echo.
    echo [ERROR] No directory path was provided. Operation cancelled.
    goto FAILURE
)

if not exist "%TARGET_PATH%" (
    echo.
    echo [ERROR] Specified directory does not exist: %TARGET_PATH%
    goto FAILURE
)

set "PS_SCRIPT=scan_games.ps1"

if not exist "%PS_SCRIPT%" (
    echo.
    echo [ERROR] Critical PowerShell script missing: '%PS_SCRIPT%'
    goto FAILURE
)

echo.
echo ============================================================
echo Launching PowerShell Scanner Engine...
echo Target Directory: %TARGET_PATH%
echo Script File      : %PS_SCRIPT%
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -GamesPath "%TARGET_PATH%"

set "PS_EXIT_CODE=%ERRORLEVEL%"

echo.
echo ============================================================
echo  SCANNER STATUS REPORT
echo ============================================================

if %PS_EXIT_CODE% EQU 0 (
    echo [SUCCESS] Game directory scanning completed without any errors!
    goto END
) else if %PS_EXIT_CODE% EQU 2 (
    echo [WARNING] Game data was added, BUT AppID Mismatches were detected for some games!
    echo           Check red log entries above for details on mismatched AppIDs.
    goto END
) else (
    echo [FAILED] Scanner script encountered critical errors during execution.
    goto FAILURE
)

:FAILURE
echo.
echo [ERROR] Scan process failed or ended with critical errors.
echo Please review the output log above for details.

:END
echo.
echo ============================================================
echo  Batch script finished. Press ANY KEY to close this window...
echo ============================================================
pause > nul