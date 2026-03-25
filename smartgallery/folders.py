# Smart Gallery for ComfyUI - Folder Management Module
# Folder configuration, database sync, initialization, and background watcher functions.

import os
import json
import time
import sqlite3
import threading
import concurrent.futures

from tqdm import tqdm

from smartgallery.config import (
    BASE_OUTPUT_PATH, BASE_INPUT_PATH, BASE_SMARTGALLERY_PATH,
    ENABLE_AI_SEARCH, THUMBNAIL_CACHE_DIR, SQLITE_CACHE_DIR,
    THUMBNAIL_CACHE_FOLDER_NAME, SQLITE_CACHE_FOLDER_NAME,
    ZIP_CACHE_FOLDER_NAME, AI_MODELS_FOLDER_NAME,
    BATCH_SIZE, MAX_PARALLEL_WORKERS, MAX_PREFIX_DROPDOWN_ITEMS,
    Colors, path_to_key
)
from smartgallery.models import get_db_connection, init_db
from smartgallery.processing import process_single_file, find_ffprobe_path
from smartgallery.utils import get_standardized_path
from smartgallery import state
from smartgallery.queries import (
    FILES_UPSERT, FILES_SELECT_PATH_MTIME_ALL, FILES_DELETE_BY_PATH,
    FILES_SELECT_PATH_MTIME_FOLDER, FILES_COUNT,
    MOUNTED_SELECT_ALL, AI_WATCHED_SELECT, AI_WATCHED_SELECT_PATHS,
    AI_INDEX_QUEUE_DELETE_COMPLETED_OLD, AI_INDEX_QUEUE_CHECK_ACTIVE,
    FILES_SELECT_AI_STATUS, FILES_SELECT_AI_STATUS_NORMALIZED,
    AI_INDEX_QUEUE_UPSERT, EVENT_LOG_PRUNE,
)


