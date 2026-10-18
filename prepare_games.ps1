$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$APPID_FILE      = Join-Path $PSScriptRoot "steam appid.txt"
$GAMES_DATA      = Join-Path $PSScriptRoot "games_data.txt"
$GBE_DIR         = Join-Path $PSScriptRoot "gbe_settings_generator"
$OUTPUT_DIR      = Join-Path $GBE_DIR "_OUTPUT"
$OUTPUT_DONE_DIR = Join-Path $GBE_DIR "_OUTPUT_DONE"

Write-Host "[PS-INIT] Game Preparation & Deployment Engine Started." -ForegroundColor Cyan

# 1. Parse games_data.txt to map Game Name -> (Raw Directory Path, Steam API Type, Unity Flag)
if (-not (Test-Path $GAMES_DATA)) {
    Write-Host "[PS-ERROR] '$GAMES_DATA' file not found!" -ForegroundColor Red
    exit 1
}

$gameInfoMap = @{}
$lines = Get-Content -Path $GAMES_DATA -Encoding UTF8
$current = @{}

foreach ($line in $lines) {
    $trimmed = $line.Trim()
    if ($trimmed -eq '...') {
        if ($current.ContainsKey('name')) {
            $gameInfoMap[$current['name'].ToLower()] = $current
            $current = @{}
        }
        continue
    }
    if ($trimmed -match '^name\s*=\s*(.+)$')       { $current['name'] = $matches[1].Trim() }
    if ($trimmed -match '^RawAchiev_path\s*=\s*(.+)$') { $current['path'] = $matches[1].Trim() }
    if ($trimmed -match '^steam_api\s*=\s*(.+)$')     { $current['api']  = $matches[1].Trim() }
    if ($trimmed -match '^unity_game\s*=\s*(.+)$')    { $current['unity'] = $matches[1].Trim() }
}
if ($current.ContainsKey('name')) {
    $gameInfoMap[$current['name'].ToLower()] = $current
}

# 2. Parse steam appid.txt into Sections
if (-not (Test-Path $APPID_FILE)) {
    Write-Host "[PS-ERROR] '$APPID_FILE' file not found!" -ForegroundColor Red
    exit 1
}

$rawAppLines   = Get-Content -Path $APPID_FILE -Encoding UTF8
$activeGames   = @()
$preparedGames = @()
$doneGames     = @()

$currentSection = "ACTIVE"

foreach ($line in $rawAppLines) {
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
        $item = @{
            Raw   = $trimmed
            Name  = $matches[1].Trim()
            AppId = $matches[2].Trim()
        }
        switch ($currentSection) {
            "ACTIVE"   { $activeGames += $item }
            "PREPARED" { $preparedGames += $item }
            "DONE"     { $doneGames += $item }
        }
    }
}

$appToGameMap = @{}
foreach ($g in ($activeGames + $preparedGames + $doneGames)) {
    $appToGameMap[$g.AppId] = $g
}

# 3. Prompt for Unity Game Processing First
Write-Host ""
$unityInput = Read-Host "Do you want to process Unity games as well? (y/N) [Default: n]"

$includeUnity = $false
if (-not [string]::IsNullOrWhiteSpace($unityInput) -and $unityInput.Trim() -ieq "y") {
    $includeUnity = $true
    Write-Host "[PS-FILTER] Mode set: ALL games (Unity & Non-Unity) will be available." -ForegroundColor Magenta
} else {
    Write-Host "[PS-FILTER] Mode set: Unity games are EXCLUDED from selection." -ForegroundColor Cyan
}

# Filter activeGames list based on choice
$filteredActiveGames = @()
foreach ($g in $activeGames) {
    $lookupKey = $g.Name.ToLower()
    $isUnity = $false

    if ($gameInfoMap.ContainsKey($lookupKey) -and $gameInfoMap[$lookupKey].ContainsKey('unity')) {
        if ($gameInfoMap[$lookupKey]['unity'] -eq "True") {
            $isUnity = $true
        }
    }

    # If user chose 'y', include ALL. If 'n'/Enter, exclude Unity games.
    if ($includeUnity -or (-not $isUnity)) {
        $filteredActiveGames += $g
    }
}

