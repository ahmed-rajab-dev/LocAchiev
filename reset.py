import json
import os
import re
import shutil
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


def find_game_root_directory(raw_path_str):
    """
    Finds the root game installation directory from a potentially deep raw_path.
    e.g., F:\\1.games\\Borderlands 2\\Binaries\\Win32 -> F:\\1.games\\Borderlands 2
    """
    if not raw_path_str:
        return None

    path = Path(raw_path_str)
    if not path.exists():
        return path

    curr = path
    while curr.parent != curr:
        parent_name = curr.parent.name.lower()
        if parent_name in ["1.games", "games", "steamapps", "common"]:
            return curr
        # Check if parent contains *_Data for Unity games
        try:
            has_data = any(p.is_dir() and p.name.endswith("_Data") for p in curr.parent.iterdir())
            if has_data:
                return curr.parent
        except Exception:
            pass
        curr = curr.parent

    return path


def reset_web_testing_environment(games_json_file, hof_dir):
    """
    Option 1: Clears Hall of Fame folder and restores 'done' games to 'prepared' in database.
    """
    console.print(
        Panel.fit(
            "[bold cyan][OPTION 1] RESETTING WEB & TESTING ENVIRONMENT[/bold cyan]",
            border_style="cyan",
        )
    )

    # 1. Clear Hall of Fame Folder
    console.print("\n[bold yellow][1/2] Cleaning Hall of Fame directory...[/bold yellow]")
    if hof_dir.exists() and hof_dir.is_dir():
        try:
            cleared_count = 0
            for item in hof_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                cleared_count += 1
            console.print(
                f" [bold green][SUCCESS][/bold green] 'Hall of Fame' folder emptied ({cleared_count} items removed)."
            )
        except Exception as e:
            console.print(
                f" [bold red][FAILED][/bold red] Could not clear Hall of Fame: {e}"
            )
    else:
        console.print(" [dim][SKIP] 'Hall of Fame' folder does not exist.[/dim]")

    # 2. Restore 'done' games to 'prepared' in games.json
    console.print(
        "\n[bold yellow][2/2] Restoring 'done' games to 'prepared' in 'games.json'...[/bold yellow]"
    )
    if games_json_file.exists():
        try:
            with open(games_json_file, "r", encoding="utf-8-sig") as f:
                games = json.load(f)

            restored_count = 0
            for game_id, game in games.items():
                if game.get("status") == "done":
                    game["status"] = "prepared"
                    restored_count += 1

            with open(games_json_file, "w", encoding="utf-8") as f:
                json.dump(games, f, indent=2, ensure_ascii=False)

            console.print(
                f" [bold green][SUCCESS][/bold green] Restored {restored_count} 'done' game(s) to 'prepared' status."
            )
        except Exception as e:
            console.print(
                f" [bold red][FAILED][/bold red] Could not update 'games.json': {e}"
            )
    else:
        console.print(
            f" [bold red][FAILED][/bold red] 'games.json' not found at: {games_json_file}"
        )