def get_dynamic_folder_config(force_refresh=False):
    if state.folder_config_cache is not None and not force_refresh:
        return state.folder_config_cache

    print("INFO: Refreshing folder configuration by scanning directory tree...")

    base_path_normalized = os.path.normpath(BASE_OUTPUT_PATH).replace('\\', '/')

    try:
        root_mtime = os.path.getmtime(BASE_OUTPUT_PATH)
    except OSError:
        root_mtime = time.time()

    dynamic_config = {
        '_root_': {
            'display_name': 'Main',
            'path': base_path_normalized,
            'relative_path': '',
            'parent': None,
            'children': [],
            'mtime': root_mtime,
            'is_watched': False,
            'is_explicitly_watched': False,
            'is_mount': False # Root is never a mount
        }
    }

    try:
        # 1. Fetch Watched Status
        watched_rules = []
        if ENABLE_AI_SEARCH:
            try:
                with get_db_connection() as conn:
                    rows = conn.execute(AI_WATCHED_SELECT).fetchall()
                    for r in rows:
                        w_path = os.path.normpath(r['path']).replace('\\', '/')
                        watched_rules.append((w_path, bool(r['recursive'])))
            except Exception: pass

        # 2. Fetch Mounted Folders (New)
        mounted_paths = set()
        try:
            with get_db_connection() as conn:
                rows = conn.execute(MOUNTED_SELECT_ALL).fetchall()
                for r in rows:
                    # Normalize for comparison
                    mounted_paths.add(os.path.normpath(r['path']).replace('\\', '/'))
        except Exception: pass

        all_folders = {}
        for dirpath, dirnames, _ in os.walk(BASE_OUTPUT_PATH):
            dirnames[:] = [d for d in dirnames if not d.startswith('.') and d not in [THUMBNAIL_CACHE_FOLDER_NAME, SQLITE_CACHE_FOLDER_NAME, ZIP_CACHE_FOLDER_NAME, AI_MODELS_FOLDER_NAME]]
            for dirname in dirnames:
                full_path = os.path.normpath(os.path.join(dirpath, dirname)).replace('\\', '/')
                relative_path = os.path.relpath(full_path, BASE_OUTPUT_PATH).replace('\\', '/')
                try:
                    mtime = os.path.getmtime(full_path)
                except OSError:
                    mtime = time.time()

                all_folders[relative_path] = {
                    'full_path': full_path,
                    'display_name': dirname,
                    'mtime': mtime
                }

        sorted_paths = sorted(all_folders.keys(), key=lambda x: x.count('/'))

        for rel_path in sorted_paths:
            folder_data = all_folders[rel_path]
            key = path_to_key(rel_path)
            parent_rel_path = os.path.dirname(rel_path).replace('\\', '/')
            parent_key = '_root_' if parent_rel_path == '.' or parent_rel_path == '' else path_to_key(parent_rel_path)

            if parent_key in dynamic_config:
                dynamic_config[parent_key]['children'].append(key)

            current_path = folder_data['full_path']

            # Watch Logic
            is_watched_folder = False
            is_explicitly_watched = False
            for w_path, is_recursive in watched_rules:
                if current_path == w_path:
                    is_watched_folder = True
                    is_explicitly_watched = True
                    break
                if is_recursive and current_path.startswith(w_path + '/'):
                    is_watched_folder = True
                    break

            # Mount Logic
            is_mount = (current_path in mounted_paths)

            # NEW: Resolve the physical path (handles Symlinks/Junctions for subfolders too)
            real_path = os.path.realpath(current_path).replace('\\', '/')

            dynamic_config[key] = {
                'display_name': folder_data['display_name'],
                'path': current_path,
                'real_path': real_path, # <--- NEW FIELD
                'relative_path': rel_path,
                'parent': parent_key,
                'children': [],
                'mtime': folder_data['mtime'],
                'is_watched': is_watched_folder,
                'is_explicitly_watched': is_explicitly_watched,
                'is_mount': is_mount
            }
    except FileNotFoundError:
        print(f"WARNING: The base directory '{BASE_OUTPUT_PATH}' was not found.")

    state.folder_config_cache = dynamic_config
    return dynamic_config