# 4. Interactive User Selection
Write-Host ""
if ($filteredActiveGames.Count -gt 0) {
    Write-Host "============================================================" -ForegroundColor Cyan
    if ($includeUnity) {
        Write-Host "             AVAILABLE UN-PREPARED GAMES (ALL)              " -ForegroundColor Magenta
    } else {
        Write-Host "           AVAILABLE UN-PREPARED NON-UNITY GAMES            " -ForegroundColor Cyan
    }
    Write-Host "============================================================" -ForegroundColor Cyan
    for ($i = 0; $i -lt $filteredActiveGames.Count; $i++) {
        $game = $filteredActiveGames[$i]
        Write-Host ("  [{0,2}] {1} (AppID: {2})" -f ($i + 1), $game.Name, $game.AppId) -ForegroundColor White
    }
    Write-Host "============================================================" -ForegroundColor Cyan
} else {
    Write-Host "[PS-INFO] No matching active games found awaiting selection for this filter." -ForegroundColor Yellow
}

Write-Host ""
$userInput = Read-Host "Select games (Enter = Skip New Gen | 'all' = Select All Displayed | Numbers e.g. 1 3)"

$toGenerate = @()

if ([string]::IsNullOrWhiteSpace($userInput)) {
    Write-Host "[PS-INFO] Selection SKIPPED by user. Proceeding directly to mandatory audit..." -ForegroundColor Yellow
} elseif ($userInput.Trim() -ieq "all") {
    $toGenerate = $filteredActiveGames
    Write-Host "[PS-INFO] User selected ALL displayed active games for processing." -ForegroundColor Cyan
} else {
    $tokens = $userInput.Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)
    foreach ($token in $tokens) {
        if ($token -match '^\d+$') {
            $idx = [int]$token - 1
            if ($idx -ge 0 -and $idx -lt $filteredActiveGames.Count) {
                $toGenerate += $filteredActiveGames[$idx]
            } else {
                Write-Host "[PS-WARN] Out of bounds selection index ignored: $token" -ForegroundColor Yellow
            }
        }
    }
}

# 5. Filter pre-existing output folders
$filteredToGenerate = @()
foreach ($game in $toGenerate) {
    $targetFolder = Join-Path $OUTPUT_DIR $game.AppId
    if (Test-Path $targetFolder) {
        Write-Host "[PS-SKIP] Skipped GBE generation for '$($game.Name)': Output folder already exists." -ForegroundColor Yellow
    } else {
        $filteredToGenerate += $game
    }
}

# 6. Run GBE Generator Command
if ($filteredToGenerate.Count -gt 0) {
    $appIdList = ($filteredToGenerate | ForEach-Object { $_.AppId }) -join " "
    Write-Host ""
    Write-Host "[PS-EXEC] Invoking GBE Generator for AppIDs: $appIdList" -ForegroundColor Cyan

    try {
        Push-Location -Path $GBE_DIR

        $genCmd = "generate_emu_config"
        if (Test-Path "generate_emu_config.bat") { $genCmd = ".\generate_emu_config.bat" }
        elseif (Test-Path "generate_emu_config.exe") { $genCmd = ".\generate_emu_config.exe" }
        elseif (Test-Path "generate_emu_config.cmd") { $genCmd = ".\generate_emu_config.cmd" }

        $process = Start-Process -FilePath "cmd.exe" -ArgumentList "/c $genCmd $appIdList" -NoNewWindow -Wait -PassThru
        Write-Host "[PS-SUCCESS] GBE Generator execution finished." -ForegroundColor Green
    } catch {
        Write-Host "[PS-ERROR] Failed to execute GBE generator script: $_" -ForegroundColor Red
    } finally {
        Pop-Location
    }
}