def revert_game_modifications(games_json_file):
    """
    Option 2: Reverts game installation directories back to their original state:
    - Traverses game root & subdirectories
    - Deletes emulator files deployed from api_new
    - Restores original backed-up DLLs from api_old
    - Deletes api_new and api_old folders
    - Optionally deletes steam_settings folders
    - Resets game status back to 'active' in database
    """
    console.print(
        Panel.fit(
            "[bold cyan][OPTION 2] REVERT GAME DIRECTORIES (UNINSTALL EMULATOR MODS)[/bold cyan]",
            border_style="cyan",
        )
    )

    if not games_json_file.exists():
        console.print(f"[bold red][ERROR] Database not found at: {games_json_file}[/bold red]")
        return False

    with open(games_json_file, "r", encoding="utf-8-sig") as f:
        games = json.load(f)

    # 1. Ask about deleting steam_settings
    console.print()
    del_settings_input = console.input(
        "[bold yellow]Do you want to delete 'steam_settings' folder as well from game directories? (y/N) [Default: n]: [/bold yellow]"
    ).strip().lower()
    clean_steam_settings = (del_settings_input == "y")

    if clean_steam_settings:
        console.print(" [bold red][ACTION] 'steam_settings' folders WILL BE DELETED from selected games.[/bold red]")
    else:
        console.print(" [dim][ACTION] 'steam_settings' folders will be PRESERVED.[/dim]")

    # 2. Find eligible games (prepared and done as specified)
    eligible_games = [
        g for g in games.values()
        if g.get("raw_path") and g.get("status") in ["prepared", "done"]
    ]

    is_fallback = False
    if not eligible_games:
        # Graceful fallback: If no games are currently marked 'prepared' or 'done', show active games with paths
        eligible_games = [
            g for g in games.values()
            if g.get("raw_path")
        ]
        is_fallback = True
        console.print("\n[dim yellow][INFO] No games currently marked as 'prepared' or 'done'. Showing all configured games with paths:[/dim yellow]")

    if not eligible_games:
        console.print("\n[yellow][INFO] No games with valid paths found in database.[/yellow]")
        return False

    # Display game selection table
    table_title = "Eligible Games to Revert & Clean" if not is_fallback else "Configured Games (Manual Cleanup Mode)"
    games_table = Table(title=table_title, border_style="cyan")
    games_table.add_column("#", style="bold cyan", width=4)
    games_table.add_column("Game Name", style="white")
    games_table.add_column("Status", style="yellow")
    games_table.add_column("Root Path", style="dim")

    for idx, g in enumerate(eligible_games, 1):
        root_path = find_game_root_directory(g.get("raw_path"))
        games_table.add_row(
            str(idx),
            g.get("name", "Unknown"),
            g.get("status", "unknown").upper(),
            str(root_path) if root_path else "Not found",
        )

    console.print()
    console.print(games_table)

    console.print()
    user_input = console.input(
        "[bold yellow]Select games to revert (Enter = Cancel | 'all' = All | Numbers e.g. 1 3 | Exclude e.g. -1 -2 -6): [/bold yellow]"
    ).strip()

    if not user_input:
        console.print("[yellow][CANCELLED] Operation cancelled by user.[/yellow]")
        return False

    tokens = user_input.split()
    has_negatives = any(t.startswith("-") and t[1:].isdigit() for t in tokens)
    has_positives = any(t.isdigit() for t in tokens)
    has_all = any(t.lower() == "all" for t in tokens)

    if has_all or (has_negatives and not has_positives):
        selected_set = set(range(len(eligible_games)))
    else:
        selected_set = set()

    for token in tokens:
        if token.lower() == "all":
            selected_set = set(range(len(eligible_games)))
        elif token.isdigit():
            idx = int(token) - 1
            if 0 <= idx < len(eligible_games):
                selected_set.add(idx)
            else:
                console.print(f"[yellow][WARN] Invalid selection number: {token}[/yellow]")
        elif token.startswith("-") and token[1:].isdigit():
            idx = int(token[1:]) - 1
            if 0 <= idx < len(eligible_games):
                selected_set.discard(idx)
            else:
                console.print(f"[yellow][WARN] Invalid exclusion number: {token}[/yellow]")

    selected_games = [eligible_games[i] for i in range(len(eligible_games)) if i in selected_set]

    if not selected_games:
        console.print("[yellow][INFO] No valid games selected. Returning.[/yellow]")
        return False

    console.print(f"\n[bold cyan]Starting Reversion for {len(selected_games)} Game(s)...[/bold cyan]")

    total_restored_files = 0
    total_removed_files = 0
    total_removed_settings = 0
    total_cleaned_folders = 0

    for game in selected_games:
        game_name = game.get("name", "Unknown Game")
        raw_path = game.get("raw_path")
        game_root = find_game_root_directory(raw_path)

        console.print("\n" + "[dim]------------------------------------------------------------[/dim]")
        console.print(f"[bold cyan][REVERTING][/bold cyan] [bold white]{game_name}[/bold white]")
        console.print(f" [dim]Target Directory: {game_root}[/dim]")

        if not game_root or not game_root.exists():
            console.print(f" [bold red][FAILED] Directory does not exist on disk: {game_root}[/bold red]")
            continue

        game_restored = 0
        game_removed = 0
        game_settings_del = 0

        # Traverse directory tree from bottom up (topdown=False) to safely process folders
        for root, dirs, files in os.walk(game_root, topdown=False):
            curr_dir = Path(root)

            # Identify new environment backup directories (api_new & api_old)
            api_new_dir = curr_dir / "api_new"
            api_old_dir = curr_dir / "api_old"

            has_api_new = api_new_dir.exists() and api_new_dir.is_dir()
            has_api_old = api_old_dir.exists() and api_old_dir.is_dir()

            # Process api_new & api_old in this folder
            if has_api_new or has_api_old:
                console.print(f"\n  [cyan][FOUND API BACKUPS][/cyan] In: {curr_dir}")

                # 1. Delete files deployed from api_new
                if has_api_new:
                    try:
                        for new_file in api_new_dir.iterdir():
                            if new_file.is_file():
                                deployed_target = curr_dir / new_file.name
                                if deployed_target.exists():
                                    try:
                                        deployed_target.unlink()
                                        game_removed += 1
                                        total_removed_files += 1
                                        console.print(f"    [bold red][REMOVED DEPLOYED][/bold red] {deployed_target.name}")
                                    except Exception as e:
                                        console.print(f"    [bold red][ERROR REMOVING][/bold red] {deployed_target.name}: {e}")
                    except Exception as e:
                        console.print(f"    [bold red][ERROR INSPECTING api_new][/bold red]: {e}")

                # 2. Restore original backed-up files from api_old
                if has_api_old:
                    try:
                        for old_file in api_old_dir.iterdir():
                            if old_file.is_file():
                                restore_target = curr_dir / old_file.name
                                try:
                                    shutil.copy2(old_file, restore_target)
                                    game_restored += 1
                                    total_restored_files += 1
                                    console.print(f"    [bold green][RESTORED ORIGINAL][/bold green] {old_file.name}")
                                except Exception as e:
                                    console.print(f"    [bold red][ERROR RESTORING][/bold red] {old_file.name}: {e}")
                    except Exception as e:
                        console.print(f"    [bold red][ERROR INSPECTING api_old][/bold red]: {e}")

                # 3. Clean and delete api_new and api_old folders
                if has_api_new:
                    try:
                        shutil.rmtree(api_new_dir)
                        total_cleaned_folders += 1
                        console.print("    [dim][CLEANED] Deleted folder: api_new[/dim]")
                    except Exception as e:
                        console.print(f"    [yellow][WARN] Could not delete api_new folder: {e}[/yellow]")

                if has_api_old:
                    try:
                        shutil.rmtree(api_old_dir)
                        total_cleaned_folders += 1
                        console.print("    [dim][CLEANED] Deleted folder: api_old[/dim]")
                    except Exception as e:
                        console.print(f"    [yellow][WARN] Could not delete api_old folder: {e}[/yellow]")

            # 4. Clean steam_settings folder if user chose to delete it
            if clean_steam_settings:
                steam_settings_dir = curr_dir / "steam_settings"
                if steam_settings_dir.exists() and steam_settings_dir.is_dir():
                    try:
                        shutil.rmtree(steam_settings_dir)
                        game_settings_del += 1
                        total_removed_settings += 1
                        console.print(f"    [bold red][DELETED SETTINGS][/bold red] Removed 'steam_settings' from: {curr_dir}")
                    except Exception as e:
                        console.print(f"    [bold red][ERROR][/bold red] Failed removing 'steam_settings': {e}")

        # Reset game status back to 'active'
        game["status"] = "active"
        console.print(
            f" [bold green][COMPLETE][/bold green] Restored: {game_restored} file(s) | "
            f"Removed: {game_removed} file(s) | Status reset to [bold cyan]ACTIVE[/bold cyan]."
        )

    # Save database updates
    try:
        with open(games_json_file, "w", encoding="utf-8") as f:
            json.dump(games, f, indent=2, ensure_ascii=False)
        console.print("\n[bold green][SAVED] Database updated with reverted game statuses.[/bold green]")
    except Exception as e:
        console.print(f"\n[bold red][ERROR] Failed saving database: {e}[/bold red]")

    # Reversion Summary Table
    summary_table = Table(title="Game Reversion & Cleanup Summary", border_style="cyan")
    summary_table.add_column("Metric", style="bold")
    summary_table.add_column("Count", style="green")

    summary_table.add_row("Games Reverted", str(len(selected_games)))
    summary_table.add_row("Original Files Restored", str(total_restored_files))
    summary_table.add_row("Deployed Emulator Files Removed", str(total_removed_files))
    summary_table.add_row("Backup Folders Purged (api_new/old)", str(total_cleaned_folders))
    if clean_steam_settings:
        summary_table.add_row("steam_settings Folders Deleted", str(total_removed_settings))

    console.print()
    console.print(summary_table)
    return True


