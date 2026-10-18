param (
    [Parameter(Mandatory=$true)]
    [string]$GamesPath
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Continue'

$GAMES_DATA_FILE = Join-Path $PSScriptRoot "games_data.txt"
$STEAM_APPID_FILE = Join-Path $PSScriptRoot "steam appid.txt"

Write-Host "[PS-INIT] Starting game directory scan process..." -ForegroundColor Cyan
Write-Host "[PS-INIT] Target Games Path : $GamesPath" -ForegroundColor Gray
Write-Host "[PS-INIT] Games Data File  : $GAMES_DATA_FILE" -ForegroundColor Gray
Write-Host "[PS-INIT] Steam AppID File : $STEAM_APPID_FILE" -ForegroundColor Gray
Write-Host ""

if (-not (Test-Path $GamesPath)) {
    Write-Host "[PS-ERROR] Target directory does not exist: $GamesPath" -ForegroundColor Red
    exit 1
}

# 1. Load existing game names from games_data.txt
$existingGames = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)

if (Test-Path $GAMES_DATA_FILE) {
    Write-Host "[PS-LOG] Reading existing games from $GAMES_DATA_FILE to avoid duplicates..." -ForegroundColor Yellow
    $lines = Get-Content -Path $GAMES_DATA_FILE -Encoding UTF8
    foreach ($line in $lines) {
        if ($line -match '^name\s*=\s*(.+)$') {
            $extractedName = $matches[1].Trim()
            [void]$existingGames.Add($extractedName)
        }
    }
    Write-Host "[PS-LOG] Found $($existingGames.Count) existing game(s) in dataset." -ForegroundColor DarkGray
} else {
    Write-Host "[PS-LOG] No existing games_data.txt file found. A new one will be created." -ForegroundColor Yellow
}

# 2. Parse steam appid.txt
$activeAppLines   = @()
$preparedAppLines = @()
$doneAppLines     = @()
$registeredNames  = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)

if (Test-Path $STEAM_APPID_FILE) {
    Write-Host "[PS-LOG] Parsing existing $STEAM_APPID_FILE..." -ForegroundColor Yellow
    $appContent = Get-Content -Path $STEAM_APPID_FILE -Encoding UTF8
    $currentSection = "ACTIVE"

    foreach ($line in $appContent) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed -match '^-{3,}$') { continue }

        if ($trimmed -ieq "PREPARED GAMES") { $currentSection = "PREPARED"; continue }
        if ($trimmed -ieq "DONE GAMES")     { $currentSection = "DONE"; continue }

        if ($trimmed -match '^\s*(.+)\s*:\s*(\d+)\s*$') {
            $gName = $matches[1].Trim()
            [void]$registeredNames.Add($gName)
            switch ($currentSection) {
                "ACTIVE"   { $activeAppLines += $trimmed }
                "PREPARED" { $preparedAppLines += $trimmed }
                "DONE"     { $doneAppLines += $trimmed }
            }
        }
    }
} else {
    Write-Host "[PS-LOG] No steam appid.txt found. A new file will be initialized." -ForegroundColor Yellow
}

# 3. Discover subdirectories
Write-Host "[PS-LOG] Discovering subdirectories inside target path..." -ForegroundColor Cyan
try {
    $subFolders = Get-ChildItem -Path $GamesPath -Directory -ErrorAction Stop
} catch {
    Write-Host "[PS-ERROR] Failed to list directories in $GamesPath : $_" -ForegroundColor Red
    exit 1
}

Write-Host "[PS-LOG] Total subfolders found: $($subFolders.Count)" -ForegroundColor Green
Write-Host ""

$addedCount       = 0
$skippedCount     = 0
$notFoundCount    = 0
$newAppIdsAdded   = 0
$mismatchCount    = 0
$newActiveEntries = @()

