import json
import os
import re
import shutil
import subprocess
import sys
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


def prepare_and_deploy_games():
    console.print(
        Panel.fit(
            "[bold cyan]Game Preparation & Deployment Tool (JSON Edition)[/bold cyan]\n"
            f"[dim]Base Directory: {BASE_DIR}[/dim]",
            border_style="cyan",
        )
    )

    games_json_file = BASE_DIR / "games.json"
    gbe_dir = BASE_DIR / "gbe_settings_generator"
    output_dir = gbe_dir / "_OUTPUT"
    output_done_dir = gbe_dir / "_OUTPUT_DONE"

    # -------------------------------------------------------------
    # Step 1: Check Required Files and Workspace
    # -------------------------------------------------------------
    console.print("\n[bold cyan][1/4] Verifying workspace setup and files...[/bold cyan]")
    missing_items = []
    if not games_json_file.exists():
        missing_items.append(f"Missing database: {games_json_file.name}")
    if not gbe_dir.exists() or not gbe_dir.is_dir():
        missing_items.append(f"Missing directory: {gbe_dir.name}")

    if missing_items:
        console.print(
            Panel.fit(
                "[bold red]Critical Error: Missing required components:[/bold red]\n"
                + "\n".join(f" - {item}" for item in missing_items),
                border_style="red",
            )
        )
        return False

    console.print(f" [bold green][OK][/bold green] Verified: {games_json_file.name}")
    console.print(f" [bold green][OK][/bold green] Verified: {gbe_dir.name}")

    # -------------------------------------------------------------
    # Step 2: Load games.json
    # -------------------------------------------------------------
    try:
        with open(games_json_file, "r", encoding="utf-8-sig") as f:
            games = json.load(f)
        console.print(f" [bold green][OK][/bold green] Loaded database with {len(games)} game entry(ies).")
    except Exception as e:
        console.print(f" [bold red][ERROR][/bold red] Failed reading '{games_json_file.name}': {e}")
        return False

    # Filter active games that have valid AppIDs
    active_games = [
        g for g in games.values()
        if g.get("status") == "active" and g.get("appid")
    ]

    # -------------------------------------------------------------
    # Step 3: Unity Game Filter & Interactive Selection
    # -------------------------------------------------------------
    console.print("\n[bold cyan][2/4] Game Selection & Filtering...[/bold cyan]")
    unity_input = console.input(
        "[bold yellow]Do you want to process Unity games as well? (y/N) [Default: n]: [/bold yellow]"
    ).strip().lower()

    include_unity = (unity_input == "y")
    if include_unity:
        console.print(" [magenta][MODE] ALL games (Unity & Non-Unity) will be available.[/magenta]")
        filtered_active_games = active_games[:]
    else:
        console.print(" [cyan][MODE] Unity games are EXCLUDED from selection.[/cyan]")
        filtered_active_games = [g for g in active_games if not g.get("is_unity", False)]

    to_generate = []
    if filtered_active_games:
        table_title = "AVAILABLE UN-PREPARED GAMES (ALL)" if include_unity else "AVAILABLE UN-PREPARED NON-UNITY GAMES"
        games_table = Table(title=table_title, border_style="cyan")
        games_table.add_column("#", style="bold cyan", width=4)
        games_table.add_column("Game Name", style="white")
        games_table.add_column("AppID", style="green")

        for idx, g in enumerate(filtered_active_games, 1):
            games_table.add_row(str(idx), g["name"], str(g["appid"]))

        console.print()
        console.print(games_table)
    else:
        console.print("\n[yellow][INFO] No matching active games found awaiting selection for this filter.[/yellow]")

    console.print()
    user_input = console.input(
        "[bold yellow]Select games (Enter = Skip New Gen | 'all' = All | Numbers e.g. 1 3 | Exclude e.g. -1 -2 -6): [/bold yellow]"
    ).strip()

    if not user_input:
        console.print("[yellow][INFO] Selection SKIPPED by user. Proceeding directly to mandatory audit...[/yellow]")
    else:
        tokens = user_input.split()
        has_negatives = any(t.startswith("-") and t[1:].isdigit() for t in tokens)
        has_positives = any(t.isdigit() for t in tokens)
        has_all = any(t.lower() == "all" for t in tokens)

        if has_all or (has_negatives and not has_positives):
            selected_set = set(range(len(filtered_active_games)))
        else:
            selected_set = set()

        for token in tokens:
            if token.lower() == "all":
                selected_set = set(range(len(filtered_active_games)))
            elif token.isdigit():
                idx = int(token) - 1
                if 0 <= idx < len(filtered_active_games):
                    selected_set.add(idx)
                else:
                    console.print(f"[yellow][WARN] Out of bounds selection index ignored: {token}[/yellow]")
            elif token.startswith("-") and token[1:].isdigit():
                idx = int(token[1:]) - 1
                if 0 <= idx < len(filtered_active_games):
                    selected_set.discard(idx)
                else:
                    console.print(f"[yellow][WARN] Out of bounds exclusion index ignored: {token}[/yellow]")

        to_generate = [filtered_active_games[i] for i in range(len(filtered_active_games)) if i in selected_set]
        console.print(f"[cyan][INFO] User selected {len(to_generate)} game(s) for processing.[/cyan]")

    # Filter out games where output folder already exists in _OUTPUT or _OUTPUT_DONE
    filtered_to_generate = []
    for game in to_generate:
        app_id_str = str(game["appid"])
        target_folder = output_dir / app_id_str
        safe_game_name = re.sub(r'[\\/:*?"<>|]', "_", game.get("name", ""))
        done_folder = output_done_dir / safe_game_name

        if target_folder.exists():
            console.print(f"[yellow][SKIP] Skipped GBE generation for '{game['name']}': Output folder already exists in _OUTPUT.[/yellow]")
        elif done_folder.exists():
            console.print(f"[yellow][SKIP] Skipped GBE generation for '{game['name']}': Emulator config already exists in _OUTPUT_DONE.[/yellow]")
        else:
            filtered_to_generate.append(game)

    # -------------------------------------------------------------
    # Step 4: Run GBE Generator Command
    # -------------------------------------------------------------
    if filtered_to_generate:
        app_id_list = [str(g["appid"]) for g in filtered_to_generate]
        console.print(f"\n[bold cyan][EXEC] Invoking GBE Generator for AppIDs: {' '.join(app_id_list)}[/bold cyan]")

        gen_cmd = "generate_emu_config"
        if (gbe_dir / "generate_emu_config.bat").exists():
            gen_cmd = str(gbe_dir / "generate_emu_config.bat")
        elif (gbe_dir / "generate_emu_config.exe").exists():
            gen_cmd = str(gbe_dir / "generate_emu_config.exe")
        elif (gbe_dir / "generate_emu_config.cmd").exists():
            gen_cmd = str(gbe_dir / "generate_emu_config.cmd")

        try:
            cmd_args = [gen_cmd] + app_id_list
            subprocess.run(cmd_args, cwd=str(gbe_dir), shell=True, check=True)
            console.print("[bold green][SUCCESS] GBE Generator execution finished.[/bold green]")
        except Exception as e:
            console.print(f"[bold red][ERROR] Failed to execute GBE generator script: {e}[/bold red]")

    # -------------------------------------------------------------
    # Step 5: Sequential Audit & Step-by-Step Deployment Phase
    # -------------------------------------------------------------
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]SEQUENTIAL AUDIT & VERIFICATION PIPELINE[/bold cyan]\n"
            "[dim]Follows strict step-by-step checks: skips existing components and moves forward[/dim]",
            border_style="cyan",
        )
    )

    output_done_dir.mkdir(parents=True, exist_ok=True)

    # Collect candidates: all folders in _OUTPUT + any selected games already in _OUTPUT_DONE
    audit_candidates = []
    if output_dir.exists():
        for folder in output_dir.iterdir():
            if folder.is_dir():
                audit_candidates.append((folder, False))  # (folder_path, is_from_done_dir)

    for game in to_generate:
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", game.get("name", ""))
        done_path = output_done_dir / safe_name
        app_id_str = str(game.get("appid"))
        if done_path.exists() and not (output_dir / app_id_str).exists():
            # Avoid duplicate additions
            if not any(cand[0] == done_path for cand in audit_candidates):
                audit_candidates.append((done_path, True))

    if not audit_candidates:
        console.print("[yellow][INFO] No pending output folders found to audit or deploy.[/yellow]")
    else:
        for folder, is_from_done_dir in audit_candidates:
            console.print("\n[dim]------------------------------------------------------------[/dim]")

            # Match game in database
            game = None
            if not is_from_done_dir:
                app_id_str = folder.name
                game = games.get(app_id_str)
                if not game:
                    game = next((g for g in games.values() if str(g.get("appid")) == app_id_str), None)
            else:
                game = next((g for g in games.values() if re.sub(r'[\\/:*?"<>|]', "_", g.get("name", "")) == folder.name), None)

            if not game:
                console.print(f"[yellow][WARN] Could not match folder '{folder.name}' to any game in database. Skipping...[/yellow]")
                continue

            game_name = game.get("name", "Unknown Game")
            raw_path_str = game.get("raw_path", "")
            target_game_dir = Path(raw_path_str) if raw_path_str else None
            api_type = str(game.get("steam_api", "64"))
            is_unity = game.get("is_unity", False)

            console.print(f"[bold cyan][AUDIT][/bold cyan] [bold white]{game_name}[/bold white] (AppID: {game.get('appid')})")
            console.print(f"  [dim]Source Config: {folder}[/dim]")

            if not target_game_dir or not target_game_dir.exists() or not target_game_dir.is_dir():
                console.print(f"  [bold red][ERROR] Game target installation folder not found: {target_game_dir}[/bold red]")
                continue

            # -------------------------------------------------------------
            # Target Paths Resolution (Handles Unity & Non-Unity Accurately)
            # -------------------------------------------------------------
            dll_file_name = "steam_api64.dll" if api_type == "64" else "steam_api.dll"

            if is_unity:
                # 1. Locate Unity Root (containing *_Data directory and Game.exe)
                unity_root = None
                curr_search = target_game_dir
                while curr_search and curr_search.parent != curr_search:
                    try:
                        has_data = any(p.is_dir() and p.name.endswith("_Data") for p in curr_search.iterdir())
                        if has_data:
                            unity_root = curr_search
                            break
                    except Exception:
                        pass
                    if curr_search.name.lower() in ["1.games", "games", "steamapps", "common"]:
                        break
                    curr_search = curr_search.parent

                if not unity_root:
                    unity_root = target_game_dir

                # 2. Locate internal Unity Plugins directory where steam_api DLL belongs
                plugins_dir = None
                if "plugins" in str(target_game_dir).lower():
                    plugins_dir = target_game_dir
                else:
                    try:
                        for item in unity_root.iterdir():
                            if item.is_dir() and item.name.endswith("_Data"):
                                cand = item / "Plugins"
                                if cand.exists():
                                    if api_type == "64" and (cand / "x86_64").exists():
                                        plugins_dir = cand / "x86_64"
                                    elif api_type == "86" and (cand / "x86").exists():
                                        plugins_dir = cand / "x86"
                                    elif (cand / dll_file_name).exists():
                                        plugins_dir = cand
                                    elif (cand / "x86_64").exists():
                                        plugins_dir = cand / "x86_64"
                                    elif (cand / "x86").exists():
                                        plugins_dir = cand / "x86"
                                    else:
                                        plugins_dir = cand
                                break
                    except Exception:
                        pass

                dll_target_dir = plugins_dir if plugins_dir else target_game_dir
                steam_settings_target = unity_root

                console.print(f"  [cyan][UNITY-CONFIG][/cyan] Root Folder (for steam_settings): {steam_settings_target}")
                console.print(f"  [cyan][UNITY-CONFIG][/cyan] Plugins Folder (for steam_api DLL): {dll_target_dir}")
            else:
                steam_settings_target = target_game_dir
                dll_target_dir = target_game_dir

            # -------------------------------------------------------------
            # STEP 1: Check & Deploy steam_settings
            # -------------------------------------------------------------
            console.print(f"  [bold cyan][STEP 1/4: STEAM_SETTINGS][/bold cyan] Target: {steam_settings_target / 'steam_settings'}")
            src_steam_settings = folder / "steam_settings"
            dest_steam_settings = steam_settings_target / "steam_settings"

            if dest_steam_settings.exists() and dest_steam_settings.is_dir() and any(dest_steam_settings.iterdir()):
                console.print(f"    [bold green][SKIP][/bold green] 'steam_settings' already exists at target. Skipping copy.")
            else:
                if src_steam_settings.exists() and src_steam_settings.is_dir():
                    console.print(f"    [yellow][DEPLOY][/yellow] Copying 'steam_settings' folder...")
                    try:
                        if dest_steam_settings.exists():
                            shutil.rmtree(dest_steam_settings)
                        shutil.copytree(src_steam_settings, dest_steam_settings)
                        console.print(f"    [bold green][SUCCESS][/bold green] 'steam_settings' deployed successfully!")
                    except Exception as e:
                        console.print(f"    [bold red][ERROR][/bold red] Failed to copy 'steam_settings': {e}")
                else:
                    console.print(f"    [dim yellow][SKIP][/dim yellow] 'steam_settings' not found in generator output.")

            # -------------------------------------------------------------
            # STEPS 2, 3, 4: DLL Handling at dll_target_dir
            # -------------------------------------------------------------
            console.print(f"  [bold cyan][API DEPLOYMENT][/bold cyan] Path: {dll_target_dir}")
            src_dll_path = folder / dll_file_name
            dest_dll_path = dll_target_dir / dll_file_name
            api_old_dir = dll_target_dir / "api_old"
            api_old_file = api_old_dir / dll_file_name
            api_new_dir = dll_target_dir / "api_new"
            api_new_file = api_new_dir / dll_file_name

            legacy_old_api = dll_target_dir / "old_api" / dll_file_name

            # --- STEP 2: Backup Original DLL (api_old) ---
            console.print(f"    [bold cyan][STEP 2/4: BACKUP ORIGINAL DLL][/bold cyan]")
            if api_old_file.exists():
                console.print(f"      [bold green][SKIP][/bold green] Original DLL backup already exists in 'api_old'.")
            elif legacy_old_api.exists():
                console.print(f"      [cyan][MIGRATE][/cyan] Found legacy backup in 'old_api'. Migrating to 'api_old'...")
                try:
                    api_old_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(legacy_old_api, api_old_file)
                    shutil.rmtree(dll_target_dir / "old_api")
                    console.print(f"      [bold green][SUCCESS][/bold green] Migrated to: {api_old_file}")
                except Exception as e:
                    console.print(f"      [bold red][ERROR][/bold red] Migration failed: {e}")
            else:
                if dest_dll_path.exists():
                    # Protect against backing up an already-deployed emulator DLL
                    is_already_emu = src_dll_path.exists() and (dest_dll_path.stat().st_size == src_dll_path.stat().st_size)
                    if is_already_emu:
                        console.print(f"      [dim yellow][SKIP][/dim yellow] Existing DLL matches emulator binary. Skipping backup to protect original state.")
                    else:
                        try:
                            api_old_dir.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(dest_dll_path, api_old_file)
                            console.print(f"      [bold green][SUCCESS][/bold green] Backed up original '{dll_file_name}' to 'api_old'.")
                        except Exception as e:
                            console.print(f"      [bold red][ERROR][/bold red] Failed backing up original DLL: {e}")
                else:
                    console.print(f"      [dim yellow][SKIP][/dim yellow] No existing '{dll_file_name}' found to back up.")

            # --- STEP 3: Deploy Emulator DLL ---
            console.print(f"    [bold cyan][STEP 3/4: DEPLOY EMULATOR DLL][/bold cyan]")
            if not src_dll_path.exists():
                console.print(f"      [bold red][ERROR][/bold red] Source '{dll_file_name}' not found in generator output.")
            else:
                if dest_dll_path.exists() and (dest_dll_path.stat().st_size == src_dll_path.stat().st_size):
                    console.print(f"      [bold green][SKIP][/bold green] Emulator DLL '{dll_file_name}' is already deployed at target.")
                else:
                    try:
                        shutil.copy2(src_dll_path, dest_dll_path)
                        console.print(f"      [bold green][SUCCESS][/bold green] '{dll_file_name}' deployed successfully!")
                    except Exception as e:
                        console.print(f"      [bold red][ERROR][/bold red] Failed deploying DLL: {e}")

            # --- STEP 4: Save Copy to api_new ---
            console.print(f"    [bold cyan][STEP 4/4: SAVE COPY TO API_NEW][/bold cyan]")
            if api_new_file.exists() and src_dll_path.exists() and (api_new_file.stat().st_size == src_dll_path.stat().st_size):
                console.print(f"      [bold green][SKIP][/bold green] Copy of deployed DLL already exists in 'api_new'.")
            else:
                if src_dll_path.exists():
                    try:
                        api_new_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_dll_path, api_new_file)
                        console.print(f"      [bold green][SUCCESS][/bold green] Placed copy of '{dll_file_name}' inside 'api_new'.")
                    except Exception as e:
                        console.print(f"      [bold red][ERROR][/bold red] Failed saving copy in 'api_new': {e}")
                else:
                    console.print(f"      [dim yellow][SKIP][/dim yellow] Source DLL not available for 'api_new'.")

            # --- STEP 5: Archive & Update Database ---
            safe_game_name = re.sub(r'[\\/:*?"<>|]', "_", game_name)
            done_destination = output_done_dir / safe_game_name

            if not is_from_done_dir:
                console.print(f"  [yellow][ARCHIVE][/yellow] Archiving output folder to _OUTPUT_DONE as '{safe_game_name}'...")
                try:
                    if done_destination.exists():
                        shutil.rmtree(done_destination)
                    shutil.move(str(folder), str(done_destination))
                    console.print(f"  [bold green][SUCCESS][/bold green] Archived to: {done_destination}")
                except Exception as e:
                    console.print(f"  [bold red][ERROR][/bold red] Failed archiving output folder: {e}")

            # Mark game status as prepared in database
            game["status"] = "prepared"

    # -------------------------------------------------------------
    # Step 6: Save updated database
    # -------------------------------------------------------------
    console.print(f"\n[bold cyan][4/4] Saving updated status to {games_json_file.name}...[/bold cyan]")
    try:
        with open(games_json_file, "w", encoding="utf-8") as f:
            json.dump(games, f, indent=2, ensure_ascii=False)
        console.print(f" [bold green][SUCCESS] '{games_json_file.name}' successfully updated![/bold green]")
    except Exception as e:
        console.print(f" [bold red][ERROR] Failed to write database: {e}[/bold red]")
        return False

    # -------------------------------------------------------------
    # Summary Report
    # -------------------------------------------------------------
    processed_count = 0
    if output_done_dir.exists():
        processed_count = len([d for d in output_done_dir.iterdir() if d.is_dir()])

    prepared_count = sum(1 for g in games.values() if g.get("status") == "prepared")

    summary_table = Table(title="Preparation & Deployment Summary", border_style="cyan")
    summary_table.add_column("Metric", style="bold")
    summary_table.add_column("Value", style="green")

    summary_table.add_row("Status", "SUCCESS")
    summary_table.add_row("Total Prepared Games", str(prepared_count))
    summary_table.add_row("Archived Games in _OUTPUT_DONE", str(processed_count))
    summary_table.add_row("Database Updated", "Yes")

    console.print()
    console.print(summary_table)

    console.print()
    console.print(
        Panel.fit(
            "[bold green]PREPARATION & DEPLOYMENT FLOW COMPLETED SUCCESSFULLY[/bold green]",
            border_style="green",
        )
    )
    return True


if __name__ == "__main__":
    try:
        prepare_and_deploy_games()
    except Exception as exc:
        console.print()
        console.print(
            Panel.fit(
                f"[bold red]Unexpected Critical Error:[/bold red]\n{exc}",
                border_style="red",
            )
        )
    finally:
        try:
            console.print()
            console.input("[bold cyan]Press Enter to close this window...[/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            pass
