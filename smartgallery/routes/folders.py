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

folders_bp = Blueprint('folders_routes', __name__, url_prefix='/galleryout')


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
            conn.execute("INSERT OR REPLACE INTO mounted_folders (path, target_source, created_at) VALUES (?, ?, ?)",
                         (norm_link_path, target_path, time.time()))
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
        row = conn.execute("SELECT path FROM mounted_folders WHERE path = ?", (norm_path,)).fetchone()
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
            conn.execute("DELETE FROM mounted_folders WHERE path = ?", (norm_path,))

            # 2. Remove from AI Watch list (if present)
            conn.execute("DELETE FROM ai_watched_folders WHERE path = ?", (path_to_remove,))

            # 3. CRITICAL: Remove the file records associated with this path from the Gallery DB
            clean_path_for_query = path_to_remove + os.sep + '%'
            conn.execute("DELETE FROM files WHERE path LIKE ?", (clean_path_for_query,))

            # 4. Also clean pending AI jobs for these files
            std_path_prefix = path_to_remove.replace('\\', '/')
            conn.execute("DELETE FROM ai_indexing_queue WHERE file_path LIKE ?", (std_path_prefix + '/%',))

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

        # Calculate "Up" button (Parent)
        parent = os.path.dirname(current_path)
        if parent == current_path:
            if os.name == 'nt':
                parent = ''
            else:
                parent = ''

        response_data['parent_path'] = parent

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

    # 1. GET EXACT FOLDER PATH FROM CONFIG
    old_folder_path = folders[folder_key]['path']

    # 2. CONSTRUCT NEW FOLDER PATH
    if '/' in old_folder_path:
        parent_dir = old_folder_path.rsplit('/', 1)[0]
        new_folder_path = f"{parent_dir}/{new_name}"
    else:
        parent_dir = os.path.dirname(old_folder_path)
        new_folder_path = os.path.join(parent_dir, new_name)

    # Check existence
    if os.path.exists(os.path.normpath(new_folder_path)):
        return jsonify({'status': 'error', 'message': 'A folder with this name already exists.'}), 400

    try:
        with get_db_connection() as conn:
            all_files_cursor = conn.execute("SELECT id, path FROM files")

            update_data = []
            ids_to_clean_collisions = []

            # Prepare check
            is_windows = (os.name == 'nt')
            check_old = old_folder_path.lower() if is_windows else old_folder_path

            for row in all_files_cursor:
                current_path = row['path']
                check_curr = current_path.lower() if is_windows else current_path

                # Check containment
                if check_curr.startswith(check_old):

                    # 1. EXTRACT FILENAME
                    filename = os.path.basename(current_path)

                    # 2. CONSTRUCT NEW PATH EXACTLY LIKE THE SCANNER DOES
                    new_file_path = os.path.join(new_folder_path, filename)

                    # 3. GENERATE ID
                    new_id = hashlib.md5(new_file_path.encode()).hexdigest()

                    update_data.append((new_id, new_file_path, row['id']))
                    ids_to_clean_collisions.append(new_id)

            # Cleanup Ghost records
            if ids_to_clean_collisions:
                placeholders = ','.join(['?'] * len(ids_to_clean_collisions))
                conn.execute(f"DELETE FROM files WHERE id IN ({placeholders})", ids_to_clean_collisions)

            # Physical Rename
            os.rename(os.path.normpath(old_folder_path), os.path.normpath(new_folder_path))

            # Atomic DB Update
            if update_data:
                conn.executemany("UPDATE files SET id = ?, path = ? WHERE id = ?", update_data)

            # Update Watch List
            watched_folders = conn.execute("SELECT path FROM ai_watched_folders").fetchall()
            for row in watched_folders:
                w_path = row['path']
                w_check = w_path.lower() if is_windows else w_path

                if w_check == check_old:
                    conn.execute("UPDATE ai_watched_folders SET path = ? WHERE path = ?", (new_folder_path, w_path))
                elif w_check.startswith(check_old):
                    if is_windows:
                        suffix = w_path[len(old_folder_path):]
                        new_w_path = new_folder_path + suffix
                        conn.execute("UPDATE ai_watched_folders SET path = ? WHERE path = ?", (new_w_path, w_path))
                    else:
                        new_w_path = w_path.replace(old_folder_path, new_folder_path, 1)
                        conn.execute("UPDATE ai_watched_folders SET path = ? WHERE path = ?", (new_w_path, w_path))

            conn.commit()

        get_dynamic_folder_config(force_refresh=True)
        publish_event("folder_renamed", {"folder_key": folder_key, "new_name": new_name})
        return jsonify({'status': 'success', 'message': 'Folder renamed.'})

    except Exception as e:
        print(f"Rename Error: {e}")
        return jsonify({'status': 'error', 'message': f'Error: {e}'}), 500


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

    # Construct new path
    new_folder_path = f"{dest_path}/{folder_name}" if '/' in dest_path else os.path.join(dest_path, folder_name)

    if os.path.exists(os.path.normpath(new_folder_path)):
        return jsonify({'status': 'error', 'message': f'A folder named "{folder_name}" already exists in the destination.'}), 400

    try:
        with get_db_connection() as conn:
            all_files_cursor = conn.execute("SELECT id, path FROM files")

            update_data = []
            ids_to_clean_collisions = []

            is_windows = (os.name == 'nt')
            check_old = old_folder_path.lower() if is_windows else old_folder_path

            for row in all_files_cursor:
                current_path = row['path']
                check_curr = current_path.lower() if is_windows else current_path

                if check_curr.startswith(check_old):
                    # Preserve relative path structure within the moved folder
                    suffix = current_path[len(old_folder_path):]
                    new_file_path = new_folder_path + suffix

                    new_id = hashlib.md5(new_file_path.encode()).hexdigest()
                    update_data.append((new_id, new_file_path, row['id']))
                    ids_to_clean_collisions.append(new_id)

            # Cleanup ghost records
            if ids_to_clean_collisions:
                placeholders = ','.join(['?'] * len(ids_to_clean_collisions))
                conn.execute(f"DELETE FROM files WHERE id IN ({placeholders})", ids_to_clean_collisions)

            # Physical move
            shutil.move(os.path.normpath(old_folder_path), os.path.normpath(new_folder_path))

            # DB update
            if update_data:
                conn.executemany("UPDATE files SET id = ?, path = ? WHERE id = ?", update_data)

            # Update watch list
            watched_folders = conn.execute("SELECT path FROM ai_watched_folders").fetchall()
            for row in watched_folders:
                w_path = row['path']
                w_check = w_path.lower() if is_windows else w_path

                if w_check == check_old or w_check.startswith(check_old):
                    suffix = w_path[len(old_folder_path):]
                    new_w_path = new_folder_path + suffix
                    conn.execute("UPDATE ai_watched_folders SET path = ? WHERE path = ?", (new_w_path, w_path))

            conn.commit()

        get_dynamic_folder_config(force_refresh=True)
        publish_event("folder_moved", {
            "folder_key": folder_key,
            "dest_key": dest_key,
            "folder_name": folder_name,
        })
        return jsonify({'status': 'success', 'message': f'Folder "{folder_name}" moved successfully.'})

    except Exception as e:
        print(f"Move Folder Error: {e}")
        return jsonify({'status': 'error', 'message': f'Error: {e}'}), 500


