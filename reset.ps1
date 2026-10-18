[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$hofDir        = Join-Path $PSScriptRoot "Hall of Fame"
$targetTxtFile = Join-Path $PSScriptRoot "steam appid.txt"
$gamesDataFile = Join-Path $PSScriptRoot "games_data.txt"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "          RESETTING TESTING ENVIRONMENT           " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# STEP 1: Clear Hall of Fame Folder
Write-Host "`n[1/3] Cleaning Hall of Fame directory..." -ForegroundColor Yellow
if (Test-Path $hofDir) {
    try {
        Get-ChildItem -Path $hofDir -Recurse | Remove-Item -Force -Recurse -ErrorAction Stop
        Write-Host " [SUCCESS] 'Hall of Fame' folder emptied successfully." -ForegroundColor Green
    } catch {
        Write-Host " [FAILED] Could not clear Hall of Fame: $($_.Exception.Message)" -ForegroundColor Red
    }
} else {
    Write-Host " [SKIP] 'Hall of Fame' folder does not exist." -ForegroundColor DarkGray
}

# STEP 2: Clear games_data.txt Content Completely
Write-Host "`n[2/3] Wiping 'games_data.txt' content..." -ForegroundColor Yellow
if (Test-Path $gamesDataFile) {
    try {
        Clear-Content -Path $gamesDataFile -ErrorAction Stop
        Write-Host " [SUCCESS] 'games_data.txt' cleared successfully." -ForegroundColor Green
    } catch {
        Write-Host " [FAILED] Could not clear 'games_data.txt': $($_.Exception.Message)" -ForegroundColor Red
    }
} else {
    Write-Host " [SKIP] 'games_data.txt' file does not exist." -ForegroundColor DarkGray
}

# STEP 3: Restore 'DONE GAMES' into 'PREPARED GAMES' Section in steam appid.txt
Write-Host "`n[3/3] Restoring 'DONE GAMES' into 'PREPARED GAMES' in 'steam appid.txt'..." -ForegroundColor Yellow

if (Test-Path $targetTxtFile) {
    try {
        $lines = Get-Content -Path $targetTxtFile -Encoding UTF8 -ErrorAction Stop
        
        $activeGames   = @()
        $preparedGames = @()
        $doneGames     = @()

        $currentSection = "ACTIVE"

        foreach ($line in $lines) {
            $trimmed = $line.Trim()
            if ([string]::IsNullOrWhiteSpace($trimmed)) { continue }

            if ($trimmed -match '^-{3,}$') { continue }

            if ($trimmed -ieq "PREPARED GAMES") {
                $currentSection = "PREPARED"
                continue
            }

            if ($trimmed -ieq "DONE GAMES") {
                $currentSection = "DONE"
                continue
            }

            if ($trimmed -match '^\s*(.+)\s*:\s*(\d+)\s*$') {
                switch ($currentSection) {
                    "ACTIVE"   { $activeGames += $trimmed }
                    "PREPARED" { $preparedGames += $trimmed }
                    "DONE"     { $doneGames += $trimmed }
                }
            }
        }

        # Merge DONE GAMES into PREPARED GAMES
        $allPrepared = $preparedGames + $doneGames

        $finalLines = @()

        # 1. Preserve Active Games at Top
        if ($activeGames.Count -gt 0) {
            $finalLines += $activeGames
        }

        # 2. Append all Prepared + Restored Done Games under PREPARED GAMES header
        if ($allPrepared.Count -gt 0) {
            $finalLines += "-----------------------------"
            $finalLines += "PREPARED GAMES"
            $finalLines += "-----------------------------"
            $finalLines += $allPrepared
        }

        Set-Content -Path $targetTxtFile -Value $finalLines -Encoding UTF8 -ErrorAction Stop
        Write-Host " [SUCCESS] All 'DONE GAMES' moved to 'PREPARED GAMES'. Saved to: $targetTxtFile" -ForegroundColor Green
    } catch {
        Write-Host " [FAILED] Could not update 'steam appid.txt': $($_.Exception.Message)" -ForegroundColor Red
    }
} else {
    Write-Host " [FAILED] 'steam appid.txt' not found at: $targetTxtFile" -ForegroundColor Red
}

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host "               RESET PROCESS COMPLETED            " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan