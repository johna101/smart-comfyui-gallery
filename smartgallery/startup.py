# Smart Gallery for ComfyUI - Startup Functions
# Banner, update check, configuration validation, and initialization.

import os
import sys
import re
import urllib.request
import threading

from smartgallery.config import (
    Colors, APP_VERSION, APP_VERSION_DATE, GITHUB_REPO_URL, GITHUB_RAW_URL,
    BASE_OUTPUT_PATH, BASE_INPUT_PATH, SERVER_HOST, SERVER_PORT, ENABLE_AI_SEARCH,
    _settings_path
)
from smartgallery import state

# Try to import tkinter for GUI dialogs, but make it optional
try:
    import tkinter as tk
    from tkinter import messagebox
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False


def print_startup_banner():
    banner = rf"""
{Colors.GREEN}{Colors.BOLD}   _____                      _      _____       _ _
  / ____|                    | |    / ____|     | | |
 | (___  _ __ ___   __ _ _ __| |_  | |  __  __ _| | | ___ _ __ _   _
  \___ \| '_ ` _ \ / _` | '__| __| | | |_ |/ _` | | |/ _ \ '__| | | |
  ____) | | | | | | (_| | |  | |_  | |__| | (_| | | |  __/ |  | |_| |
 |_____/|_| |_| |_|\__,_|_|   \__|  \_____|\__,_|_|_|\___|_|   \__, |
                                                                __/ |
                                                               |___/ {Colors.RESET}
    """
    print(banner)
    print(f"   {Colors.BOLD}Smart Gallery for ComfyUI{Colors.RESET}")
    print(f"   Author     : {Colors.BLUE}Biagio Maffettone{Colors.RESET}")
    print(f"   Version    : {Colors.YELLOW}{APP_VERSION}{Colors.RESET} ({APP_VERSION_DATE})")
    print(f"   GitHub     : {Colors.CYAN}{GITHUB_REPO_URL}{Colors.RESET}")
    print(f"   Contributor: {Colors.CYAN}Martial Michel (Docker & Codebase){Colors.RESET}")
    print("")


def check_for_updates():
    """Checks the GitHub repo for a newer version without external libs."""
    print("Checking for updates...", end=" ", flush=True)
    try:
        with urllib.request.urlopen(GITHUB_RAW_URL, timeout=3) as response:
            content = response.read().decode('utf-8')

            match = re.search(r'APP_VERSION\s*=\s*["\']?([0-9.]+)["\']?', content)

            remote_version_str = None
            if match:
                remote_version_str = match.group(1)
            else:
                match_header = re.search(r'#\s*Version:\s*([0-9.]+)', content)
                if match_header:
                    remote_version_str = match_header.group(1)

            if remote_version_str:
                local_clean = re.sub(r'[^0-9.]', '', str(APP_VERSION))
                remote_clean = re.sub(r'[^0-9.]', '', str(remote_version_str))

                local_dots = local_clean.count('.')
                remote_dots = remote_clean.count('.')

                is_update_available = False

                if local_dots <= 1 and remote_dots <= 1:
                    try:
                        is_update_available = float(remote_clean) > float(local_clean)
                    except ValueError:
                        pass

                if not is_update_available:
                    local_v = tuple(map(int, local_clean.split('.'))) if local_clean else (0,)
                    remote_v = tuple(map(int, remote_clean.split('.'))) if remote_clean else (0,)
                    is_update_available = remote_v > local_v

                if is_update_available:
                    state.UPDATE_AVAILABLE = True
                    state.REMOTE_VERSION = remote_version_str
                    print(f"\n{Colors.YELLOW}{Colors.BOLD}NOTICE: A new version ({remote_version_str}) is available!{Colors.RESET}")
                else:
                    print("You are up to date.")
            else:
                print("Could not parse remote version.")

    except Exception:
        print("Skipped (Offline or GitHub unreachable).")


def show_config_error_and_exit(path):
    """Shows a critical error message and exits the program."""
    msg = (
        f"❌ CRITICAL ERROR: The specified path does not exist or is not accessible:\n\n"
        f"👉 {path}\n\n"
        f"INSTRUCTIONS:\n"
        f"1. Set 'comfyui_output_path' in your settings.json: {_settings_path}\n"
        f"2. Or set the BASE_OUTPUT_PATH environment variable.\n"
        f"3. Or use run_smartgallery.sh with the correct paths.\n\n"
        f"The program cannot continue and will now exit."
    )

    if TKINTER_AVAILABLE:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        messagebox.showerror("SmartGallery - Configuration Error", msg)
        root.destroy()
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}" + "="*70 + f"{Colors.RESET}")
        print(f"{Colors.RED}{Colors.BOLD}{msg}{Colors.RESET}")
        print(f"{Colors.RED}{Colors.BOLD}" + "="*70 + f"{Colors.RESET}\n")

    sys.exit(1)


def show_ffmpeg_warning():
    """Shows a non-blocking warning message for missing FFmpeg."""
    msg = (
        "WARNING: FFmpeg/FFprobe not found\n\n"
        "The system uses the 'ffprobe' utility to analyze video files. "
        "It seems it is missing or not configured correctly.\n\n"
        "CONSEQUENCES:\n"
        "❌ You will NOT be able to extract ComfyUI workflows from video files (.mp4, .mov, etc).\n"
        "✅ Gallery browsing, playback, and image features will still work perfectly.\n\n"
        "To fix this, install FFmpeg or check the 'FFPROBE_MANUAL_PATH' in the configuration."
    )

    if TKINTER_AVAILABLE:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        messagebox.showwarning("SmartGallery - Feature Limitation", msg)
        root.destroy()
    else:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}" + "="*70 + f"{Colors.RESET}")
        print(f"{Colors.YELLOW}{msg}{Colors.RESET}")
        print(f"{Colors.YELLOW}{Colors.BOLD}" + "="*70 + f"{Colors.RESET}\n")


