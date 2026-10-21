import base64
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Resolve working base directory (works for both .py script and frozen .exe)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent.resolve()
else:
    BASE_DIR = Path(__file__).parent.resolve()

console = Console()


def download_cover_image(image_url, dest_file):
    """
    Downloads cover banner image locally so games can be viewed completely offline.
    """
    if not image_url or dest_file.exists():
        return dest_file.exists()

    try:
        req = urllib.request.Request(
            image_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            content = resp.read()
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_file, "wb") as f:
                f.write(content)
        return True
    except Exception as e:
        console.print(f"  [dim yellow][IMG-WARN] Failed downloading cover ({dest_file.name}): {e}[/dim yellow]")
        return False


def get_or_create_game_done_folder(output_done_dir, game):
    """
    Finds the matching game directory inside _OUTPUT_DONE or creates a safe named one.
    """
    name = game.get("name", "")
    folder_name = game.get("folder_name", "")
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', name)

    if output_done_dir.exists():
        existing_folders = [d for d in output_done_dir.iterdir() if d.is_dir()]

        # 1. Exact match with folder_name or name
        for d in existing_folders:
            if folder_name and d.name.lower() == folder_name.lower():
                return d
            if d.name.lower() == name.lower() or d.name.lower() == safe_name.lower():
                return d

        # 2. Substring match
        for d in existing_folders:
            d_lower = d.name.lower()
            n_lower = name.lower()
            if d_lower in n_lower or n_lower in d_lower:
                return d

    # 3. Create new target folder if none exists
    target = output_done_dir / safe_name
    target.mkdir(parents=True, exist_ok=True)
    return target


def ensure_game_cover_in_output_done(output_done_dir, game):
    """
    Checks if game cover already exists inside _OUTPUT_DONE/<game_folder>/cover/
    If not, downloads it. Returns the relative path for index.html.
    """
    game_folder = get_or_create_game_done_folder(output_done_dir, game)
    cover_dir = game_folder / "cover"
    cover_file = cover_dir / "cover.jpg"

    rel_path = f"gbe_settings_generator/_OUTPUT_DONE/{game_folder.name}/cover/cover.jpg"

    # Check if cover already exists
    if cover_file.exists():
        return rel_path, False

    # Also check if any existing image is in cover/
    if cover_dir.exists():
        existing_imgs = list(cover_dir.glob("*.jpg")) + list(cover_dir.glob("*.png"))
        if existing_imgs:
            return f"gbe_settings_generator/_OUTPUT_DONE/{game_folder.name}/cover/{existing_imgs[0].name}", False

    # Download if missing and header_image exists
    header_url = game.get("header_image")
    if header_url:
        console.print(f" [dim]Downloading cover for '{game.get('name')}' into {game_folder.name}/cover/...[/dim]")
        if download_cover_image(header_url, cover_file):
            return rel_path, True

    return None, False


def find_game_steam_settings(game):
    """
    Finds the steam_settings directory containing achievements.json.
    Accurately handles Unity games (where steam_settings is located in the game root directory),
    regular games, and fallbacks to _OUTPUT_DONE or _OUTPUT.
    Returns: (raw_achievements_json_path, img_directory_path) or (None, None)
    """
    raw_path_str = game.get("raw_path", "")
    game_name = game.get("name", "")
    app_id = str(game.get("appid", ""))
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", game_name)

    # 1. Search in raw_path and all parent directories up to game root or drive root
    if raw_path_str:
        curr = Path(raw_path_str)
        while curr and curr.parent != curr:
            cand = curr / "steam_settings"
            if cand.exists() and (cand / "achievements.json").exists():
                img_cand = cand / "img"
                if not img_cand.exists() or not img_cand.is_dir():
                    # Fallback to _OUTPUT_DONE for icons if not inside game folder
                    done_img = BASE_DIR / "gbe_settings_generator" / "_OUTPUT_DONE" / safe_name / "steam_settings" / "img"
                    if done_img.exists() and done_img.is_dir():
                        img_cand = done_img
                return cand / "achievements.json", img_cand

            if curr.name.lower() in ["1.games", "games", "steamapps", "common"]:
                break
            curr = curr.parent

    # 2. Fallback: Search in _OUTPUT_DONE/<safe_name>/steam_settings
    done_cand = BASE_DIR / "gbe_settings_generator" / "_OUTPUT_DONE" / safe_name / "steam_settings"
    if done_cand.exists() and (done_cand / "achievements.json").exists():
        return done_cand / "achievements.json", done_cand / "img"

    # 3. Fallback: Search in _OUTPUT/<app_id>/steam_settings
    out_cand = BASE_DIR / "gbe_settings_generator" / "_OUTPUT" / app_id / "steam_settings"
    if out_cand.exists() and (out_cand / "achievements.json").exists():
        return out_cand / "achievements.json", out_cand / "img"

    return None, None