# --- BACKGROUND WATCHER THREAD ---
def background_watcher_task():
    """
    Periodically scans watched folders.
    Ensures TRUE incremental indexing:
    1. Ignores files currently 'pending' or 'processing'.
    2. Checks 'files' DB: if ai_data is missing or outdated -> queues it.
    3. Revives 'completed'/'error' queue entries back to 'pending' if the file is dirty.
    """
    print("INFO: AI Background Watcher started (Incremental Mode).")
    while True:
        try:
            if ENABLE_AI_SEARCH:
                with get_db_connection() as conn:
                    # 1. Cleanup very old jobs to keep table light (> 3 days)
                    conn.execute(AI_INDEX_QUEUE_DELETE_COMPLETED_OLD, (time.time() - 259200,))

                    watched = conn.execute(AI_WATCHED_SELECT).fetchall()

                    for row in watched:
                        folder_path = row['path']
                        is_recursive = row['recursive']

                        valid_exts = {'.png','.jpg','.jpeg','.webp','.gif','.mp4','.mov','.avi','.webm'}
                        EXCLUDED = {'.thumbnails_cache', '.sqlite_cache', '.zip_downloads', '.AImodels', 'venv', 'venv-ai', '.git'}

                        files_to_check = []

                        if os.path.isdir(folder_path):
                            if is_recursive:
                                for root, dirs, files in os.walk(folder_path, topdown=True):
                                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in EXCLUDED]
                                    for f in files:
                                        if os.path.splitext(f)[1].lower() in valid_exts:
                                            files_to_check.append(os.path.join(root, f))
                            else:
                                try:
                                    for f in os.listdir(folder_path):
                                        full = os.path.join(folder_path, f)
                                        if os.path.isfile(full) and os.path.splitext(f)[1].lower() in valid_exts:
                                            files_to_check.append(full)
                                except OSError: pass

                        # Process Candidates
                        for raw_path in files_to_check:
                            p_key = get_standardized_path(raw_path)

                            # 1. CHECK ACTIVE STATUS
                            # Only skip if it is actively waiting or running.
                            # Do NOT skip if it is 'completed' or 'error' (we might need to retry/update).
                            active_job = conn.execute(AI_INDEX_QUEUE_CHECK_ACTIVE, (p_key,)).fetchone()

                            if active_job:
                                continue # Busy, come back later

                            # 2. CHECK FILE STATE IN DB
                            # We need to find the file ID and its scan timestamp
                            # We use the robust path lookup logic (normalized slash match)
                            # to ensure we find the record even if slashes differ.

                            # Try exact match first
                            file_row = conn.execute(FILES_SELECT_AI_STATUS, (raw_path,)).fetchone()

                            # Fallback: Normalized Match
                            if not file_row:
                                norm_p = raw_path.replace('\\', '/')
                                file_row = conn.execute(FILES_SELECT_AI_STATUS_NORMALIZED, (norm_p,)).fetchone()

                            if not file_row:
                                # File exists on disk but NOT in DB.
                                # We cannot index it yet (missing metadata/dimensions).
                                # The main 'files' sync must run first. We skip it silently.
                                continue

                            file_id = file_row['id']
                            last_scan_ts = file_row['ai_last_scanned'] if file_row['ai_last_scanned'] is not None else 0
                            mtime = file_row['mtime']

                            # 3. DIRTY CHECK (The Core Incremental Logic)
                            needs_index = False

                            if last_scan_ts == 0:
                                needs_index = True # Never scanned or Reset by user
                            elif last_scan_ts < mtime:
                                needs_index = True # File modified on disk after last scan

                            if needs_index:
                                # UPSERT: If exists (e.g. 'completed'), revive to 'pending'. If new, insert.
                                # This fixes the issue where completed items were ignored even after reset.
                                conn.execute(AI_INDEX_QUEUE_UPSERT, (p_key, file_id, time.time()))

                    conn.commit()

        except Exception as e:
            print(f"Watcher Loop Error: {e}")

        time.sleep(10) # Faster check cycle (10s instead of 60s) to feel responsive