# 7. MANDATORY AUDIT & DEPLOYMENT PHASE (steam_settings & API DLL)
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "       MANDATORY AUDIT & STEAM_SETTINGS / API DEPLOYMENT     " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if (-not (Test-Path $OUTPUT_DIR)) {
    Write-Host "[PS-WARN] Output directory '$OUTPUT_DIR' does not exist yet." -ForegroundColor Yellow
} else {
    $outputFolders = Get-ChildItem -Path $OUTPUT_DIR -Directory

    if ($outputFolders.Count -eq 0) {
        Write-Host "[PS-INFO] Output folder is empty." -ForegroundColor Yellow
    } else {
        # Ensure _OUTPUT_DONE exists
        if (-not (Test-Path $OUTPUT_DONE_DIR)) {
            New-Item -ItemType Directory -Path $OUTPUT_DONE_DIR -Force | Out-Null
            Write-Host "[PS-INIT] Created folder: $OUTPUT_DONE_DIR" -ForegroundColor Cyan
        }

        foreach ($folder in $outputFolders) {
            $appId = $folder.Name
            Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
            Write-Host "[AUDIT] Checking Output Folder for AppID: $appId" -ForegroundColor Cyan

            if (-not $appToGameMap.ContainsKey($appId)) {
                Write-Host "  [WARNING] AppID $appId not in '$APPID_FILE'. Skipping..." -ForegroundColor Yellow
                continue
            }

            $gameObj   = $appToGameMap[$appId]
            $gameName  = $gameObj.Name
            $lookupKey = $gameName.ToLower()

            Write-Host "  [INFO] Matched Game: '$gameName'" -ForegroundColor White

            if (-not $gameInfoMap.ContainsKey($lookupKey)) {
                Write-Host "  [ERROR] Game '$gameName' not found in '$GAMES_DATA'!" -ForegroundColor Red
                continue
            }

            $gameData      = $gameInfoMap[$lookupKey]
            $targetGameDir = $gameData['path']
            $apiType       = $gameData['api']
            $isUnity       = $gameData['unity']

            Write-Host "  [TYPE] Target API Type: steam_api=$apiType | Unity: $isUnity" -ForegroundColor Gray

            if (-not (Test-Path $targetGameDir)) {
                Write-Host "  [ERROR] Target installation folder does not exist at: $targetGameDir" -ForegroundColor Red
                continue
            }

            # --- Logic to Determine Deployment Paths ---
            $deployPaths = @($targetGameDir)
            $steamSettingsTarget = $targetGameDir # Default location for steam_settings

            # If it's a Unity game, find the Root folder containing *_Data
            if ($isUnity -eq "True") {
                $currSearchPath = $targetGameDir
                $unityRootPath = $null

                while (-not [string]::IsNullOrEmpty($currSearchPath)) {
                    $dataDir = Get-ChildItem -Path $currSearchPath -Directory -Filter "*_Data" -ErrorAction SilentlyContinue | Select-Object -First 1
                    if ($dataDir) {
                        $unityRootPath = $currSearchPath
                        break
                    }
                    $parentPath = Split-Path $currSearchPath -Parent
                    if ($parentPath -eq $currSearchPath) { break } # Reached drive root
                    $currSearchPath = $parentPath
                }

                # If root is found and is different from the deep DLL path
                if ($unityRootPath -and $unityRootPath -ne $targetGameDir) {
                    $deployPaths += $unityRootPath
                    $steamSettingsTarget = $unityRootPath # Override steam_settings location to ONLY be the Root
                    Write-Host "  [UNITY] Found Unity Root directory: $unityRootPath" -ForegroundColor Cyan
                }
            }

            # --- A. COPY steam_settings (Executed ONCE to the appropriate target) ---
            Write-Host "  [DEPLOY-SETTINGS] Target Path: $steamSettingsTarget" -ForegroundColor Magenta
            $srcSteamSettings  = Join-Path $folder.FullName "steam_settings"
            $destSteamSettings = Join-Path $steamSettingsTarget "steam_settings"

            if (Test-Path $srcSteamSettings) {
                Write-Host "    [COPY] Copying 'steam_settings'..." -ForegroundColor Yellow
                try {
                    if (Test-Path $destSteamSettings) {
                        Remove-Item -Path $destSteamSettings -Recurse -Force -ErrorAction Stop
                    }
                    Copy-Item -Path $srcSteamSettings -Destination $destSteamSettings -Recurse -Force -ErrorAction Stop
                    Write-Host "    [SUCCESS] 'steam_settings' copied successfully!" -ForegroundColor Green
                } catch {
                    Write-Host "    [ERROR] Failed to copy 'steam_settings': $_" -ForegroundColor Red
                }
            }

            # --- B. Backup & COPY API DLL & Create api_new (Executed for ALL target paths) ---
            foreach ($deployPath in $deployPaths) {
                Write-Host "  [DEPLOY-DLL] Processing Path: $deployPath" -ForegroundColor Magenta

                $dllFileName = if ($apiType -eq "64") { "steam_api64.dll" } else { "steam_api.dll" }
                $srcDllPath  = Join-Path $folder.FullName $dllFileName
                $destDllPath = Join-Path $deployPath $dllFileName
                
                $apiOldDir   = Join-Path $deployPath "api_old"
                $apiNewDir   = Join-Path $deployPath "api_new"

                if (Test-Path $srcDllPath) {
                    # 1. Backup existing old API DLL (Only if it exists in this specific path)
                    if (Test-Path $destDllPath) {
                        Write-Host "    [BACKUP] Backing up existing '$dllFileName' to 'api_old'..." -ForegroundColor Yellow
                        try {
                            if (-not (Test-Path $apiOldDir)) {
                                New-Item -ItemType Directory -Path $apiOldDir -Force | Out-Null
                            }
                            $backupPath = Join-Path $apiOldDir $dllFileName
                            Move-Item -Path $destDllPath -Destination $backupPath -Force -ErrorAction Stop
                            Write-Host "    [SUCCESS] Old API backed up to: $backupPath" -ForegroundColor Green
                        } catch {
                            Write-Host "    [ERROR] Failed to backup old API: $_" -ForegroundColor Red
                        }
                    }

                    # 2. Copy new generated API DLL to target path
                    Write-Host "    [DEPLOY] Copying new '$dllFileName'..." -ForegroundColor Yellow
                    try {
                        Copy-Item -Path $srcDllPath -Destination $destDllPath -Force -ErrorAction Stop
                        Write-Host "    [SUCCESS] '$dllFileName' deployed successfully!" -ForegroundColor Green

                        # 3. Create api_new and store a clean copy of the new DLL there
                        if (-not (Test-Path $apiNewDir)) {
                            New-Item -ItemType Directory -Path $apiNewDir -Force | Out-Null
                        }
                        $newApiBackupPath = Join-Path $apiNewDir $dllFileName
                        Copy-Item -Path $srcDllPath -Destination $newApiBackupPath -Force -ErrorAction Stop
                        Write-Host "    [SUCCESS] Placed a copy of '$dllFileName' inside 'api_new' folder." -ForegroundColor Green

                    } catch {
                        Write-Host "    [ERROR] Failed to deploy new API DLL or api_new: $_" -ForegroundColor Red
                    }
                } else {
                    Write-Host "    [WARNING] API file '$dllFileName' not found in source: $srcDllPath" -ForegroundColor Yellow
                }
            }

            # --- C. Archive to _OUTPUT_DONE with Game Name ---
            $safeGameName = $gameName -replace '[\\/:*?"<>|]', '_'
            $doneDestination = Join-Path $OUTPUT_DONE_DIR $safeGameName

            Write-Host "  [ARCHIVE] Moving AppID folder to _OUTPUT_DONE as '$safeGameName'..." -ForegroundColor Yellow
            try {
                if (Test-Path $doneDestination) {
                    Remove-Item -Path $doneDestination -Recurse -Force -ErrorAction Stop
                }
                Move-Item -Path $folder.FullName -Destination $doneDestination -Force -ErrorAction Stop
                Write-Host "  [SUCCESS] Output folder moved and renamed to: $doneDestination" -ForegroundColor Green
            } catch {
                Write-Host "  [ERROR] Failed to archive folder to _OUTPUT_DONE: $_" -ForegroundColor Red
            }
        }
    }
}

