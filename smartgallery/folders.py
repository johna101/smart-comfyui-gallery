# Smart Gallery for ComfyUI - Folder Management Module
# Folder configuration, database sync, initialization, and background watcher functions.

import os
import json
import time
import sqlite3
import itertools
import threading
import concurrent.futures

from tqdm import tqdm

from smartgallery.config import (
    BASE_OUTPUT_PATH, BASE_INPUT_PATH, BASE_SMARTGALLERY_PATH,
    THUMBNAIL_CACHE_DIR, SQLITE_CACHE_DIR,
    THUMBNAIL_CACHE_FOLDER_NAME, SQLITE_CACHE_FOLDER_NAME,
    ZIP_CACHE_FOLDER_NAME,
    BATCH_SIZE, MAX_PARALLEL_WORKERS, MAX_PREFIX_DROPDOWN_ITEMS,
    Colors, path_to_key
)
from smartgallery.models import get_db_connection, init_db
from smartgallery.processing import process_single_file, find_ffprobe_path
from smartgallery import state
from smartgallery.events import event_bus, GalleryEvent, publish_event
from smartgallery.queries import (
    FILES_UPSERT, FILES_SELECT_PATH_MTIME_ALL, FILES_DELETE_BY_PATH,
    FILES_SELECT_PATH_MTIME_FOLDER, FILES_COUNT,
    MOUNTED_SELECT_ALL, EVENT_LOG_PRUNE,
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
            'is_mount': False # Root is never a mount
        }
    }

    try:
        # 1. Fetch Mounted Folders
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
            dirnames[:] = [d for d in dirnames if not d.startswith('.') and d not in [THUMBNAIL_CACHE_FOLDER_NAME, SQLITE_CACHE_FOLDER_NAME, ZIP_CACHE_FOLDER_NAME, '.AImodels']]
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
            is_mount = (current_path in mounted_paths)
            real_path = os.path.realpath(current_path).replace('\\', '/')

            dynamic_config[key] = {
                'display_name': folder_data['display_name'],
                'path': current_path,
                'real_path': real_path,
                'relative_path': rel_path,
                'parent': parent_key,
                'children': [],
                'mtime': folder_data['mtime'],
                'is_mount': is_mount
            }
    except FileNotFoundError:
        print(f"WARNING: The base directory '{BASE_OUTPUT_PATH}' was not found.")

    state.folder_config_cache = dynamic_config
    return dynamic_config

def _publish_scan_progress(processed, total, phase='processing'):
    """Push lightweight progress event to SSE clients (no DB persistence)."""
    event_bus.publish(GalleryEvent('scan_progress', {
        'processed': processed, 'total': total, 'phase': phase
    }, source='system'))


def full_sync_database(conn):
    print("INFO: Starting full file scan...")
    state.scan_in_progress = True
    _publish_scan_progress(0, 0, phase='started')
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
        total = len(files_to_process)
        num_workers = MAX_PARALLEL_WORKERS or os.cpu_count() or 4
        print(f"INFO: Processing {total} files in parallel using up to {num_workers} CPU cores...")

        chunk = []
        inserted = 0

        with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
            pending = set()
            file_iter = iter(files_to_process)
            done_count = 0

            # Seed the executor with a limited number of initial jobs
            for path in itertools.islice(file_iter, num_workers * 2):
                pending.add(executor.submit(process_single_file, path))

            with tqdm(total=total, desc="Processing files") as pbar:
                while pending:
                    # Wait for at least one future to complete
                    done, pending = concurrent.futures.wait(
                        pending, return_when=concurrent.futures.FIRST_COMPLETED
                    )

                    for future in done:
                        result = future.result()
                        if result:
                            chunk.append(result)
                        done_count += 1
                        pbar.update(1)

                    # Flush chunk to DB when ready
                    if len(chunk) >= BATCH_SIZE:
                        while state.folder_operation_in_progress:
                            time.sleep(0.5)
                        conn.executemany(FILES_UPSERT, chunk)
                        conn.commit()
                        inserted += len(chunk)
                        chunk = []

                    # Update UI progress every 100 files (decoupled from DB batch size)
                    if done_count % 100 < len(done):
                        _publish_scan_progress(inserted + len(chunk), total)

                    # Submit more work — but pause if a folder operation is active
                    if not state.folder_operation_in_progress:
                        for path in itertools.islice(file_iter, len(done)):
                            pending.add(executor.submit(process_single_file, path))

        # Flush remaining partial chunk
        if chunk:
            while state.folder_operation_in_progress:
                time.sleep(0.5)
            conn.executemany(FILES_UPSERT, chunk)
            conn.commit()
            inserted += len(chunk)

        if inserted:
            print(f"INFO: Inserted {inserted} processed records into the database.")

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
            while state.folder_operation_in_progress:
                time.sleep(0.5)
            print(f"INFO: Removing {len(safe_to_delete)} obsolete file entries from the database...")

            paths_to_remove = [(p,) for p in safe_to_delete]
            conn.executemany(FILES_DELETE_BY_PATH, paths_to_remove)
            conn.commit()

    state.scan_in_progress = False
    elapsed = time.time() - start_time
    print(f"INFO: Full scan completed in {elapsed:.2f} seconds.")
    _publish_scan_progress(0, 0, phase='complete')