def full_sync_database(conn):
    print("INFO: Starting full file scan...")
    start_time = time.time()

    all_folders = get_dynamic_folder_config(force_refresh=True)
    db_files = {row['path']: row['mtime'] for row in conn.execute(FILES_SELECT_PATH_MTIME_ALL).fetchall()}

    disk_files = {}
    print("INFO: Scanning directories on disk...")

    # Whitelist approach: Only index valid media files
    valid_extensions = {
        '.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp', '.gif',  # Images
        '.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v', '.wmv', '.flv', '.mts', '.ts', # Videos
        '.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac' # Audio
    }

    for folder_data in all_folders.values():
        folder_path = folder_data['path']
        if not os.path.isdir(folder_path): continue
        try:
            for name in os.listdir(folder_path):
                filepath = os.path.join(folder_path, name)

                # Skip macOS resource fork files (._filename)
                if name.startswith('._'):
                    continue
                # Check extension against whitelist
                _, ext = os.path.splitext(name)
                if os.path.isfile(filepath) and ext.lower() in valid_extensions:
                    disk_files[filepath] = os.path.getmtime(filepath)

        except OSError as e:
            print(f"WARNING: Could not access folder {folder_path}: {e}")

    db_paths = set(db_files.keys())
    disk_paths = set(disk_files.keys())

    to_delete = db_paths - disk_paths
    to_add = disk_paths - db_paths
    to_check = disk_paths & db_paths
    to_update = {path for path in to_check if int(disk_files.get(path, 0)) > int(db_files.get(path, 0))}

    files_to_process = list(to_add.union(to_update))
    # debug if files_to_process: print(f"{Colors.YELLOW}DEBUG - File to process: {files_to_process}{Colors.RESET}")
    if files_to_process:
        print(f"INFO: Processing {len(files_to_process)} files in parallel using up to {MAX_PARALLEL_WORKERS or 'all'} CPU cores...")

        results = []
        # --- CORRECT BLOCK FOR PROGRESS BAR ---
        with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
            # Submit all jobs to the pool and get future objects
            futures = {executor.submit(process_single_file, path): path for path in files_to_process}

            # Create the progress bar with the correct total
            with tqdm(total=len(files_to_process), desc="Processing files") as pbar:
                # Iterate over the jobs as they are COMPLETED
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        results.append(result)
                    # Update the bar by 1 step for each completed job
                    pbar.update(1)

        if results:
            print(f"INFO: Inserting {len(results)} processed records into the database...")
            for i in range(0, len(results), BATCH_SIZE):
                batch = results[i:i + BATCH_SIZE]
                conn.executemany(FILES_UPSERT, batch)
                conn.commit()

    # SAFETY GUARD FOR DISCONNECTED DRIVES
    if to_delete:
        print(f"INFO: Detecting disconnected drives before cleanup...")

        # 1. Identify Offline Mounts
        # We fetch all configured mount points to check if their root is accessible
        mount_rows = conn.execute(MOUNTED_SELECT_ALL).fetchall()
        offline_prefixes = []

        for row in mount_rows:
            m_path = row['path']
            # If the mount root itself is missing, assume the drive is offline.
            # note: os.path.exists returns False for broken symlinks/junctions
            if not os.path.exists(m_path):
                print(f"{Colors.YELLOW}WARN: Mount point seems offline: {m_path}{Colors.RESET}")
                offline_prefixes.append(m_path)

        # 2. Filter files to delete
        # Only delete files if they do NOT belong to an offline mount
        safe_to_delete = []
        protected_count = 0

        for path_to_remove in to_delete:
            is_protected = False
            for offline_root in offline_prefixes:
                # Check if file path starts with the offline root path
                if path_to_remove.startswith(offline_root):
                    is_protected = True
                    break

            if is_protected:
                protected_count += 1
            else:
                safe_to_delete.append(path_to_remove)

        if protected_count > 0:
            print(f"{Colors.YELLOW}PROTECTION ACTIVE: Skipped deletion of {protected_count} files because their source drive appears offline.{Colors.RESET}")

        # 3. Proceed with safe deletion
        if safe_to_delete:
            print(f"INFO: Removing {len(safe_to_delete)} obsolete file entries from the database...")

            paths_to_remove = [(p,) for p in safe_to_delete]
            conn.executemany(FILES_DELETE_BY_PATH, paths_to_remove)

            # Clean AI Queue for validly deleted files
            std_paths_to_remove = [(get_standardized_path(p),) for p in safe_to_delete]
            conn.executemany("DELETE FROM ai_indexing_queue WHERE file_path = ?", std_paths_to_remove)

            conn.commit()

    print(f"INFO: Full scan completed in {time.time() - start_time:.2f} seconds.")

