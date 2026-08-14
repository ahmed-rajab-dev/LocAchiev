param (
    [Parameter(Mandatory=$true)]
    [string]$GamesPath
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Continue'

$GAMES_DATA_FILE = Join-Path $PSScriptRoot "games_data.txt"

Write-Host "[PS-INIT] Starting game directory scan process..." -ForegroundColor Cyan
Write-Host "[PS-INIT] Target Games Path : $GamesPath" -ForegroundColor Gray
Write-Host "[PS-INIT] Output Data File  : $GAMES_DATA_FILE" -ForegroundColor Gray
Write-Host ""

if (-not (Test-Path $GamesPath)) {
    Write-Host "[PS-ERROR] Target directory does not exist: $GamesPath" -ForegroundColor Red
    exit 1
}

# Load existing game names to avoid duplicates
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

# Fetch top-level subdirectories
Write-Host "[PS-LOG] Discovering subdirectories inside target path..." -ForegroundColor Cyan
try {
    $subFolders = Get-ChildItem -Path $GamesPath -Directory -ErrorAction Stop
} catch {
    Write-Host "[PS-ERROR] Failed to list directories in $GamesPath : $_" -ForegroundColor Red
    exit 1
}

Write-Host "[PS-LOG] Total subfolders found: $($subFolders.Count)" -ForegroundColor Green
Write-Host ""

$addedCount   = 0
$skippedCount = 0
$notFoundCount = 0

foreach ($folder in $subFolders) {
    $gameName   = $folder.Name
    $folderPath = $folder.FullName

    Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "[PS-SCAN] Checking Folder: '$gameName'" -ForegroundColor Cyan
    Write-Host "[PS-PATH] Full Path: $folderPath" -ForegroundColor Gray

    # Skip if game already registered in games_data.txt
    if ($existingGames.Contains($gameName)) {
        Write-Host "[PS-SKIP] Game '$gameName' is already present in games_data.txt. Skipping..." -ForegroundColor Yellow
        $skippedCount++
        continue
    }

    # Search recursively for steam_api.dll or steam_api64.dll
    Write-Host "[PS-SEARCH] Searching for steam_api.dll / steam_api64.dll inside '$gameName'..." -ForegroundColor Gray
    
    $foundApi = Get-ChildItem -Path $folderPath -Recurse -File -ErrorAction SilentlyContinue | 
                Where-Object { $_.Name -ieq "steam_api.dll" -or $_.Name -ieq "steam_api64.dll" } | 
                Select-Object -First 1

    if ($foundApi) {
        $apiDir = $foundApi.DirectoryName
        $achievementsPath = Join-Path $apiDir "achievements.json"
        
        Write-Host "[PS-FOUND] DLL Found at: $($foundApi.FullName)" -ForegroundColor Green
        Write-Host "[PS-FORMAT] Calculated RawAchiev_path: $achievementsPath" -ForegroundColor Green

        # Build entry text block
        $entryLines = @(
            "name = $gameName",
            "RawAchiev_path = $achievementsPath",
            "..."
        )

        try {
            Add-Content -Path $GAMES_DATA_FILE -Value $entryLines -Encoding UTF8 -ErrorAction Stop
            [void]$existingGames.Add($gameName)
            $addedCount++
            Write-Host "[PS-SUCCESS] Appended entry for '$gameName' to $GAMES_DATA_FILE" -ForegroundColor Green
        } catch {
            Write-Host "[PS-ERROR] Failed to write entry to $GAMES_DATA_FILE : $_" -ForegroundColor Red
        }
    } else {
        Write-Host "[PS-NOTFOUND] No steam_api.dll or steam_api64.dll found in '$gameName'." -ForegroundColor DarkYellow
        $notFoundCount++
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "[PS-SUMMARY] PROCESS COMPLETED" -ForegroundColor Cyan
Write-Host "[PS-SUMMARY] Total Directories Scanned : $($subFolders.Count)" -ForegroundColor White
Write-Host "[PS-SUMMARY] New Games Added          : $addedCount" -ForegroundColor Green
Write-Host "[PS-SUMMARY] Skipped (Already Exist)  : $skippedCount" -ForegroundColor Yellow
Write-Host "[PS-SUMMARY] Skipped (DLL Not Found)  : $notFoundCount" -ForegroundColor DarkYellow
Write-Host "============================================================" -ForegroundColor Cyan

exit 0