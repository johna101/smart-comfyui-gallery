# Smart Gallery for ComfyUI - Folder Management Routes
# Create, mount, unmount, rename, delete folders and filesystem browsing.

import os
import re
import hashlib
import shutil
import time
import subprocess
import sys
from flask import Blueprint, request, jsonify, abort

from smartgallery.config import BASE_OUTPUT_PATH, PROTECTED_FOLDER_KEYS
from smartgallery.models import get_db_connection
from smartgallery.folders import get_dynamic_folder_config, sync_folder_on_demand
from smartgallery.events import publish_event
from smartgallery import state
from smartgallery.queries import (
    MOUNTED_INSERT, MOUNTED_SELECT_BY_PATH, MOUNTED_DELETE,
    FILES_SELECT_ID_PATH_ALL, FILES_DELETE_BY_ID_BATCH, FILES_DELETE_BY_PATH_LIKE,
)

folders_bp = Blueprint('folders_routes', __name__, url_prefix='/galleryout')


def _begin_folder_operation():
    """Stop watcher entirely before a folder mutation."""
    state.folder_operation_in_progress = True
    # Cancel any pending restart from a previous operation
    if state.watcher_restart_timer:
        state.watcher_restart_timer.cancel()
        state.watcher_restart_timer = None
    observer = state.watcher_observer
    if observer:
        try:
            observer.stop()
            observer.join(timeout=5)
        except Exception:
            pass
        state.watcher_observer = None
    handler = state.watcher_handler
    if handler:
        handler.cancel_all_timers()


def _end_folder_operation():
    """Restart watcher immediately but keep suppression flag set briefly.
    The watcher is back online for new ComfyUI output, but FSEvents replay
    from the folder op is absorbed by the _suppressed() checks in handlers."""
    import threading as _threading

    # Restart watcher now — it's online but events are still suppressed
    try:
        from smartgallery.watcher import start_watcher
        start_watcher()
    except Exception as e:
        print(f"WARNING: Failed to restart file watcher: {e}")

    # Clear flag after 3s — enough for FSEvents to flush its replay buffer
    def _clear():
        state.watcher_restart_timer = None
        state.folder_operation_in_progress = False
    timer = _threading.Timer(3.0, _clear)
    state.watcher_restart_timer = timer
    timer.start()


def _rebase_file_records(conn, old_path, new_path):
    """Rewrite file DB records and AI watch paths when a folder is renamed or moved.

    Computes new file paths by replacing the old_path prefix with new_path,
    generates new content-addressed IDs, cleans ghost collisions, and
    updates mounted folder paths.
    """
    all_files = conn.execute(FILES_SELECT_ID_PATH_ALL).fetchall()

    update_data = []
    collision_ids = []
    is_windows = (os.name == 'nt')
    check_old = old_path.lower() if is_windows else old_path

    for row in all_files:
        current_path = row['path']
        check_curr = current_path.lower() if is_windows else current_path

        if check_curr.startswith(check_old):
            suffix = current_path[len(old_path):]
            new_file_path = new_path + suffix
            new_id = hashlib.md5(new_file_path.encode()).hexdigest()
            update_data.append((new_id, new_file_path, row['id']))
            collision_ids.append(new_id)

    if collision_ids:
        placeholders = ','.join(['?'] * len(collision_ids))
        conn.execute(FILES_DELETE_BY_ID_BATCH.format(placeholders=placeholders), collision_ids)

    if update_data:
        conn.executemany("UPDATE files SET id = ?, path = ? WHERE id = ?", update_data)


@folders_bp.route('/create_folder', methods=['POST'])
def create_folder():
    data = request.json
    parent_key = data.get('parent_key', '_root_')

    raw_name = data.get('folder_name', '').strip()
    folder_name = re.sub(r'[\\/:*?"<>|]', '', raw_name)

    if not folder_name or folder_name in ['.', '..']:
        return jsonify({'status': 'error', 'message': 'Invalid folder name provided.'}), 400

    folders = get_dynamic_folder_config()
    if parent_key not in folders: return jsonify({'status': 'error', 'message': 'Parent folder not found.'}), 404
    parent_path = folders[parent_key]['path']
    new_folder_path = os.path.join(parent_path, folder_name)
    try:
        os.makedirs(new_folder_path, exist_ok=False)
        sync_folder_on_demand(parent_path)
        publish_event("folder_created", {"parent_key": parent_key, "folder_name": folder_name})
        return jsonify({'status': 'success', 'message': f'Folder "{folder_name}" created successfully.'})
    except FileExistsError: return jsonify({'status': 'error', 'message': 'Folder already exists.'}), 400
    except Exception as e: return jsonify({'status': 'error', 'message': str(e)}), 500