def sync_folder_on_demand(folder_path):
    yield f"data: {json.dumps({'message': 'Checking folder for changes...', 'current': 0, 'total': 1})}\n\n"

    try:
        with get_db_connection() as conn:
            disk_files, valid_extensions = {}, {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.mkv', '.webm', '.mov', '.avi', '.mp3', '.wav', '.ogg', '.flac'}
            if os.path.isdir(folder_path):
                for name in os.listdir(folder_path):
                    if name.startswith('._'):
                        continue  # Skip macOS resource fork files
                    filepath = os.path.join(folder_path, name)
                    if os.path.isfile(filepath) and os.path.splitext(name)[1].lower() in valid_extensions:
                        disk_files[filepath] = os.path.getmtime(filepath)

            db_files_query = conn.execute(FILES_SELECT_PATH_MTIME_FOLDER, (folder_path + os.sep + '%',)).fetchall()
            db_files = {row['path']: row['mtime'] for row in db_files_query if os.path.normpath(os.path.dirname(row['path'])) == os.path.normpath(folder_path)}

            disk_filepaths, db_filepaths = set(disk_files.keys()), set(db_files.keys())
            files_to_add = disk_filepaths - db_filepaths
            files_to_delete = db_filepaths - disk_filepaths
            files_to_update = {path for path in (disk_filepaths & db_filepaths) if int(disk_files[path]) > int(db_files[path])}

            if not files_to_add and not files_to_update and not files_to_delete:
                yield f"data: {json.dumps({'message': 'Folder is up-to-date.', 'status': 'no_changes', 'current': 1, 'total': 1})}\n\n"
                return

            files_to_process = list(files_to_add.union(files_to_update))
            total_files = len(files_to_process)

            if total_files > 0:
                yield f"data: {json.dumps({'message': f'Found {total_files} new/modified files. Processing...', 'current': 0, 'total': total_files})}\n\n"

                data_to_upsert = []
                processed_count = 0

                with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
                    futures = {executor.submit(process_single_file, path): path for path in files_to_process}

                    for future in concurrent.futures.as_completed(futures):
                        result = future.result()
                        if result:
                            data_to_upsert.append(result)

                        processed_count += 1
                        path = futures[future]
                        progress_data = {
                            'message': f'Processing: {os.path.basename(path)}',
                            'current': processed_count,
                            'total': total_files
                        }
                        yield f"data: {json.dumps(progress_data)}\n\n"

                if data_to_upsert:
                    conn.executemany(FILES_UPSERT, data_to_upsert)

            if files_to_delete:
                conn.executemany("DELETE FROM files WHERE path IN (?)", [(p,) for p in files_to_delete])

            conn.commit()
            yield f"data: {json.dumps({'message': 'Sync complete. Reloading...', 'status': 'reloading', 'current': total_files, 'total': total_files})}\n\n"

    except Exception as e:
        error_message = f"Error during sync: {e}"
        print(f"ERROR: {error_message}")
        yield f"data: {json.dumps({'message': error_message, 'current': 1, 'total': 1, 'error': True})}\n\n"

def scan_folder_and_extract_options(folder_path, recursive=False):
    """
    Scans the physical folder to count files and extract metadata.
    Supports recursive mode to include subfolders in the count.
    """
    extensions, prefixes = set(), set()
    file_count = 0
    try:
        if not os.path.isdir(folder_path):
            return 0, [], []

        if recursive:
            # Recursive scan using os.walk
            for root, dirs, files in os.walk(folder_path):
                # Filter out hidden/protected folders in-place
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in [THUMBNAIL_CACHE_FOLDER_NAME, SQLITE_CACHE_FOLDER_NAME, ZIP_CACHE_FOLDER_NAME, AI_MODELS_FOLDER_NAME]]
                for filename in files:
                    if filename.startswith('._'):
                        continue  # Skip macOS resource fork files
                    ext = os.path.splitext(filename)[1].lower()
                    if ext and ext not in ['.json', '.sqlite']:
                        file_count += 1
                        extensions.add(ext.lstrip('.'))
                        if '_' in filename: prefixes.add(filename.split('_')[0])
        else:
            # Single folder scan using os.scandir (faster)
            for entry in os.scandir(folder_path):
                if entry.is_file():
                    filename = entry.name
                    if filename.startswith('._'):
                        continue  # Skip macOS resource fork files
                    ext = os.path.splitext(filename)[1].lower()
                    if ext and ext not in ['.json', '.sqlite']:
                        file_count += 1
                        extensions.add(ext.lstrip('.'))
                        if '_' in filename: prefixes.add(filename.split('_')[0])

    except Exception as e:
        print(f"ERROR: Could not scan folder '{folder_path}': {e}")

    return file_count, sorted(list(extensions)), sorted(list(prefixes))

