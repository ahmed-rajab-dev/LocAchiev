@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ============================================================
echo  Game Preparation & Deployment Tool v2.0
echo ============================================================
echo Current Directory: %CD%
echo.

set "APPID_FILE=steam appid.txt"
set "GAMES_DATA=games_data.txt"
set "GBE_DIR=gbe_settings_generator"
set "DONE_DIR=%GBE_DIR%\_OUTPUT_DONE"
set "PS_SCRIPT=prepare_games.ps1"

:: Step 1: Check Required System Components
echo [STEP 1/3] Verifying workspace setup and files...

if not exist "%APPID_FILE%" goto ERR_APPID
echo [OK] Verified: %APPID_FILE%

if not exist "%GAMES_DATA%" goto ERR_GAMES
echo [OK] Verified: %GAMES_DATA%

if not exist "%GBE_DIR%" goto ERR_GBE
echo [OK] Verified: %GBE_DIR%

if not exist "%PS_SCRIPT%" goto ERR_PS
echo [OK] Verified: %PS_SCRIPT%
echo.

goto STEP_2

:ERR_APPID
echo [ERROR] Critical file missing: '%APPID_FILE%'
goto FAILURE

:ERR_GAMES
echo [ERROR] Critical file missing: '%GAMES_DATA%'
goto FAILURE

:ERR_GBE
echo [ERROR] Critical directory missing: '%GBE_DIR%'
goto FAILURE

:ERR_PS
echo [ERROR] Critical script missing: '%PS_SCRIPT%'
goto FAILURE

:STEP_2
:: Step 2: Prompt Instructions Guidance
echo [STEP 2/3] User Input Instructions:
echo  - Choose whether to process Unity games as well (y/n).
echo  - Press ENTER on Selection to SKIP new generation and run audit sync.
echo  - Type 'all' to select ALL available filtered games.
echo  - Type space-separated numbers (e.g., '1 3 4') to select specific games.
echo.

:: Step 3: Run Engine
echo [STEP 3/3] Executing Orchestration Engine...
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"

set "PS_EXIT_CODE=%ERRORLEVEL%"

:: Step 4: Calculate Output Statistics
set /a PROCESSED_COUNT=0
if not exist "%DONE_DIR%" goto SHOW_STATS

for /d %%D in ("%DONE_DIR%\*") do set /a PROCESSED_COUNT+=1

:SHOW_STATS
echo.
echo ============================================================
echo  DETAILED PROCESS STATISTICS & STATUS REPORT
echo ============================================================

if %PS_EXIT_CODE% NEQ 0 goto SHOW_FAILURE

echo  [STATUS]           : SUCCESS
echo  [ARCHIVED GAMES]   : %PROCESSED_COUNT% Game Folder(s) in '_OUTPUT_DONE'
echo  [TARGET DONE DIR]  : %DONE_DIR%
echo  [APPID FILE]       : '%APPID_FILE%' successfully re-structured.
echo ============================================================
goto END

:SHOW_FAILURE
echo  [STATUS]           : FAILED / CRITICAL ERROR
echo  [LOG CHECK]        : Please review the PowerShell output logs above.
echo ============================================================
goto FAILURE

:FAILURE
echo.
echo [ERROR] Task ended with errors. Check log output above.

:END
echo ============================================================
echo  Press ANY KEY to close this window...
echo ============================================================
pause > nul