@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ============================================================
echo  Achievement Standalone Builder v3 (DEBUG MODE)
echo ============================================================
echo Current Directory: %CD%
echo.

set "GAMES_FILE=games_data.txt"
set "TEMPLATE_FILE=template.html"
set "OUTPUT_DIR=Hall of Fame"
set "PS_SCRIPT=build.ps1"
set "INDEX_FILE=index.html"

:: Check required files
if not exist "%GAMES_FILE%" (
    echo [ERROR] %GAMES_FILE% not found!
    goto END
)
if not exist "%TEMPLATE_FILE%" (
    echo [ERROR] %TEMPLATE_FILE% not found!
    goto END
)
if not exist "%PS_SCRIPT%" (
    echo [ERROR] %PS_SCRIPT% not found!
    goto END
)

:: Prompt User for Mode
echo Select Mode:
echo  [1] Press Enter directly for normal BUILD
echo  [2] Type 'reset' to Reset Environment
echo.
set "MODE=build"
set /p "USER_INPUT=Type choice or press Enter: "
if /i "%USER_INPUT%"=="reset" set "MODE=reset"

echo.
echo Starting PowerShell process (Mode: %MODE%)...
echo ============================================================

:: Run PowerShell script file safely with Mode argument
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -Mode "%MODE%"

set "PS_EXIT_CODE=%ERRORLEVEL%"

echo.
echo ============================================================
echo  PROCESS STATUS REPORT
echo ============================================================

if %PS_EXIT_CODE% EQU 0 (
    if "%MODE%"=="reset" (
        echo  [SUCCESS] Environment reset completed successfully!
    ) else (
        if exist "%INDEX_FILE%" (
            echo  [SUCCESS] index.html has been updated successfully!
        ) else (
            echo  [WARNING] Process finished, but index.html file was missing.
        )
    )
) else (
    echo  [FAILED] Process failed due to an error.
)

:END
echo ============================================================
echo  Batch script finished.
echo  Press ANY KEY to close this window...
echo ============================================================
pause > nul