def get_game_achievement_stats(gse_base_path, app_id, default_total=0):
    """
    Calculates unlocked and total achievements from GSE Saves JSON file.
    Returns (unlocked_count, total_count, percentage).
    """
    if not app_id:
        return 0, default_total, 0

    gse_ach_file = gse_base_path / str(app_id) / "achievements.json"
    if gse_ach_file.exists():
        try:
            with open(gse_ach_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if isinstance(data, dict):
                unlocked = sum(
                    1 for v in data.values()
                    if isinstance(v, dict) and (v.get("earned") is True or v.get("earned_time", 0) > 0)
                )
                total = len(data) if len(data) > 0 else default_total
                pct = round((unlocked / total) * 100) if total > 0 else 0
                return unlocked, total, pct
        except Exception:
            pass

    pct = 0
    return 0, default_total, pct


def build_achievements():
    console.print(
        Panel.fit(
            "[bold cyan]Achievement Standalone Builder & Web Publisher (Sketch UI)[/bold cyan]\n"
            f"[dim]Base Directory: {BASE_DIR}[/dim]",
            border_style="cyan",
        )
    )

    games_json_file = BASE_DIR / "games.json"
    template_file = BASE_DIR / "template.html"
    index_file = BASE_DIR / "index.html"
    output_dir = BASE_DIR / "Hall of Fame"
    output_done_dir = BASE_DIR / "gbe_settings_generator" / "_OUTPUT_DONE"

    appdata = os.environ.get("APPDATA")
    if appdata:
        gse_base_path = Path(appdata) / "GSE Saves"
    else:
        gse_base_path = Path.home() / "AppData" / "Roaming" / "GSE Saves"

    # -------------------------------------------------------------
    # 0. Check Required Files
    # -------------------------------------------------------------
    missing_files = []
    if not games_json_file.exists():
        missing_files.append(str(games_json_file.name))
    if not template_file.exists():
        missing_files.append(str(template_file.name))

    if missing_files:
        console.print(
            Panel.fit(
                f"[bold red]Critical Error: Missing required file(s):[/bold red]\n"
                + "\n".join(f" - {f}" for f in missing_files),
                border_style="red",
            )
        )
        return

    # -------------------------------------------------------------
    # 1. Read main template and games database
    # -------------------------------------------------------------
    console.print("\n[bold cyan][1/4] Loading template and database...[/bold cyan]")
    try:
        with open(template_file, "r", encoding="utf-8") as f:
            template = f.read()
        console.print(" [bold green][OK][/bold green] Template loaded successfully.")
    except Exception as e:
        console.print(f" [bold red][FAILED][/bold red] Error reading template: {e}")
        return

    try:
        with open(games_json_file, "r", encoding="utf-8-sig") as f:
            games = json.load(f)
        console.print(
            f" [bold green][OK][/bold green] Loaded database with {len(games)} game entry(ies)."
        )
    except Exception as e:
        console.print(f" [bold red][FAILED][/bold red] Error reading games.json: {e}")
        return

    # -------------------------------------------------------------
    # 2. Filter PREPARED games
    # -------------------------------------------------------------
    console.print("\n[bold cyan][2/4] Identifying PREPARED games...[/bold cyan]")
    prepared_games = [
        g for g in games.values()
        if g.get("status") == "prepared" and g.get("appid")
    ]

    console.print(
        f" [bold green][OK][/bold green] Found [bold yellow]{len(prepared_games)}[/bold yellow] game(s) ready for build."
    )

    # -------------------------------------------------------------
    # 3. Process PREPARED Games
    # -------------------------------------------------------------
    processed = 0
    skipped = 0

    if prepared_games:
        console.print("\n[bold cyan][3/4] Building achievement pages...[/bold cyan]")
        for game in prepared_games:
            game_name = game.get("name", "Unknown Game")
            app_id = str(game.get("appid"))
            console.print(f"\n [bold yellow]--- Processing: {game_name} (AppID: {app_id}) ---[/bold yellow]")

            raw_path, img_path = find_game_steam_settings(game)
            game_path = gse_base_path / app_id / "achievements.json"

            if not raw_path or not raw_path.exists():
                console.print(f"  [bold red]ERROR:[/bold red] RAW achievements.json not found for: {game_name}")
                skipped += 1
                continue

            if not game_path.exists():
                console.print(
                    f"  [bold red]ERROR:[/bold red] GSE achievements.json not found at: {game_path}"
                )
                skipped += 1
                continue

            try:
                with open(game_path, "r", encoding="utf-8") as f:
                    json_content = f.read()
                with open(raw_path, "r", encoding="utf-8") as f:
                    raw_content = f.read()
            except Exception as e:
                console.print(f"  [bold red]ERROR reading JSON files:[/bold red] {e}")
                skipped += 1
                continue

            # Base64 icon embedding
            icon_map = {}
            if img_path.exists() and img_path.is_dir():
                file_count = 0
                for img_file in img_path.iterdir():
                    if img_file.is_file():
                        try:
                            with open(img_file, "rb") as bf:
                                b64 = base64.b64encode(bf.read()).decode("utf-8")
                            ext = img_file.suffix.lstrip(".").lower()
                            if ext == "jpg":
                                ext = "jpeg"
                            mime = f"image/{ext}"
                            icon_map[img_file.name.lower()] = f"data:{mime};base64,{b64}"
                            file_count += 1
                        except Exception as ie:
                            console.print(f"  [yellow]WARNING: Failed to encode image {img_file.name}: {ie}[/yellow]")
                console.print(f"  [bold green]Embedded:[/bold green] {file_count} images successfully.")
            else:
                console.print("  [yellow]WARNING: img folder not found. No icons embedded.[/yellow]")

            icon_map_json = json.dumps(icon_map, separators=(",", ":"))

            # Build HTML content
            output_html = template
            output_html = output_html.replace("/*JSON_DATA_PLACEHOLDER*/{}", json_content)
            output_html = output_html.replace("/*RAW_DATA_PLACEHOLDER*/[]", raw_content)
            output_html = output_html.replace("/*ICON_MAP_PLACEHOLDER*/{}", icon_map_json)

            output_dir.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r'[^a-zA-Z0-9]', '_', game_name)
            html_filename = f"{safe_name}.html"
            out_file = output_dir / html_filename

            try:
                with open(out_file, "w", encoding="utf-8") as f:
                    f.write(output_html)
                console.print(f"  [bold green]SUCCESS:[/bold green] Built page: {out_file.name}")

                # Update status in database
                game["status"] = "done"
                game["html_file"] = html_filename
                processed += 1
            except Exception as e:
                console.print(f"  [bold red]ERROR writing output file:[/bold red] {e}")
                skipped += 1

    # -------------------------------------------------------------
    # 4. Check & Download Covers inside _OUTPUT_DONE/<game>/cover/
    # -------------------------------------------------------------
    console.print("\n[bold cyan][4/5] Checking and caching game covers inside _OUTPUT_DONE...[/bold cyan]")
    output_done_dir.mkdir(parents=True, exist_ok=True)
    downloaded_covers = 0
    already_cached = 0

    for game in games.values():
        if game.get("status") == "done" and game.get("header_image"):
            cover_path, was_downloaded = ensure_game_cover_in_output_done(output_done_dir, game)
            if cover_path:
                game["cover_local"] = cover_path
                if was_downloaded:
                    downloaded_covers += 1
                else:
                    already_cached += 1

    if downloaded_covers > 0:
        console.print(f" [bold green][OK][/bold green] Downloaded {downloaded_covers} new cover(s) to '_OUTPUT_DONE/<game>/cover/'.")
    console.print(f" [bold green][OK][/bold green] {already_cached} cover(s) verified already cached in '_OUTPUT_DONE'.")

    # Save database updates
    try:
        with open(games_json_file, "w", encoding="utf-8") as f:
            json.dump(games, f, indent=2, ensure_ascii=False)
        console.print(" [bold green][OK][/bold green] Database updated with cover paths and statuses.")
    except Exception as e:
        console.print(f" [bold red][ERROR][/bold red] Failed updating database: {e}")

    # -------------------------------------------------------------
    # 5. Update index.html with Sketch Layout UI
    # -------------------------------------------------------------
    console.print("\n[bold cyan][5/5] Publishing index.html with Sketch Layout UI...[/bold cyan]")
    if index_file.exists():
        html_files = list(output_dir.glob("*.html")) if output_dir.exists() else []

        done_games_map = {}
        for g in games.values():
            if g.get("html_file"):
                done_games_map[g["html_file"].lower()] = g
            safe_k = re.sub(r'[^a-zA-Z0-9]', '_', g.get("name", "")).lower() + ".html"
            done_games_map[safe_k] = g

        if not html_files:
            cards_html = (
                '<div class="empty"><h3>NO GAMES YET</h3><p>No games have been added to the Hall of Fame yet</p></div>'
            )
        else:
            cards_list = []
            for hfile in sorted(html_files, key=lambda p: p.name.lower()):
                file_key = hfile.name.lower()
                game_obj = done_games_map.get(file_key, {})
                display_name = game_obj.get("name") or hfile.stem.replace("_", " ")
                app_id = game_obj.get("appid")
                target_path = f"Hall of Fame/{hfile.name}"

                # Cover Image: verify local path in _OUTPUT_DONE
                cover_rel = game_obj.get("cover_local")
                if not cover_rel or not (BASE_DIR / cover_rel).exists():
                    # Check in _OUTPUT_DONE directly
                    g_folder = get_or_create_game_done_folder(output_done_dir, game_obj)
                    cand = g_folder / "cover" / "cover.jpg"
                    if cand.exists():
                        cover_rel = f"gbe_settings_generator/_OUTPUT_DONE/{g_folder.name}/cover/cover.jpg"
                    else:
                        cover_rel = game_obj.get("header_image", "")

                if cover_rel:
                    cover_img_html = f'<img class="card-thumb" src="{cover_rel}" alt="{display_name}" loading="lazy" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';"/><div class="card-fallback" style="display:none;">+</div>'
                else:
                    cover_img_html = '<div class="card-fallback">+</div>'

                # Genres
                genres = game_obj.get("genres", [])
                tags_str = " ".join(genres).lower()
                if genres:
                    genres_html = '<div class="game-genres">' + "".join(f'<span class="genre-tag">{g}</span>' for g in genres[:3]) + '</div>'
                else:
                    genres_html = '<div class="game-genres"><span class="genre-tag">Game</span></div>'

                # Calculate live progress from GSE Saves: "unlocked / total 🏆"
                default_tot = game_obj.get("total_achievements", 0)
                unlocked, total, pct = get_game_achievement_stats(gse_base_path, app_id, default_tot)

                # Layout matching User's Sketch:
                # [ Image Box ]   [ game name ]
                #                 [ game genres (red) ]
                #                                          [ 15 / 121 🏆 ]
                #                 [ =================================== ] (progress bar)
                card_str = f"""    <a class="game-card" href="{target_path}" data-title="{display_name.lower()}" data-tags="{tags_str}">
      <div class="card-thumb-wrap">
        {cover_img_html}
      </div>
      <div class="card-content">
        <div class="card-header-area">
          <div class="game-title">{display_name}</div>
          {genres_html}
        </div>
        <div class="card-progress-area">
          <div class="ach-stats-row">
            <span class="ach-ratio">{unlocked} / {total} <span class="trophy-icon">🏆</span></span>
          </div>
          <div class="progress-bar-track">
            <div class="progress-bar-fill" style="width: {pct}%;"></div>
          </div>
        </div>
      </div>
    </a>"""
                cards_list.append(card_str)

            cards_html = "\n" + "\n".join(cards_list) + "\n  "

        # Build clean complete HTML for index.html
        full_index_html = f"""<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Hall of Fame — Game Index</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet"/>
<style>
:root {{
  --night:      #0A0E1A;
  --card:       #111827;
  --teal:       #5ECFB1;
  --teal-dim:   #2A6B5A;
  --orange:     #F4A244;
  --gold:       #FFD166;
  --gold-dim:   #6B5520;
  --text:       #C8D8E8;
  --dim:        #8BAAB8;
  --muted:      #2A3644;
  --locked:     #161E2E;
  --accent-red: #FF5A5A;
  --font-pixel: 'Press Start 2P', monospace;
  --font-sans:  'Inter', sans-serif;
  --font-mono:  'JetBrains Mono', monospace;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ scroll-behavior: smooth; }}
body {{
  background: var(--night);
  color: var(--text);
  font-family: var(--font-sans);
  font-size: 15px;
  line-height: 1.6;
  min-height: 100vh;
  overflow-x: hidden;
}}
body::before {{
  content: '';
  position: fixed;
  inset: 0;
  background-image:
    linear-gradient(rgba(94,207,177,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(94,207,177,0.03) 1px, transparent 1px);
  background-size: 20px 20px;
  pointer-events: none;
  z-index: 0;
}}
.wrap {{
  position: relative;
  z-index: 1;
  max-width: 1100px;
  margin: 0 auto;
  padding: 0 20px 80px;
}}
header {{
  padding: 44px 0 32px;
  text-align: center;
  border-bottom: 2px solid var(--muted);
  margin-bottom: 30px;
  position: relative;
}}
header::after {{
  content: '';
  position: absolute;
  bottom: -2px; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--teal), transparent);
}}
.header-tag {{
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.3em;
  text-transform: uppercase;
  color: var(--teal);
  margin-bottom: 12px;
  display: block;
}}
.header-title {{
  font-family: var(--font-pixel);
  font-size: clamp(20px, 4vw, 30px);
  color: var(--gold);
  letter-spacing: 0.05em;
  line-height: 1.4;
  margin-bottom: 8px;
  text-shadow: 0 0 20px rgba(255,209,102,0.35);
}}
.header-sub {{
  font-family: var(--font-sans);
  font-size: 15px;
  color: var(--dim);
}}

/* Search Bar */
.search-bar-wrap {{
  margin-bottom: 26px;
  position: relative;
}}
.search-input {{
  width: 100%;
  background: var(--card);
  border: 2px solid var(--muted);
  padding: 14px 20px;
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text);
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
  clip-path: polygon(6px 0, calc(100% - 6px) 0, 100% 6px, 100% calc(100% - 6px), calc(100% - 6px) 100%, 6px 100%, 0 calc(100% - 6px), 0 6px);
}}
.search-input:focus {{
  border-color: var(--teal);
  box-shadow: 0 0 16px rgba(94,207,177,0.25);
}}
.search-input::placeholder {{
  color: var(--dim);
}}

/* Grid Layout */
.game-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(480px, 1fr));
  gap: 18px;
}}
@media (max-width: 640px) {{
  .game-grid {{
    grid-template-columns: 1fr;
  }}
}}

/* Horizontal Card Structure (Sketch Layout) */
.game-card {{
  background: var(--card);
  border: 2px solid var(--muted);
  padding: 14px 16px;
  display: flex;
  flex-direction: row;
  align-items: stretch;
  gap: 16px;
  text-decoration: none;
  color: inherit;
  position: relative;
  transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.2s, box-shadow 0.2s;
  clip-path: polygon(8px 0, calc(100% - 8px) 0, 100% 8px, 100% calc(100% - 8px), calc(100% - 8px) 100%, 8px 100%, 0 calc(100% - 8px), 0 8px);
}}
.game-card::before {{
  content: '';
  position: absolute;
  top: 0; left: 8px; right: 8px;
  height: 2px;
  background: var(--teal);
}}
.game-card:hover {{
  transform: translateY(-3px);
  border-color: var(--teal);
  box-shadow: 0 8px 24px rgba(94,207,177,0.18);
}}

/* Left: Game Image Box */
.card-thumb-wrap {{
  width: 140px;
  min-width: 140px;
  height: 100px;
  background: var(--locked);
  border: 1px solid var(--muted);
  border-radius: 4px;
  overflow: hidden;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  align-self: center;
}}
.card-thumb {{
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s ease;
}}
.game-card:hover .card-thumb {{
  transform: scale(1.06);
}}
.card-fallback {{
  font-family: var(--font-pixel);
  font-size: 20px;
  color: var(--gold);
}}

/* Right: Content Area */
.card-content {{
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-width: 0;
}}
.card-header-area {{
  display: flex;
  flex-direction: column;
  gap: 5px;
}}
.game-title {{
  font-family: var(--font-pixel);
  font-size: 12px;
  color: var(--text);
  line-height: 1.5;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.15s;
}}
.game-card:hover .game-title {{
  color: var(--gold);
}}

/* Game Genres (Red accent like sketch) */
.game-genres {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}}
.genre-tag {{
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 500;
  color: var(--accent-red);
  background: rgba(255, 90, 90, 0.12);
  border: 1px solid rgba(255, 90, 90, 0.3);
  padding: 1px 7px;
  border-radius: 3px;
  letter-spacing: 0.03em;
}}

/* Bottom Progress Area */
.card-progress-area {{
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}}
.ach-stats-row {{
  display: flex;
  justify-content: flex-end;
  align-items: center;
}}
.ach-ratio {{
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 700;
  color: var(--gold);
  letter-spacing: 0.05em;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}}
.trophy-icon {{
  font-size: 14px;
  filter: drop-shadow(0 0 4px rgba(255, 209, 102, 0.5));
}}

/* Progress Bar */
.progress-bar-track {{
  width: 100%;
  height: 8px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid var(--muted);
  border-radius: 4px;
  overflow: hidden;
  position: relative;
}}
.progress-bar-fill {{
  height: 100%;
  background: linear-gradient(90deg, var(--teal), var(--gold));
  border-radius: 4px;
  transition: width 0.4s ease;
}}

.empty {{
  text-align: center;
  padding: 80px 20px;
  grid-column: 1 / -1;
}}
footer {{
  text-align: center;
  margin-top: 64px;
  padding-top: 20px;
  border-top: 2px solid var(--muted);
  font-family: var(--font-pixel);
  font-size: 8px;
  color: var(--muted);
  letter-spacing: 0.2em;
}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <span class="header-tag">[ HALL OF FAME DIRECTORY ]</span>
    <h1 class="header-title">GAMES INDEX</h1>
    <p class="header-sub">Select a game to view its full achievements log</p>
  </header>

  <div class="search-bar-wrap">
    <input type="text" id="game-search" class="search-input" placeholder="🔍 SEARCH GAMES BY TITLE OR GENRE..." oninput="filterGames()" autocomplete="off"/>
  </div>

  <main class="game-grid">
{cards_html}
  </main>

  <footer>ACHIEVEMENT CHRONICLE — INDEX EDITION</footer>
</div>

<script>
function filterGames() {{
  const query = (document.getElementById('game-search')?.value || '').toLowerCase().trim();
  const cards = document.querySelectorAll('.game-card');
  cards.forEach(card => {{
    const title = card.getAttribute('data-title') || '';
    const tags = card.getAttribute('data-tags') || '';
    if (!query || title.includes(query) || tags.includes(query)) {{
      card.style.display = 'flex';
    }} else {{
      card.style.display = 'none';
    }}
  }});
}}
</script>
</body>
</html>
"""
        try:
            with open(index_file, "w", encoding="utf-8") as f:
                f.write(full_index_html)
            console.print(" [bold green][OK][/bold green] index.html successfully published with Sketch Layout UI!")
        except Exception as e:
            console.print(f" [bold red][ERROR][/bold red] Failed to update index.html: {e}")
    else:
        console.print(" [yellow]WARNING: index.html not found! Skipping index update.[/yellow]")

    # -------------------------------------------------------------
    # Summary Report
    # -------------------------------------------------------------
    summary_table = Table(title="Build Process Summary", border_style="cyan")
    summary_table.add_column("Metric", style="bold")
    summary_table.add_column("Value", style="green")

    summary_table.add_row("New Pages Built", str(processed))
    summary_table.add_row("Pages Skipped", str(skipped), style="yellow" if skipped > 0 else "green")
    summary_table.add_row("Covers Downloaded (New)", str(downloaded_covers))
    summary_table.add_row("Covers Already Cached", str(already_cached))
    summary_table.add_row("Custom Sketch UI Published", "Yes" if index_file.exists() else "No")

    console.print()
    console.print(summary_table)

    console.print()
    console.print(
        Panel.fit(
            "[bold green]BUILD & PUBLISH COMPLETED SUCCESSFULLY[/bold green]",
            border_style="green",
        )
    )


if __name__ == "__main__":
    try:
        build_achievements()
    except Exception as exc:
        console.print()
        console.print(
            Panel.fit(
                f"[bold red]Unexpected Critical Error:[/bold red]\n{exc}",
                border_style="red",
            )
        )
    finally:
        console.print()
        console.input("[bold cyan]Press Enter to close this window...[/bold cyan]")