# 8. Restructure & Update steam appid.txt
Write-Host ""
Write-Host "[PS-UPDATE] Re-evaluating game preparation status in $APPID_FILE..." -ForegroundColor Cyan

$newActive = @()
$newPrepared = @($preparedGames)

foreach ($g in $activeGames) {
    $generatedFolder = Join-Path $OUTPUT_DIR $g.AppId
    $doneFolder      = Join-Path $OUTPUT_DONE_DIR ($g.Name -replace '[\\/:*?"<>|]', '_')

    if ((Test-Path $generatedFolder) -or (Test-Path $doneFolder)) {
        if (-not ($newPrepared | Where-Object { $_.AppId -eq $g.AppId })) {
            $newPrepared += $g
        }
    } else {
        $newActive += $g
    }
}

$finalLines = @()

if ($newActive.Count -gt 0) {
    foreach ($g in $newActive) { $finalLines += $g.Raw }
}

if ($newPrepared.Count -gt 0) {
    $finalLines += "-----------------------------"
    $finalLines += "PREPARED GAMES"
    $finalLines += "-----------------------------"
    foreach ($g in $newPrepared) { $finalLines += $g.Raw }
}

if ($doneGames.Count -gt 0) {
    $finalLines += "-----------------------------"
    $finalLines += "DONE GAMES"
    $finalLines += "-----------------------------"
    foreach ($g in $doneGames) { $finalLines += $g.Raw }
}

try {
    $finalLines | Set-Content -Path $APPID_FILE -Encoding UTF8 -ErrorAction Stop
    Write-Host "[PS-SUCCESS] '$APPID_FILE' successfully updated!" -ForegroundColor Green
} catch {
    Write-Host "[PS-ERROR] Failed to write updates to '$APPID_FILE': $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "[PS-SUMMARY] PREPARATION & DEPLOYMENT FLOW COMPLETED" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

exit 0