@folders_bp.route('/mount_folder', methods=['POST'])
def mount_folder():
    data = request.json
    link_name_raw = data.get('link_name', '').strip()
    target_path_raw = data.get('target_path', '').strip()

    # Sanitize name
    link_name = re.sub(r'[\\/:*?"<>|]', '', link_name_raw)

    if not link_name or not target_path_raw:
        return jsonify({'status': 'error', 'message': 'Missing name or target path.'}), 400

    # Security: Normalize target path
    target_path = os.path.normpath(target_path_raw)

    if not os.path.exists(target_path) or not os.path.isdir(target_path):
        return jsonify({'status': 'error', 'message': f'Target path does not exist: {target_path}'}), 404

    # Construct link path inside BASE_OUTPUT_PATH
    link_full_path = os.path.join(BASE_OUTPUT_PATH, link_name)

    if os.path.exists(link_full_path):
        return jsonify({'status': 'error', 'message': 'A folder with this name already exists.'}), 409

    try:
        if os.name == 'nt':
            # --- WINDOWS ROBUST LOGIC ---

            # 1. Force Windows-style backslashes for cmd.exe compatibility
            win_link = link_full_path.replace('/', '\\')
            win_target = target_path.replace('/', '\\')

            # Attempt 1: Junction (/J)
            cmd_junction = f'mklink /J "{win_link}" "{win_target}"'

            result = subprocess.run(cmd_junction, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            if result.returncode != 0:
                err_junction = result.stderr.strip() or result.stdout.strip() or "Unknown Error"

                print(f"WARN: Junction failed ({err_junction}). Trying Symlink fallback...")

                # Attempt 2: Symbolic Link (/D)
                cmd_symlink = f'mklink /D "{win_link}" "{win_target}"'
                result_sym = subprocess.run(cmd_symlink, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                if result_sym.returncode != 0:
                    err_sym = result_sym.stderr.strip() or result_sym.stdout.strip()

                    error_msg = (
                        f"Failed to create link.\n\n"
                        f"Attempt 1 (Junction): {err_junction}\n"
                        f"Attempt 2 (Symlink): {err_sym}\n\n"
                        f"TIP: If using Virtual Drives or Network Shares, try running ComfyUI as Administrator."
                    )
                    raise Exception(error_msg)

        else:
            # LINUX/MAC: Standard symlink
            os.symlink(target_path, link_full_path)

        # Register in DB
        with get_db_connection() as conn:
            norm_link_path = os.path.normpath(link_full_path).replace('\\', '/')
            conn.execute(MOUNTED_INSERT, (norm_link_path, target_path, time.time()))
            conn.commit()

        # Refresh Cache
        get_dynamic_folder_config(force_refresh=True)

        publish_event("folder_mounted", {"link_name": link_name})
        return jsonify({'status': 'success', 'message': f'Successfully linked "{link_name}".'})

    except Exception as e:
        print(f"Mount Error: {e}")
        # Clean up if partially created
        if os.path.exists(link_full_path):
            try: os.rmdir(link_full_path)
            except OSError: pass
            try: os.unlink(link_full_path)
            except OSError: pass

        return jsonify({'status': 'error', 'message': str(e)}), 500


@folders_bp.route('/unmount_folder', methods=['POST'])
def unmount_folder():
    data = request.json
    folder_key = data.get('folder_key')

    folders = get_dynamic_folder_config()
    if folder_key not in folders: return jsonify({'status':'error', 'message':'Folder not found'}), 404

    folder_info = folders[folder_key]
    path_to_remove = folder_info['path']

    # Security Check: Ensure it is actually in the mounted_folders table
    is_safe_mount = False
    with get_db_connection() as conn:
        norm_path = os.path.normpath(path_to_remove).replace('\\', '/')
        row = conn.execute(MOUNTED_SELECT_BY_PATH, (norm_path,)).fetchone()
        if row: is_safe_mount = True

    if not is_safe_mount:
        return jsonify({'status':'error', 'message':'This folder is not a managed mount point. Cannot unmount.'}), 403

    try:
        # Remove the Link (Not the content)
        if os.name == 'nt':
            os.rmdir(path_to_remove)
        else:
            os.unlink(path_to_remove)

        # Cleanup DB
        with get_db_connection() as conn:
            # 1. Remove from Mounts registry
            conn.execute(MOUNTED_DELETE, (norm_path,))

            # 2. Remove the file records associated with this path from the Gallery DB
            clean_path_for_query = path_to_remove + os.sep + '%'
            conn.execute(FILES_DELETE_BY_PATH_LIKE, (clean_path_for_query,))

            conn.commit()

        get_dynamic_folder_config(force_refresh=True)
        publish_event("folder_unmounted", {"folder_key": folder_key})
        return jsonify({'status': 'success', 'message': 'Folder unmounted successfully.'})

    except Exception as e:
        print(f"Unmount Error: {e}")
        return jsonify({'status':'error', 'message':f"Error unmounting: {e}"}), 500


@folders_bp.route('/api/browse_filesystem', methods=['POST'])
def browse_filesystem():
    data = request.json
    # Get path safely, handling None
    raw_path = data.get('path', '')
    if raw_path is None: raw_path = ''
    current_path = str(raw_path).strip()

    response_data = {
        'current_path': '',
        'parent_path': '',
        'folders': [],
        'error': None
    }

    # --- BLOCK 1: LIST DRIVES (WINDOWS) OR ROOT ---
    if not current_path or current_path == 'Computer':
        response_data['current_path'] = 'Computer'

        if os.name == 'nt':
            drives = []
            import string
            for letter in string.ascii_uppercase:
                drive_path = f'{letter}:\\'
                try:
                    if os.path.isdir(drive_path):
                        drives.append({
                            'name': f'Drive ({letter}:)',
                            'path': drive_path,
                            'is_drive': True
                        })
                except Exception:
                    continue

            response_data['folders'] = drives
            return jsonify(response_data)

        else:
            current_path = '/'

    # --- BLOCK 2: SCAN FOLDER CONTENT ---
    try:
        current_path = os.path.normpath(current_path)
        items = []

        with os.scandir(current_path) as it:
            for entry in it:
                try:
                    if entry.is_dir() and not entry.name.startswith('.'):
                        items.append({
                            'name': entry.name,
                            'path': entry.path,
                            'is_drive': False
                        })
                except Exception:
                    continue

        items.sort(key=lambda x: x['name'].lower())
        response_data['folders'] = items
        response_data['current_path'] = current_path

        # Calculate "Up" button (Parent) — at filesystem root, dirname == path
        parent = os.path.dirname(current_path)
        response_data['parent_path'] = '' if parent == current_path else parent

    except Exception as e:
        response_data['error'] = f"Error accessing folder: {str(e)}"

    return jsonify(response_data)


@folders_bp.route('/rename_folder/<string:folder_key>', methods=['POST'])
def rename_folder(folder_key):
    if folder_key in PROTECTED_FOLDER_KEYS: return jsonify({'status': 'error', 'message': 'This folder cannot be renamed.'}), 403

    raw_name = request.json.get('new_name', '').strip()
    new_name = re.sub(r'[\\/:*?"<>|]', '', raw_name)

    if not new_name or new_name in ['.', '..']:
        return jsonify({'status': 'error', 'message': 'Invalid name.'}), 400

    folders = get_dynamic_folder_config()
    if folder_key not in folders: return jsonify({'status': 'error', 'message': 'Folder not found.'}), 400

    old_folder_path = folders[folder_key]['path']
    new_folder_path = os.path.join(os.path.dirname(old_folder_path), new_name)

    if os.path.exists(os.path.normpath(new_folder_path)):
        return jsonify({'status': 'error', 'message': 'A folder with this name already exists.'}), 400

    try:
        _begin_folder_operation()

        try:
            os.rename(os.path.normpath(old_folder_path), os.path.normpath(new_folder_path))
        except Exception as e:
            print(f"Rename Error (filesystem): {e}")
            return jsonify({'status': 'error', 'message': f'Error: {e}'}), 500

        try:
            with get_db_connection() as conn:
                _rebase_file_records(conn, old_folder_path, new_folder_path)
                conn.commit()
        except Exception as e:
            print(f"WARNING: Folder renamed on disk but DB update failed (will reconcile on next scan): {e}")

    finally:
        _end_folder_operation()

    get_dynamic_folder_config(force_refresh=True)
    publish_event("folder_renamed", {"folder_key": folder_key, "new_name": new_name})
    return jsonify({'status': 'success', 'message': 'Folder renamed.'})


@folders_bp.route('/move_folder/<string:folder_key>', methods=['POST'])
def move_folder(folder_key):
    """Move a folder to a new parent directory."""
    if folder_key in PROTECTED_FOLDER_KEYS:
        return jsonify({'status': 'error', 'message': 'This folder cannot be moved.'}), 403

    dest_key = request.json.get('destination_folder')
    if not dest_key:
        return jsonify({'status': 'error', 'message': 'No destination folder provided.'}), 400

    folders = get_dynamic_folder_config(force_refresh=True)
    if folder_key not in folders:
        return jsonify({'status': 'error', 'message': 'Folder not found.'}), 404
    if dest_key not in folders:
        return jsonify({'status': 'error', 'message': 'Destination folder not found.'}), 404

    old_folder_path = folders[folder_key]['path']
    folder_name = folders[folder_key]['display_name']
    dest_path = folders[dest_key]['path']

    # Prevent moving into itself or a subfolder of itself
    dest_norm = os.path.normpath(dest_path).replace('\\', '/')
    old_norm = os.path.normpath(old_folder_path).replace('\\', '/')
    if dest_norm == old_norm or dest_norm.startswith(old_norm + '/'):
        return jsonify({'status': 'error', 'message': 'Cannot move a folder into itself.'}), 400

    new_folder_path = os.path.join(dest_path, folder_name)

    if os.path.exists(os.path.normpath(new_folder_path)):
        return jsonify({'status': 'error', 'message': f'A folder named "{folder_name}" already exists in the destination.'}), 400

    try:
        # Suppress watcher events during the move to prevent cascade
        _begin_folder_operation()

        # Filesystem move first — if this fails, nothing to roll back
        try:
            shutil.move(os.path.normpath(old_folder_path), os.path.normpath(new_folder_path))
        except Exception as e:
            print(f"Move Folder Error (filesystem): {e}")
            return jsonify({'status': 'error', 'message': f'Error: {e}'}), 500

        # Rewrite DB paths to match the new location
        try:
            with get_db_connection() as conn:
                _rebase_file_records(conn, old_folder_path, new_folder_path)
                conn.commit()
        except Exception as e:
            print(f"WARNING: Folder moved on disk but DB update failed (will reconcile on next scan): {e}")

    finally:
        _end_folder_operation()

    get_dynamic_folder_config(force_refresh=True)
    publish_event("folder_moved", {
        "folder_key": folder_key,
        "dest_key": dest_key,
        "folder_name": folder_name,
    })
    return jsonify({'status': 'success', 'message': f'Folder "{folder_name}" moved successfully.'})


@folders_bp.route('/delete_folder/<string:folder_key>', methods=['POST'])
def delete_folder(folder_key):
    if folder_key in PROTECTED_FOLDER_KEYS: return jsonify({'status': 'error', 'message': 'This folder cannot be deleted.'}), 403
    folders = get_dynamic_folder_config()
    if folder_key not in folders: return jsonify({'status': 'error', 'message': 'Folder not found.'}), 404
    try:
        folder_path = folders[folder_key]['path']
        with get_db_connection() as conn:
            # 1. Remove files from DB
            conn.execute(FILES_DELETE_BY_PATH_LIKE, (folder_path + os.sep + '%',))
            conn.commit()

        # 3. Physical deletion
        shutil.rmtree(folder_path)

        get_dynamic_folder_config(force_refresh=True)
        parent_key = folders[folder_key].get('parent', '_root_')
        publish_event("folder_deleted", {"folder_key": folder_key, "parent_key": parent_key})
        return jsonify({'status': 'success', 'message': 'Folder deleted.'})
    except Exception as e: return jsonify({'status': 'error', 'message': f'Error: {e}'}), 500