def watcher_sync(conn):
    """Lightweight database sync triggered by filesystem watcher.

    Same reconciliation logic as full_sync_database (diff disk vs DB, process
    new/changed files, delete removed files) but without progress UI, tqdm,
    or scan_in_progress state. Designed to run frequently after small changes.

    Publishes a single 'watcher_sync_complete' SSE event when changes are found,
    so the frontend can refetch the current view.
    """
    start = time.time()
    all_folders = get_dynamic_folder_config(force_refresh=True)
    db_files = {row['path']: row['mtime'] for row in conn.execute(FILES_SELECT_PATH_MTIME_ALL).fetchall()}

    valid_extensions = {
        '.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp', '.gif',
        '.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v', '.wmv', '.flv', '.mts', '.ts',
        '.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac'
    }

    disk_files = {}
    for folder_data in all_folders.values():
        folder_path = folder_data['path']
        if not os.path.isdir(folder_path):
            continue
        try:
            for name in os.listdir(folder_path):
                if name.startswith('._'):
                    continue
                filepath = os.path.join(folder_path, name)
                _, ext = os.path.splitext(name)
                if os.path.isfile(filepath) and ext.lower() in valid_extensions:
                    disk_files[filepath] = os.path.getmtime(filepath)
        except OSError:
            pass

    db_paths = set(db_files.keys())
    disk_paths = set(disk_files.keys())

    to_delete = db_paths - disk_paths
    to_add = disk_paths - db_paths
    to_check = disk_paths & db_paths
    to_update = {p for p in to_check if int(disk_files.get(p, 0)) > int(db_files.get(p, 0))}

    files_to_process = list(to_add | to_update)
    added = 0
    removed = 0

    # Process new/changed files
    if files_to_process:
        chunk = []
        for filepath in files_to_process:
            if state.folder_operation_in_progress:
                break
            result = process_single_file(filepath)
            if result:
                chunk.append(result)
        if chunk:
            conn.executemany(FILES_UPSERT, chunk)
            conn.commit()
            added = len(chunk)

    # Delete removed files (skip files on offline mounts)
    if to_delete:
        mount_rows = conn.execute(MOUNTED_SELECT_ALL).fetchall()
        offline_prefixes = [
            row['path'] for row in mount_rows
            if not os.path.exists(row['path'])
        ]
        safe_to_delete = [
            p for p in to_delete
            if not any(p.startswith(prefix) for prefix in offline_prefixes)
        ]
        if safe_to_delete:
            conn.executemany(FILES_DELETE_BY_PATH, [(p,) for p in safe_to_delete])
            conn.commit()
            removed = len(safe_to_delete)

    elapsed = time.time() - start
    if added or removed:
        print(f"[Watcher] Sync: +{added} -{removed} ({elapsed:.2f}s)")
        publish_event("watcher_sync_complete", {
            "added": added,
            "removed": removed,
        }, source="watcher")
    else:
        logger = __import__('logging').getLogger(__name__)
        logger.debug("Watcher sync: no changes (%.2fs)", elapsed)


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
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in [THUMBNAIL_CACHE_FOLDER_NAME, SQLITE_CACHE_FOLDER_NAME, ZIP_CACHE_FOLDER_NAME, '.AImodels']]
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

def initialize_db():
    """Phase 1: Fast DB setup — migrations, pruning, dirs. Must complete before Flask starts."""
    print("INFO: Initializing database...")
    state.FFPROBE_EXECUTABLE_PATH = find_ffprobe_path()
    os.makedirs(THUMBNAIL_CACHE_DIR, exist_ok=True)
    os.makedirs(SQLITE_CACHE_DIR, exist_ok=True)

    with get_db_connection() as conn:
        try:
            init_db(conn)
            conn.execute(EVENT_LOG_PRUNE, (time.time() - 604800,))
            conn.commit()
        except sqlite3.DatabaseError as e:
            print(f"ERROR initializing database: {e}")


def run_startup_scan():
    """Phase 2: Full file scan — runs in background thread after Flask starts."""
    with get_db_connection() as conn:
        try:
            print(f"{Colors.BLUE}INFO: Performing startup consistency check...{Colors.RESET}")
            full_sync_database(conn)
        except sqlite3.DatabaseError as e:
            print(f"ERROR during startup scan: {e}")


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