foreach ($folder in $subFolders) {
    $gameName   = $folder.Name
    $folderPath = $folder.FullName

    Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "[PS-SCAN] Checking Folder: '$gameName'" -ForegroundColor Cyan
    Write-Host "[PS-PATH] Full Path: $folderPath" -ForegroundColor Gray

    if ($existingGames.Contains($gameName)) {
        Write-Host "[PS-SKIP] Game '$gameName' is already present in games_data.txt. Skipping..." -ForegroundColor Yellow
        $skippedCount++
        continue
    }

    # Detect Unity Game Structure (*_Data directory)
    $unityDataDir = Get-ChildItem -Path $folderPath -Directory -ErrorAction SilentlyContinue | 
                    Where-Object { $_.Name -like "*_Data" } | Select-Object -First 1
    
    $isUnity = if ($unityDataDir) { "True" } else { "False" }

    # Search for steam_api64.dll / steam_api.dll
    Write-Host "[PS-SEARCH] Searching for steam_api64.dll / steam_api.dll inside '$gameName'..." -ForegroundColor Gray
    
    $allDlls = Get-ChildItem -Path $folderPath -Recurse -File -ErrorAction SilentlyContinue | 
               Where-Object { $_.Name -ieq "steam_api64.dll" -or $_.Name -ieq "steam_api.dll" }

    $foundApi = $allDlls | Where-Object { $_.Name -ieq "steam_api64.dll" } | Select-Object -First 1
    $apiType = "64"

    if (-not $foundApi) {
        $foundApi = $allDlls | Where-Object { $_.Name -ieq "steam_api.dll" } | Select-Object -First 1
        $apiType = "86"
    }

    if ($foundApi) {
        $rawFolderDirectory = $foundApi.DirectoryName
        
        Write-Host " [SUCCESS] Priority DLL Found ($($foundApi.Name)) at: $($foundApi.FullName)" -ForegroundColor Green
        Write-Host " [FORMAT] Calculated RawAchiev_path: $rawFolderDirectory" -ForegroundColor Green
        Write-Host " [FORMAT] Detected steam_api: $apiType" -ForegroundColor Green
        Write-Host " [UNITY] Unity Engine Detected: $isUnity" -ForegroundColor Cyan

        $entryLines = @(
            "name = $gameName",
            "RawAchiev_path = $rawFolderDirectory",
            "steam_api = $apiType",
            "unity_game = $isUnity",
            "..."
        )

        try {
            Add-Content -Path $GAMES_DATA_FILE -Value $entryLines -Encoding UTF8 -ErrorAction Stop
            [void]$existingGames.Add($gameName)
            $addedCount++
            Write-Host " [SUCCESS] Appended entry for '$gameName' to $GAMES_DATA_FILE" -ForegroundColor Green
        } catch {
            Write-Host " [FAILED] Could not write entry to $GAMES_DATA_FILE : $_" -ForegroundColor Red
        }

        # --- STEP: Search & Validate AppID from steam_appid.txt, steam_api.ini, and steam_emu.ini ---
        Write-Host " [APPID-SEARCH] Searching for AppID files inside '$gameName'..." -ForegroundColor Gray
        
        $txtFile    = Get-ChildItem -Path $folderPath -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -ieq "steam_appid.txt" } | Select-Object -First 1
        $apiIniFile = Get-ChildItem -Path $folderPath -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -ieq "steam_api.ini" } | Select-Object -First 1
        $emuIniFile = Get-ChildItem -Path $folderPath -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -ieq "steam_emu.ini" } | Select-Object -First 1

        $extractedTxtId = $null
        $extractedApiIniId = $null
        $extractedEmuIniId = $null

        # Parse steam_appid.txt
        if ($txtFile) {
            try {
                $rawTxt = (Get-Content -Path $txtFile.FullName -Raw -ErrorAction Stop).Trim()
                if ($rawTxt -match '(\d+)') {
                    $extractedTxtId = [long]$matches[1]
                }
            } catch {
                Write-Host " [APPID-WARN] Failed to read '$($txtFile.FullName)'" -ForegroundColor Yellow
            }
        }

        # Parse steam_api.ini
        if ($apiIniFile) {
            try {
                $iniLines = Get-Content -Path $apiIniFile.FullName -ErrorAction Stop
                foreach ($line in $iniLines) {
                    if ($line -match '^\s*AppId\s*=\s*0*(\d+)\s*$') {
                        $extractedApiIniId = [long]$matches[1]
                        break
                    }
                }
            } catch {
                Write-Host " [APPID-WARN] Failed to read '$($apiIniFile.FullName)'" -ForegroundColor Yellow
            }
        }

        # Parse steam_emu.ini
        if ($emuIniFile) {
            try {
                $emuLines = Get-Content -Path $emuIniFile.FullName -ErrorAction Stop
                foreach ($line in $emuLines) {
                    if ($line -match '^\s*AppId\s*=\s*0*(\d+)\s*$') {
                        $extractedEmuIniId = [long]$matches[1]
                        break
                    }
                }
            } catch {
                Write-Host " [APPID-WARN] Failed to read '$($emuIniFile.FullName)'" -ForegroundColor Yellow
            }
        }

        # Collect all valid AppIDs found
        $detectedValues = @()
        if ($extractedTxtId)    { $detectedValues += $extractedTxtId }
        if ($extractedApiIniId) { $detectedValues += $extractedApiIniId }
        if ($extractedEmuIniId) { $detectedValues += $extractedEmuIniId }

        $finalAppId = $null

        if ($detectedValues.Count -gt 0) {
            $uniqueValues = $detectedValues | Select-Object -Unique

            if ($detectedValues.Count -gt 1) {
                Write-Host " [APPID-AUDIT] Multiple AppID sources found. Validating values..." -ForegroundColor Cyan
                if ($extractedTxtId)    { Write-Host "               -> steam_appid.txt Value : $extractedTxtId" -ForegroundColor Gray }
                if ($extractedApiIniId) { Write-Host "               -> steam_api.ini Value   : $extractedApiIniId" -ForegroundColor Gray }
                if ($extractedEmuIniId) { Write-Host "               -> steam_emu.ini Value   : $extractedEmuIniId" -ForegroundColor Gray }
            }

            if ($uniqueValues.Count -eq 1) {
                $finalAppId = $uniqueValues[0]
                if ($detectedValues.Count -gt 1) {
                    Write-Host " [APPID-SUCCESS] MATCH CONFIRMED across all sources! Valid AppID: $finalAppId" -ForegroundColor Green
                } else {
                    Write-Host " [APPID-FOUND] Found valid AppID: $finalAppId" -ForegroundColor Green
                }
            } else {
                Write-Host " [APPID-MISMATCH-ERROR] CRITICAL: AppID mismatch detected between config files in '$gameName'!" -ForegroundColor Red
                Write-Host "                        Skipping AppID registration for this game." -ForegroundColor Red
                $mismatchCount++
            }
        } else {
            Write-Host " [APPID-NOTFOUND] No valid AppID found in steam_appid.txt, steam_api.ini, or steam_emu.ini." -ForegroundColor DarkYellow
        }

        # Register AppID if valid and non-conflicting
        if ($finalAppId) {
            if (-not $registeredNames.Contains($gameName)) {
                $formattedAppEntry = "$gameName : $finalAppId"
                $newActiveEntries += $formattedAppEntry
                [void]$registeredNames.Add($gameName)
                $newAppIdsAdded++
                Write-Host " [SUCCESS] Registered '$formattedAppEntry' into Active Games section." -ForegroundColor Green
            } else {
                Write-Host " [APPID-SKIP] Game '$gameName' already exists in $STEAM_APPID_FILE." -ForegroundColor Yellow
            }
        }

    } else {
        Write-Host " [FAILED] No steam_api.dll or steam_api64.dll found in '$gameName'." -ForegroundColor DarkYellow
        $notFoundCount++
    }
}

