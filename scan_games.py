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


def fetch_steam_metadata(appid):
    """
    Fetches official game metadata directly from Steam Store API.
    No API key required. Safe and handles connection timeouts gracefully.
    """
    if not appid:
        return {}

    url = f"https://store.steampowered.com/api/appdetails?appids={appid}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
            },
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))

        str_id = str(appid)
        if str_id in data and data[str_id].get("success"):
            details = data[str_id].get("data", {})
            return {
                "steam_name": details.get("name"),
                "header_image": details.get("header_image"),
                "total_achievements": details.get("achievements", {}).get("total", 0),
                "genres": [g["description"] for g in details.get("genres", [])],
                "release_date": details.get("release_date", {}).get("date", ""),
                "short_description": details.get("short_description", ""),
            }
    except Exception as e:
        console.print(f" [dim yellow][STEAM-API] Could not fetch metadata for AppID {appid} (Offline/Timeout): {e}[/dim yellow]")

    return {}


def scan_games_directory(games_path_input=None):
    console.print(
        Panel.fit(
            "[bold cyan]Steam API Games Scanner (JSON + Steam Store API)[/bold cyan]\n"
            f"[dim]Base Directory: {BASE_DIR}[/dim]",
            border_style="cyan",
        )
    )

    games_json_file = BASE_DIR / "games.json"

    # Get target games directory from parameter, argv, or user prompt
    if games_path_input:
        target_path_str = games_path_input
    elif len(sys.argv) > 1:
        target_path_str = sys.argv[1].strip()
    else:
        console.print()
        target_path_str = console.input(
            "[bold yellow]Enter the target games directory path (e.g., F:\\1.games): [/bold yellow]"
        ).strip()

    if not target_path_str:
        console.print("\n[bold red][ERROR] No directory path was provided. Operation cancelled.[/bold red]")
        return False

    games_path = Path(target_path_str)
    if not games_path.exists() or not games_path.is_dir():
        console.print(f"\n[bold red][ERROR] Specified directory does not exist: {games_path}[/bold red]")
        return False

    console.print(f"\n[bold cyan][INIT] Scanning Target Path:[/bold cyan] {games_path}")
    console.print(f"[dim]Database File: {games_json_file}[/dim]\n")

    # -------------------------------------------------------------
    # 1. Load existing database from games.json
    # -------------------------------------------------------------
    games = {}
    if games_json_file.exists():
        console.print(f"[yellow][LOG] Loading existing database from '{games_json_file.name}'...[/yellow]")
        try:
            with open(games_json_file, "r", encoding="utf-8-sig") as f:
                games = json.load(f)
            console.print(f" [dim]Loaded {len(games)} existing game(s) from database.[/dim]")
        except Exception as e:
            console.print(f" [bold red][ERROR][/bold red] Failed reading games.json: {e}")
    else:
        console.print(f"[yellow][LOG] No existing games.json found. A new database will be created.[/yellow]")

    existing_names = {g.get("name", "").strip().lower() for g in games.values()}
    # Also track folder names if recorded
    for g in games.values():
        if "folder_name" in g:
            existing_names.add(g["folder_name"].strip().lower())

    # -------------------------------------------------------------
    # 2. Discover subdirectories inside target games directory
    # -------------------------------------------------------------
    console.print(f"\n[bold cyan][LOG] Discovering subdirectories inside '{games_path}'...[/bold cyan]")
    try:
        sub_folders = [f for f in games_path.iterdir() if f.is_dir()]
    except Exception as e:
        console.print(f"[bold red][ERROR] Failed to list directories in {games_path}: {e}[/bold red]")
        return False

    console.print(f"[bold green][OK] Total subfolders found: {len(sub_folders)}[/bold green]\n")

    added_count = 0
    skipped_count = 0
    not_found_count = 0
    mismatch_count = 0
    enriched_count = 0

    for folder in sub_folders:
        game_name = folder.name
        folder_path = folder.resolve()

        console.print("[dim]------------------------------------------------------------[/dim]")
        console.print(f"[bold cyan][SCAN] Checking Folder:[/bold cyan] '{game_name}'")

        if game_name.lower() in existing_names:
            console.print(f" [yellow][SKIP] Game '{game_name}' already exists in database. Skipping...[/yellow]")
            skipped_count += 1
            continue

        # Detect Unity Game Structure (*_Data directory)
        unity_data_dir = None
        try:
            for item in folder_path.iterdir():
                if item.is_dir() and item.name.endswith("_Data"):
                    unity_data_dir = item
                    break
        except Exception:
            pass

        is_unity = unity_data_dir is not None

        # Search for steam_api64.dll / steam_api.dll
        console.print(f" [dim][SEARCH] Searching for steam_api64.dll / steam_api.dll inside '{game_name}'...[/dim]")

        found_api = None
        api_type = "64"

        try:
            found_64 = None
            found_86 = None

            for root, dirs, files in os.walk(folder_path):
                for f in files:
                    f_lower = f.lower()
                    if f_lower == "steam_api64.dll" and not found_64:
                        found_64 = Path(root) / f
                    elif f_lower == "steam_api.dll" and not found_86:
                        found_86 = Path(root) / f
                if found_64:
                    break

            if found_64:
                found_api = found_64
                api_type = "64"
            elif found_86:
                found_api = found_86
                api_type = "86"
        except Exception as e:
            console.print(f" [bold red][ERROR] Error searching DLLs: {e}[/bold red]")

        if found_api:
            raw_folder_directory = str(found_api.parent)

            console.print(f" [bold green][SUCCESS][/bold green] Priority DLL Found ({found_api.name}) at: {found_api}")
            console.print(f" [bold green][FORMAT][/bold green] RawAchiev_path: {raw_folder_directory}")
            console.print(f" [bold green][FORMAT][/bold green] Detected steam_api: {api_type}")
            console.print(f" [cyan][UNITY][/cyan] Unity Engine Detected: {is_unity}")

            # --- Search & Validate AppID ---
            console.print(f" [dim][APPID-SEARCH] Searching for AppID config files inside '{game_name}'...[/dim]")

            txt_file = None
            api_ini_file = None
            emu_ini_file = None

            try:
                for root, dirs, files in os.walk(folder_path):
                    for f in files:
                        f_lower = f.lower()
                        if f_lower == "steam_appid.txt" and not txt_file:
                            txt_file = Path(root) / f
                        elif f_lower == "steam_api.ini" and not api_ini_file:
                            api_ini_file = Path(root) / f
                        elif f_lower == "steam_emu.ini" and not emu_ini_file:
                            emu_ini_file = Path(root) / f
                    if txt_file and api_ini_file and emu_ini_file:
                        break
            except Exception:
                pass

            extracted_txt_id = None
            extracted_api_ini_id = None
            extracted_emu_ini_id = None

            if txt_file and txt_file.exists():
                try:
                    with open(txt_file, "r", encoding="utf-8-sig", errors="ignore") as f:
                        m = re.search(r"(\d+)", f.read().strip())
                        if m:
                            extracted_txt_id = int(m.group(1))
                except Exception:
                    console.print(f" [yellow][APPID-WARN] Failed to read '{txt_file.name}'[/yellow]")

            if api_ini_file and api_ini_file.exists():
                try:
                    with open(api_ini_file, "r", encoding="utf-8-sig", errors="ignore") as f:
                        for line in f:
                            m = re.match(r"^\s*AppId\s*=\s*0*(\d+)\s*$", line, re.IGNORECASE)
                            if m:
                                extracted_api_ini_id = int(m.group(1))
                                break
                except Exception:
                    console.print(f" [yellow][APPID-WARN] Failed to read '{api_ini_file.name}'[/yellow]")

            if emu_ini_file and emu_ini_file.exists():
                try:
                    with open(emu_ini_file, "r", encoding="utf-8-sig", errors="ignore") as f:
                        for line in f:
                            m = re.match(r"^\s*AppId\s*=\s*0*(\d+)\s*$", line, re.IGNORECASE)
                            if m:
                                extracted_emu_ini_id = int(m.group(1))
                                break
                except Exception:
                    console.print(f" [yellow][APPID-WARN] Failed to read '{emu_ini_file.name}'[/yellow]")

            detected_values = []
            if extracted_txt_id is not None:
                detected_values.append(extracted_txt_id)
            if extracted_api_ini_id is not None:
                detected_values.append(extracted_api_ini_id)
            if extracted_emu_ini_id is not None:
                detected_values.append(extracted_emu_ini_id)

            final_app_id = None
            if detected_values:
                unique_values = list(set(detected_values))
                if len(unique_values) == 1:
                    final_app_id = unique_values[0]
                    console.print(f" [bold green][APPID-SUCCESS] Valid AppID confirmed: {final_app_id}[/bold green]")
                else:
                    console.print(f" [bold red][APPID-MISMATCH] Conflicting AppIDs detected: {unique_values}[/bold red]")
                    mismatch_count += 1
            else:
                console.print(" [yellow][APPID-NOTFOUND] No AppID files found.[/yellow]")

            # --- Steam Store API Auto-Enrichment ---
            steam_meta = {}
            if final_app_id:
                console.print(f" [bold magenta][STEAM-API] Querying Steam Store API for AppID {final_app_id}...[/bold magenta]")
                steam_meta = fetch_steam_metadata(final_app_id)
                if steam_meta:
                    enriched_count += 1
                    console.print(
                        f"   -> [bold green]Enriched:[/bold green] '{steam_meta.get('steam_name')}' | "
                        f"Genres: {steam_meta.get('genres', [])} | Total Achievements: {steam_meta.get('total_achievements', 0)}"
                    )

            display_name = steam_meta.get("steam_name") or game_name
            safe_name = re.sub(r"[^a-zA-Z0-9]", "_", display_name)
            game_key = str(final_app_id) if final_app_id else f"pending_{safe_name}"

            games[game_key] = {
                "name": display_name,
                "folder_name": game_name,
                "appid": final_app_id,
                "status": "active" if final_app_id else "scanned",
                "raw_path": raw_folder_directory,
                "steam_api": api_type,
                "is_unity": is_unity,
                "html_file": f"{safe_name}.html",
                "header_image": steam_meta.get("header_image"),
                "total_achievements": steam_meta.get("total_achievements", 0),
                "genres": steam_meta.get("genres", []),
                "release_date": steam_meta.get("release_date", ""),
            }

            existing_names.add(game_name.lower())
            existing_names.add(display_name.lower())
            added_count += 1
            console.print(f" [bold green][SUCCESS] Added '{display_name}' to database (Key: {game_key}, Status: {games[game_key]['status']})[/bold green]")
        else:
            console.print(f" [dim yellow][NOT FOUND] No steam_api.dll or steam_api64.dll found in '{game_name}'.[/dim yellow]")
            not_found_count += 1

    # -------------------------------------------------------------
    # 3. Save database to games.json
    # -------------------------------------------------------------
    if added_count > 0 or not games_json_file.exists():
        try:
            with open(games_json_file, "w", encoding="utf-8") as f:
                json.dump(games, f, indent=2, ensure_ascii=False)
            console.print(f"\n[bold green][SAVED] Database '{games_json_file.name}' saved with {len(games)} game(s).[/bold green]")
        except Exception as e:
            console.print(f"\n[bold red][ERROR] Failed saving database: {e}[/bold red]")

    # -------------------------------------------------------------
    # Summary Table
    # -------------------------------------------------------------
    summary_table = Table(title="Scanner Process Summary", border_style="cyan")
    summary_table.add_column("Metric", style="bold")
    summary_table.add_column("Count", style="white")

    summary_table.add_row("Total Directories Scanned", str(len(sub_folders)))
    summary_table.add_row("New Games Added to Database", str(added_count), style="green" if added_count > 0 else "white")
    summary_table.add_row("Games Enriched via Steam API", str(enriched_count), style="magenta" if enriched_count > 0 else "white")
    summary_table.add_row("AppID Mismatches (Warnings)", str(mismatch_count), style="red" if mismatch_count > 0 else "green")
    summary_table.add_row("Skipped (Already in Database)", str(skipped_count), style="yellow" if skipped_count > 0 else "white")
    summary_table.add_row("Skipped (DLL Not Found)", str(not_found_count), style="dim" if not_found_count > 0 else "white")

    console.print()
    console.print(summary_table)

    console.print()
    console.print(
        Panel.fit(
            "[bold green]SCAN COMPLETED SUCCESSFULLY[/bold green]",
            border_style="green",
        )
    )

    return True


if __name__ == "__main__":
    try:
        scan_games_directory()
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