def main_menu():
    console.print(
        Panel.fit(
            "[bold cyan]LocAchievs Reset & Maintenance Center[/bold cyan]\n"
            f"[dim]Base Directory: {BASE_DIR}[/dim]",
            border_style="cyan",
        )
    )

    games_json_file = BASE_DIR / "games.json"
    hof_dir = BASE_DIR / "Hall of Fame"

    console.print("\n[bold white]Select an operation to perform:[/bold white]")
    console.print("  [bold cyan][1][/bold cyan] [bold white]Reset Web/Testing Environment[/bold white]")
    console.print("      [dim]• Empties 'Hall of Fame' directory[/dim]")
    console.print("      [dim]• Restores all 'done' games back to 'prepared' status in database[/dim]\n")
    console.print("  [bold cyan][2][/bold cyan] [bold white]Revert Game Folders to Clean State[/bold white]")
    console.print("      [dim]• Removes deployed emulator DLLs from game folders[/dim]")
    console.print("      [dim]• Restores original backed-up game DLLs from 'api_old'[/dim]")
    console.print("      [dim]• Deletes 'api_new' and 'api_old' folders[/dim]")
    console.print("      [dim]• Optional: Deletes 'steam_settings' folders[/dim]")
    console.print("      [dim]• Resets game status back to 'active'[/dim]\n")
    console.print("  [bold cyan][3][/bold cyan] [bold white]Complete Factory Reset (Both 1 and 2)[/bold white]")
    console.print("      [dim]• Executes Option 2 (Revert games) then Option 1 (Reset environment)[/dim]\n")
    console.print("  [bold red][0][/bold red] [dim]Cancel / Exit[/dim]\n")

    choice = console.input("[bold yellow]Enter option number [0-3]: [/bold yellow]").strip()

    if choice == "1":
        reset_web_testing_environment(games_json_file, hof_dir)
    elif choice == "2":
        revert_game_modifications(games_json_file)
    elif choice == "3":
        revert_game_modifications(games_json_file)
        console.print("\n" + "=" * 60 + "\n")
        reset_web_testing_environment(games_json_file, hof_dir)
    elif choice == "0" or not choice:
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
    else:
        console.print(f"\n[bold red]Invalid option selected: '{choice}'. Operation cancelled.[/bold red]")


if __name__ == "__main__":
    try:
        main_menu()
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