def cleanup_invalid_watched_folders(conn):
    """
    Checks if watched folders still exist on disk.
    [SAFE MODE]: If a folder is missing, we assumes it might be a disconnected drive
    and we DO NOT remove it automatically to prevent config loss.
    """
    try:
        rows = conn.execute(AI_WATCHED_SELECT_PATHS).fetchall()

        for row in rows:
            path = row['path']
            if not os.path.exists(path) or not os.path.isdir(path):
                # We just WARN the user, we do NOT delete the config.
                print(f"{Colors.YELLOW}WARN: Watched folder not found (Offline or Deleted): {path}")
                print(f"      Skipping AI checks for this folder. Config preserved.{Colors.RESET}")

    except Exception as e:
        print(f"ERROR checking watched folders: {e}")

def initialize_gallery():
    print("INFO: Initializing gallery...")
    state.FFPROBE_EXECUTABLE_PATH = find_ffprobe_path()
    os.makedirs(THUMBNAIL_CACHE_DIR, exist_ok=True)
    os.makedirs(SQLITE_CACHE_DIR, exist_ok=True)

    with get_db_connection() as conn:
        try:
            init_db(conn)
            # Prune old event log entries (keep 7 days)
            conn.execute(EVENT_LOG_PRUNE, (time.time() - 604800,))
            conn.commit()
            # Cleanup invalid watched folders before full sync
            if ENABLE_AI_SEARCH:
                cleanup_invalid_watched_folders(conn)
            # Force full sync on every startup to clean external deletions
            print(f"{Colors.BLUE}INFO: Performing startup consistency check...{Colors.RESET}")
            full_sync_database(conn)

        except sqlite3.DatabaseError as e:
            print(f"ERROR initializing database: {e}")


def get_filter_options_from_db(conn, scope, folder_path=None, recursive=False):
    """
    Extracts extensions and prefixes for dropdowns using a robust
    Python-side path filtering to handle mixed slashes and cross-platform issues.
    """
    extensions, prefixes = set(), set()
    prefix_limit_reached = False

    # Identical helper to gallery_view for consistency
    def safe_path_norm(p):
        if not p: return ""
        return os.path.normpath(str(p).replace('\\', '/')).replace('\\', '/').lower().rstrip('/')

    try:
        # We fetch all names and paths. For very large DBs (100k+ files),
        # this is still faster than failing with a wrong SQL LIKE.
        cursor = conn.execute("SELECT name, path FROM files")

        target_norm = safe_path_norm(folder_path)

        for row in cursor:
            f_path_raw = row['path']
            f_name = row['name']

            # NORMALIZATION STEP
            f_path_norm = safe_path_norm(f_path_raw)
            f_dir_norm = safe_path_norm(os.path.dirname(f_path_norm))

            # FILTERING LOGIC (Same as Gallery View)
            show_file = False
            if scope == 'global':
                show_file = True
            elif recursive:
                # Check if it's inside the target folder tree
                if f_path_norm.startswith(target_norm + '/'):
                    show_file = True
            else:
                # Strict local: must be in this exact folder
                if f_dir_norm == target_norm:
                    show_file = True

            if show_file:
                # 1. Extensions
                _, ext = os.path.splitext(f_name)
                if ext:
                    extensions.add(ext.lstrip('.').lower())

                # 2. Prefixes
                if not prefix_limit_reached and '_' in f_name:
                    pfx = f_name.split('_')[0]
                    if pfx:
                        prefixes.add(pfx)
                        if len(prefixes) > MAX_PREFIX_DROPDOWN_ITEMS:
                            prefix_limit_reached = True
                            prefixes.clear()

    except Exception as e:
        print(f"Error extracting options: {e}")

    return sorted(list(extensions)), sorted(list(prefixes)), prefix_limit_reached