@folders_bp.route('/delete_folder/<string:folder_key>', methods=['POST'])
def delete_folder(folder_key):
    if folder_key in PROTECTED_FOLDER_KEYS: return jsonify({'status': 'error', 'message': 'This folder cannot be deleted.'}), 403
    folders = get_dynamic_folder_config()
    if folder_key not in folders: return jsonify({'status': 'error', 'message': 'Folder not found.'}), 404
    try:
        folder_path = folders[folder_key]['path']
        with get_db_connection() as conn:
            # 1. Remove files from DB
            conn.execute("DELETE FROM files WHERE path LIKE ?", (folder_path + os.sep + '%',))

            # 2. AI WATCHED FOLDERS CLEANUP
            conn.execute("DELETE FROM ai_watched_folders WHERE path = ?", (folder_path,))
            conn.execute("DELETE FROM ai_watched_folders WHERE path LIKE ?", (folder_path + os.sep + '%',))

            conn.commit()

        # 3. Physical deletion
        shutil.rmtree(folder_path)

        get_dynamic_folder_config(force_refresh=True)
        parent_key = folders[folder_key].get('parent', '_root_')
        publish_event("folder_deleted", {"folder_key": folder_key, "parent_key": parent_key})
        return jsonify({'status': 'success', 'message': 'Folder deleted.'})
    except Exception as e: return jsonify({'status': 'error', 'message': f'Error: {e}'}), 500