def run_app():
    """Main entry point - startup checks and run the Flask server."""
    from smartgallery.config import print_configuration
    from smartgallery.folders import initialize_gallery, background_watcher_task
    from smartgallery import create_app

    print_startup_banner()
    check_for_updates()
    print_configuration()

    # --- CHECK: FIRST-RUN / NO CONFIG ---
    if not BASE_OUTPUT_PATH:
        import json as _json
        if not os.path.exists(_settings_path):
            template = {
                "comfyui_output_path": "/path/to/comfyui/output",
                "comfyui_input_path": "/path/to/comfyui/input",
                "ffprobe_path": "auto",
                "server_host": "0.0.0.0",
                "server_port": 8189,
                "delete_mode": "permanent",
                "thumbnail_width": 300,
                "enable_ai_search": False
            }
            try:
                with open(_settings_path, 'w') as f:
                    _json.dump(template, f, indent=2)
                    f.write('\n')
                print(f"\n{Colors.YELLOW}{Colors.BOLD}First run — created settings.json with placeholders:{Colors.RESET}")
                print(f"  {Colors.CYAN}{_settings_path}{Colors.RESET}\n")
                print(f"Edit it with your ComfyUI paths, then run again.\n")
            except OSError as e:
                print(f"\n{Colors.RED}{Colors.BOLD}SmartGallery is not configured.{Colors.RESET}\n")
                print(f"Could not create settings.json ({e}). Create it manually at:")
                print(f"  {Colors.CYAN}{_settings_path}{Colors.RESET}\n")
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}SmartGallery is not configured.{Colors.RESET}\n")
            print(f"Edit your settings.json with a valid ComfyUI output path:")
            print(f"  {Colors.CYAN}{_settings_path}{Colors.RESET}\n")

        print(f"Or set the {Colors.BOLD}BASE_OUTPUT_PATH{Colors.RESET} environment variable.\n")
        sys.exit(1)

    # --- CHECK: CRITICAL OUTPUT PATH CHECK ---
    if not os.path.exists(BASE_OUTPUT_PATH):
        show_config_error_and_exit(BASE_OUTPUT_PATH)

    # --- CHECK: INPUT PATH CHECK (Non-Blocking) ---
    if not BASE_INPUT_PATH or not os.path.exists(BASE_INPUT_PATH):
        print(f"{Colors.YELLOW}{Colors.BOLD}WARNING: Input Path not found!{Colors.RESET}")
        print(f"{Colors.YELLOW}   The path '{BASE_INPUT_PATH or '(not configured)'}' does not exist.{Colors.RESET}")
        print(f"{Colors.YELLOW}   > Source media visualization in Node Summary will be DISABLED.{Colors.RESET}")
        print(f"{Colors.YELLOW}   > The gallery will still function normally for output files.{Colors.RESET}\n")

    # Initialize the gallery (Creates DB, Migrations, etc.)
    initialize_gallery()

    # --- CHECK: FFMPEG WARNING ---
    if not state.FFPROBE_EXECUTABLE_PATH:
        if os.environ.get('DISPLAY') or os.name == 'nt':
            try:
                show_ffmpeg_warning()
            except Exception:
                print(f"{Colors.RED}WARNING: FFmpeg not found. Video workflows extraction disabled.{Colors.RESET}")
        else:
            print(f"{Colors.RED}WARNING: FFmpeg not found. Video workflows extraction disabled.{Colors.RESET}")

    # --- START BACKGROUND WATCHERS ---
    if ENABLE_AI_SEARCH:
        try:
            watcher = threading.Thread(target=background_watcher_task, daemon=True)
            watcher.start()
            print(f"{Colors.BLUE}INFO: AI Background Watcher started.{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}ERROR: Failed to start AI Watcher: {e}{Colors.RESET}")

    # Start filesystem watcher for real-time change detection
    try:
        from smartgallery.watcher import start_watcher
        fs_observer = start_watcher()
        if fs_observer:
            print(f"{Colors.BLUE}INFO: File watcher started on {BASE_OUTPUT_PATH}{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.YELLOW}WARNING: File watcher not available: {e}{Colors.RESET}")

    # Create and run the Flask app
    app = create_app()

    print(f"{Colors.GREEN}{Colors.BOLD}🚀 Gallery started successfully!{Colors.RESET}")

    # Discover all network interfaces for a useful access URL
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

    if SERVER_HOST == '0.0.0.0':
        import socket
        print(f"👉 Access URLs:")
        print(f"   {Colors.CYAN}http://localhost:{SERVER_PORT}/galleryout/{Colors.RESET}  (local)")
        try:
            # Get all non-loopback IPv4 addresses
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if not ip.startswith('127.'):
                    print(f"   {Colors.CYAN}{Colors.BOLD}http://{ip}:{SERVER_PORT}/galleryout/{Colors.RESET}")
        except Exception:
            pass
    else:
        print(f"👉 Access URL: {Colors.CYAN}{Colors.BOLD}http://{SERVER_HOST}:{SERVER_PORT}/galleryout/{Colors.RESET}")

    if debug_mode:
        print(f"   {Colors.YELLOW}Debug mode: ON (Vite dev server expected on :5173){Colors.RESET}")
    print(f"   (Press CTRL+C to stop)\n")

    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=debug_mode)