# 4. Write updates back to steam appid.txt
if ($newActiveEntries.Count -gt 0 -or (-not (Test-Path $STEAM_APPID_FILE))) {
    Write-Host ""
    Write-Host "[PS-UPDATE] Updating $STEAM_APPID_FILE structure..." -ForegroundColor Cyan

    $allActive = $activeAppLines + $newActiveEntries
    $finalContent = @()

    if ($allActive.Count -gt 0) {
        $finalContent += $allActive
    }

    if ($preparedAppLines.Count -gt 0) {
        $finalContent += "-----------------------------"
        $finalContent += "PREPARED GAMES"
        $finalContent += "-----------------------------"
        $finalContent += $preparedAppLines
    }

    if ($doneAppLines.Count -gt 0) {
        $finalContent += "-----------------------------"
        $finalContent += "DONE GAMES"
        $finalContent += "-----------------------------"
        $finalContent += $doneAppLines
    }

    try {
        $finalContent | Set-Content -Path $STEAM_APPID_FILE -Encoding UTF8 -ErrorAction Stop
        Write-Host "[PS-SUCCESS] Updated $STEAM_APPID_FILE successfully with $newAppIdsAdded new AppID(s)." -ForegroundColor Green
    } catch {
        Write-Host "[PS-ERROR] Failed to save updates to $STEAM_APPID_FILE : $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "[PS-SUMMARY] PROCESS COMPLETED" -ForegroundColor Cyan
Write-Host "[PS-SUMMARY] Total Directories Scanned : $($subFolders.Count)" -ForegroundColor White
Write-Host "[PS-SUMMARY] New Games Added to Data  : $addedCount" -ForegroundColor Green
Write-Host "[PS-SUMMARY] New AppIDs Added to File : $newAppIdsAdded" -ForegroundColor Green
Write-Host "[PS-SUMMARY] AppID Mismatches (Errors): $mismatchCount" -ForegroundColor Red
Write-Host "[PS-SUMMARY] Skipped (Already Exist)  : $skippedCount" -ForegroundColor Yellow
Write-Host "[PS-SUMMARY] Skipped (DLL Not Found)  : $notFoundCount" -ForegroundColor DarkYellow
Write-Host "============================================================" -ForegroundColor Cyan

if ($mismatchCount -gt 0) {
    exit 2 # Signal BAT script about mismatches
} else {
    exit 0
}