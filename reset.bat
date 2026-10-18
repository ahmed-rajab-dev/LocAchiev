@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ============================================================
echo  Environment Reset Tool v2.0
echo ============================================================
echo Current Directory: %CD%
echo.

set "PS_SCRIPT=reset.ps1"

if not exist "%PS_SCRIPT%" (
    echo [ERROR] Critical script missing: '%PS_SCRIPT%'
    goto FAILURE
)

echo [STEP 1/1] Executing Environment Reset Engine...
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"

set "PS_EXIT_CODE=%ERRORLEVEL%"

echo.
echo ============================================================
echo  RESET PROCESS STATUS REPORT
echo ============================================================

if %PS_EXIT_CODE% EQU 0 (
    echo [SUCCESS] Reset operations completed successfully.
    goto END
) else (
    echo [FAILED] Reset script encountered critical errors.
    goto FAILURE
)

:FAILURE
echo.
echo [ERROR] Reset process failed. Check output above for details.

:END
echo ============================================================
echo  Press ANY KEY to close this window...
echo ============================================================
pause > nul