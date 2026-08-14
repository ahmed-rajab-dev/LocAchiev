$ErrorActionPreference = 'Stop'

$GAMES_FILE    = "games_data.txt"
$TEMPLATE_FILE = "template.html"
$APPID_FILE    = "steam appid.txt"
$INDEX_FILE    = "index.html"
$OUTPUT_DIR    = "Hall of Fame"
$GSE_BASE_PATH = "C:\Users\Ahmed Ragab\AppData\Roaming\GSE Saves"

$global:IndexUpdated = $false
$global:AddedCount   = 0

try {
    # 1. Read main template and games data
    Write-Host "[PS] Reading template file..." -ForegroundColor Cyan
    $template = Get-Content -Path $TEMPLATE_FILE -Raw -Encoding UTF8
    Write-Host "[PS] Template loaded successfully." -ForegroundColor Green

    Write-Host "[PS] Reading games_data.txt..." -ForegroundColor Cyan
    $lines = Get-Content -Path $GAMES_FILE -Encoding UTF8

    $gamesDict = @{}
    $current = @{}
    foreach ($line in $lines) {
        $line = $line.Trim()
        if ($line -eq '...') {
            if ($current.ContainsKey('name')) {
                $gamesDict[$current['name'].ToLower()] = $current
                $current = @{}
            }
            continue
        }
        if ($line -match '^name\s*=\s*(.+)$') { $current['name'] = $matches[1].Trim() }
        if ($line -match '^RawAchiev_path\s*=\s*(.+)$') { $current['raw_path'] = $matches[1].Trim() }
    }
    if ($current.ContainsKey('name')) {
        $gamesDict[$current['name'].ToLower()] = $current
    }

    # 2. Read steam appid.txt
    if (-not (Test-Path $APPID_FILE)) {
        Write-Host "[PS] ERROR: $APPID_FILE not found!" -ForegroundColor Red
        return
    }

    Write-Host "[PS] Reading $APPID_FILE..." -ForegroundColor Cyan
    $appidContent = Get-Content -Path $APPID_FILE -Encoding UTF8

    $activeAppIds = @()
    $doneAppIds   = @()
    $isBelowLine  = $false

    foreach ($line in $appidContent) {
        $trimmed = $line.Trim()
        if ($trimmed -match '^-{3,}$') {
            $isBelowLine = $true
            continue
        }
        if ([string]::IsNullOrWhiteSpace($trimmed)) { continue }

        if (-not $isBelowLine) {
            $activeAppIds += $line
        } else {
            $doneAppIds += $line
        }
    }

    Write-Host "[PS] Found $($activeAppIds.Count) game(s) to process above the line." -ForegroundColor Green

    $processed = 0
    $skipped   = 0
    $successfullyProcessedLines = @()

    if ($activeAppIds.Count -gt 0) {
        foreach ($appLine in $activeAppIds) {
            if ($appLine -match '^\s*(.+)\s*:\s*(\d+)\s*$') {
                $gameName  = $matches[1].Trim()
                $appId     = $matches[2].Trim()
                $lookupKey = $gameName.ToLower()

                Write-Host ""
                Write-Host "[PS] --- Processing: $gameName (AppID: $appId) ---" -ForegroundColor Yellow

                if (-not $gamesDict.ContainsKey($lookupKey)) {
                    Write-Host "[PS]   ERROR: Game '$gameName' not found in $GAMES_FILE!" -ForegroundColor Red
                    $skipped++
                    continue
                }

                $gameData = $gamesDict[$lookupKey]
                $rawPath  = $gameData['raw_path']

                # Deduce img path automatically
                $rawFileItem = Get-Item -Path $rawPath -ErrorAction SilentlyContinue
                if ($rawFileItem) {
                    $imgPath = Join-Path $rawFileItem.DirectoryName "img"
                } else {
                    $imgPath = $rawPath -replace 'achievements\.json$', 'img'
                }

                $gamePath = Join-Path $GSE_BASE_PATH "$appId\achievements.json"

                if (-not (Test-Path "$rawPath")) {
                    Write-Host "[PS]   ERROR: RAW file not found at: $rawPath" -ForegroundColor Red
                    $skipped++
                    continue
                }

                if (-not (Test-Path "$gamePath")) {
                    Write-Host "[PS]   ERROR: GSE GAME achievements.json not found at: $gamePath" -ForegroundColor Red
                    $skipped++
                    continue
                }

                try {
                    $json = Get-Content -Path "$gamePath" -Raw -Encoding UTF8
                    $raw  = Get-Content -Path "$rawPath" -Raw -Encoding UTF8
                } catch {
                    Write-Host "[PS]   ERROR reading JSON files: $_" -ForegroundColor Red
                    $skipped++
                    continue
                }

                # Base64 icon embedding
                Write-Host "[PS]   Checking Auto-detected IMG Path: $imgPath" -ForegroundColor Gray
                $iconMap = @{}
                if (Test-Path "$imgPath") {
                    $files = Get-ChildItem -Path "$imgPath" -File
                    $fileCount = 0
                    foreach ($file in $files) {
                        try {
                            $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
                            $base64 = [Convert]::ToBase64String($bytes)
                            $ext = $file.Extension.Replace('.','').ToLower()
                            if ($ext -eq 'jpg') { $ext = 'jpeg' }
                            $mime = 'image/' + $ext
                            $iconMap[$file.Name.ToLower()] = 'data:' + $mime + ';base64,' + $base64
                            $fileCount++
                        } catch {
                            Write-Host "[PS]   WARNING: Failed to convert $($file.Name)" -ForegroundColor Yellow
                        }
                    }
                    Write-Host "[PS]   Successfully embedded $fileCount images." -ForegroundColor Green
                } else {
                    Write-Host "[PS]   WARNING: img folder not found. No icons embedded." -ForegroundColor Yellow
                }

                $iconMapJson = $iconMap | ConvertTo-Json -Compress
                if (-not $iconMapJson) { $iconMapJson = '{}' }

                $outputHtml = $template
                $outputHtml = $outputHtml.Replace('/*JSON_DATA_PLACEHOLDER*/{}', $json)
                $outputHtml = $outputHtml.Replace('/*RAW_DATA_PLACEHOLDER*/[]', $raw)
                $outputHtml = $outputHtml.Replace('/*ICON_MAP_PLACEHOLDER*/{}', $iconMapJson)

                # Safe file name
                $safeName = $gameName -replace '[^a-zA-Z0-9]', '_'
                $outFile = Join-Path $OUTPUT_DIR "$safeName.html"

                [System.IO.File]::WriteAllText($outFile, $outputHtml, [System.Text.Encoding]::UTF8)

                Write-Host "[PS]   SUCCESS: $gameName built successfully!" -ForegroundColor Green
                $processed++
                $successfullyProcessedLines += $appLine
            }
        }

        # Update steam appid.txt
        if ($successfullyProcessedLines.Count -gt 0) {
            $remainingActive = $activeAppIds | Where-Object { $successfullyProcessedLines -notcontains $_ }
            $newContent = @()
            if ($remainingActive.Count -gt 0) { $newContent += $remainingActive }
            $newContent += "-----------------------------"
            $newContent += $doneAppIds
            $newContent += $successfullyProcessedLines
            $newContent | Set-Content -Path $APPID_FILE -Encoding UTF8
        }
    }

    $global:AddedCount = $processed

    # 3. Update index.html
    Write-Host ""
    Write-Host "[PS] Updating index.html with all games in $OUTPUT_DIR..." -ForegroundColor Cyan

    if (Test-Path $INDEX_FILE) {
        $htmlFiles = Get-ChildItem -Path $OUTPUT_DIR -Filter "*.html"

        if ($htmlFiles.Count -eq 0) {
            $cardsHtml = '<div class="empty"><h3>NO GAMES YET</h3><p>No games have been added to the Hall of Fame yet</p></div>'
        } else {
            $cardsHtml = ""
            foreach ($file in $htmlFiles) {
                $displayName = $file.BaseName -replace '_', ' '
                
                # مسار محلي مباشر ونظيف دون رموز غريبة أو تشفير زائد
                $targetPath = "$OUTPUT_DIR/$($file.Name)"

                $cardsHtml += @"
    <a class="game-card" href="$targetPath">
      <div class="game-info">
        <div class="game-icon-box"></div>
        <div class="game-title">$displayName</div>
      </div>
      <div class="game-foot">
        <span>VIEW LOG</span>
        <span class="badge-launch">OPEN</span>
      </div>
    </a>
"@
            }
        }

        $indexContent = Get-Content -Path $INDEX_FILE -Raw -Encoding UTF8

        if ($indexContent -match '<!-- GAMES_LIST_PLACEHOLDER -->') {
            $newIndexContent = $indexContent -replace '<!-- GAMES_LIST_PLACEHOLDER -->', $cardsHtml
        } else {
            $newIndexContent = $indexContent -replace '(?s)<main class="game-grid">.*?</main>', "<main class=`"game-grid`">$cardsHtml</main>"
        }

        [System.IO.File]::WriteAllText($INDEX_FILE, $newIndexContent, [System.Text.Encoding]::UTF8)
        Write-Host "[PS] index.html updated successfully!" -ForegroundColor Green
        $global:IndexUpdated = $true
    } else {
        Write-Host "[PS] WARNING: $INDEX_FILE not found! Skipping index update." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "[PS] BUILD COMPLETE!" -ForegroundColor Cyan
    Write-Host "[PS] Games Processed: $processed" -ForegroundColor Green
    Write-Host "[PS] Games Skipped: $skipped" -ForegroundColor Yellow
    Write-Host "[PS] Output folder: $OUTPUT_DIR" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Cyan

} catch {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Red
    Write-Host "[PS] CRITICAL ERROR!" -ForegroundColor Red
    Write-Host "[PS] Error Message: $_" -ForegroundColor Red
    Write-Host "============================================================" -ForegroundColor Red
    exit 1
}