# Smart Gallery for ComfyUI - File Operations Routes
# Move, copy, delete, rename, and favorite operations.

import os
import hashlib
import shutil
import time
import re
from flask import Blueprint, request, jsonify, abort

from smartgallery.config import DELETE_TO
from smartgallery.models import get_db_connection
from smartgallery.processing import safe_delete_file
from smartgallery.folders import get_dynamic_folder_config

files_bp = Blueprint('files', __name__, url_prefix='/galleryout')


# --- Helper Functions (shared with media routes) ---

# Whitelist of columns allowed in dynamic SELECT to prevent SQL injection
_ALLOWED_COLUMNS = frozenset({'*', 'path', 'name', 'type', 'mtime', 'is_favorite', 'has_workflow'})

def get_file_info_from_db(file_id, column='*'):
    if column not in _ALLOWED_COLUMNS:
        raise ValueError(f"Invalid column: {column}")
    with get_db_connection() as conn:
        row = conn.execute(f"SELECT {column} FROM files WHERE id = ?", (file_id,)).fetchone()
    if not row: abort(404)
    return dict(row) if column == '*' else row[0]


def _get_unique_filepath(destination_folder, filename):
    """
    Generates a unique filepath using the NATIVE OS separator.
    This ensures that the path matches exactly what the Scanner generates,
    preventing duplicate records in the database.
    """
    base, ext = os.path.splitext(filename)
    counter = 1

    # Use standard os.path.join.
    # On Windows with base path "C:/A", it produces "C:/A\file.txt" (Matches your DB).
    # On Linux, it produces "C:/A/file.txt" (Matches Linux DB).
    full_path = os.path.join(destination_folder, filename)

    while os.path.exists(full_path):
        new_filename = f"{base}({counter}){ext}"
        full_path = os.path.join(destination_folder, new_filename)
        counter += 1

    return full_path


@files_bp.route('/move_batch', methods=['POST'])
def move_batch():
    data = request.json
    file_ids = data.get('file_ids', [])
    dest_key = data.get('destination_folder')

    folders = get_dynamic_folder_config()

    if not all([file_ids, dest_key, dest_key in folders]):
        return jsonify({'status': 'error', 'message': 'Invalid data provided.'}), 400

    moved_count, renamed_count, skipped_count = 0, 0, 0
    failed_files = []

    # Get destination path from config
    dest_path_raw = folders[dest_key]['path']

    with get_db_connection() as conn:
        # Pre-fetch all file metadata in one query to avoid N+1
        placeholders = ','.join(['?'] * len(file_ids))
        query_fetch = f"""
            SELECT id, path, name, size, has_workflow, is_favorite, type, duration, dimensions,
                   ai_last_scanned, ai_caption, ai_embedding, ai_error, workflow_files, workflow_prompt
            FROM files WHERE id IN ({placeholders})
        """
        all_rows = conn.execute(query_fetch, file_ids).fetchall()
        file_map = {row['id']: dict(row) for row in all_rows}

        for file_id in file_ids:
            source_path = None
            try:
                # 1. Fetch Source Data + AI Metadata (from pre-fetched map)
                file_info = file_map.get(file_id)

                if not file_info:
                    failed_files.append(f"ID {file_id} not found in DB")
                    continue

                source_path = file_info['path']
                source_filename = file_info['name']

                # Metadata Pack
                meta = {
                    'size': file_info['size'],
                    'has_workflow': file_info['has_workflow'],
                    'is_favorite': file_info['is_favorite'],
                    'type': file_info['type'],
                    'duration': file_info['duration'],
                    'dimensions': file_info['dimensions'],
                    'ai_last_scanned': file_info['ai_last_scanned'],
                    'ai_caption': file_info['ai_caption'],
                    'ai_embedding': file_info['ai_embedding'],
                    'ai_error': file_info['ai_error'],
                    'workflow_files': file_info['workflow_files'],
                    'workflow_prompt': file_info['workflow_prompt']
                }

                # Check Source vs Dest (OS Agnostic comparison)
                source_dir_norm = os.path.normpath(os.path.dirname(source_path))
                dest_dir_norm = os.path.normpath(dest_path_raw)
                is_same_folder = (source_dir_norm.lower() == dest_dir_norm.lower()) if os.name == 'nt' else (source_dir_norm == dest_dir_norm)

                if is_same_folder:
                    skipped_count += 1
                    continue

                if not os.path.exists(source_path):
                    failed_files.append(f"{source_filename} (not found on disk)")
                    conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
                    continue

                # 2. Calculate unique path NATIVELY (No separator forcing)
                # This guarantees the path string matches what the Scanner will see.
                final_dest_path = _get_unique_filepath(dest_path_raw, source_filename)
                final_filename = os.path.basename(final_dest_path)

                if final_filename != source_filename:
                    renamed_count += 1

                # 3. Move file on disk
                shutil.move(source_path, final_dest_path)

                # 4. Calculate New ID based on the NATIVE path
                new_id = hashlib.md5(final_dest_path.encode()).hexdigest()

                # 5. DB Update / Merge Logic
                existing_target = conn.execute("SELECT id FROM files WHERE id = ?", (new_id,)).fetchone()

                if existing_target:
                    # MERGE: Target exists (e.g. ghost record). Overwrite with source metadata.
                    query_merge = """
                        UPDATE files
                        SET path = ?, name = ?, mtime = ?,
                            size = ?, has_workflow = ?, is_favorite = ?,
                            type = ?, duration = ?, dimensions = ?,
                            ai_last_scanned = ?, ai_caption = ?, ai_embedding = ?, ai_error = ?,
                            workflow_files = ?, workflow_prompt = ?
                        WHERE id = ?
                    """
                    conn.execute(query_merge, (
                        final_dest_path, final_filename, time.time(),
                        meta['size'], meta['has_workflow'], meta['is_favorite'],
                        meta['type'], meta['duration'], meta['dimensions'],
                        meta['ai_last_scanned'], meta['ai_caption'], meta['ai_embedding'], meta['ai_error'],
                        meta['workflow_files'],
                        meta['workflow_prompt'],
                        new_id
                    ))
                    conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
                else:
                    # STANDARD: Update existing record path/name.
                    conn.execute("UPDATE files SET id = ?, path = ?, name = ? WHERE id = ?",
                                (new_id, final_dest_path, final_filename, file_id))

                moved_count += 1

            except Exception as e:
                filename_for_error = os.path.basename(source_path) if source_path else f"ID {file_id}"
                failed_files.append(filename_for_error)
                print(f"ERROR: Failed to move file {filename_for_error}. Reason: {e}")
                continue
        conn.commit()

    message = f"Successfully moved {moved_count} file(s)."
    if skipped_count > 0: message += f" {skipped_count} skipped (same folder)."
    if renamed_count > 0: message += f" {renamed_count} renamed."
    if failed_files: message += f" Failed: {len(failed_files)}."

    status = 'success'
    if failed_files or (skipped_count > 0 and moved_count == 0): status = 'partial_success'

    return jsonify({'status': status, 'message': message})


@files_bp.route('/copy_batch', methods=['POST'])
def copy_batch():
    data = request.json
    file_ids = data.get('file_ids', [])
    dest_key = data.get('destination_folder')
    keep_favorites = data.get('keep_favorites', False)

    folders = get_dynamic_folder_config()

    if not all([file_ids, dest_key, dest_key in folders]):
        return jsonify({'status': 'error', 'message': 'Invalid data provided.'}), 400

    dest_path_raw = folders[dest_key]['path']
    copied_count = 0
    failed_files = []

    with get_db_connection() as conn:
        # Pre-fetch all file metadata in one query to avoid N+1
        placeholders = ','.join(['?'] * len(file_ids))
        all_rows = conn.execute(f"SELECT * FROM files WHERE id IN ({placeholders})", file_ids).fetchall()
        file_map = {row['id']: dict(row) for row in all_rows}

        for file_id in file_ids:
            try:
                # 1. Fetch Source info (from pre-fetched map)
                file_info = file_map.get(file_id)
                if not file_info: continue

                source_path = file_info['path']
                source_filename = file_info['name']

                if not os.path.exists(source_path):
                    failed_files.append(f"{source_filename} (not found)")
                    continue

                # 2. Determine Destination Path (Auto-rename logic)
                # Helper function _get_unique_filepath handles (1), (2) etc.
                final_dest_path = _get_unique_filepath(dest_path_raw, source_filename)
                final_filename = os.path.basename(final_dest_path)

                # 3. Physical Copy (Metadata preserved via copy2)
                shutil.copy2(source_path, final_dest_path)

                # 4. Create DB Record
                new_id = hashlib.md5(final_dest_path.encode()).hexdigest()
                new_mtime = time.time() # New file gets new import time

                # Logic for Favorites
                is_fav = file_info['is_favorite'] if keep_favorites else 0

                # Insert Copy
                # We copy AI data too because the image content is identical!
                conn.execute("""
                    INSERT INTO files (
                        id, path, mtime, name, type, duration, dimensions, has_workflow,
                        size, is_favorite, last_scanned, workflow_files, workflow_prompt,
                        ai_last_scanned, ai_caption, ai_embedding, ai_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    new_id, final_dest_path, new_mtime, final_filename,
                    file_info['type'], file_info['duration'], file_info['dimensions'],
                    file_info['has_workflow'], file_info['size'],
                    is_fav, # User Choice
                    file_info['last_scanned'],
                    file_info['workflow_files'], file_info['workflow_prompt'],
                    file_info['ai_last_scanned'], file_info['ai_caption'], file_info['ai_embedding'], file_info['ai_error']
                ))

                copied_count += 1

            except Exception as e:
                print(f"COPY ERROR: {e}")
                failed_files.append(source_filename)

        conn.commit()

    msg = f"Successfully copied {copied_count} files."
    status = 'success'
    if failed_files:
        status = 'partial_success'
        msg += f" Failed: {len(failed_files)}"

    return jsonify({'status': status, 'message': msg})


@files_bp.route('/delete_batch', methods=['POST'])
def delete_batch():
    try:
        data = request.json
        file_ids = data.get('file_ids', [])

        if not file_ids:
            return jsonify({'status': 'error', 'message': 'No files selected.'}), 400

        deleted_count = 0
        failed_files = []
        ids_to_remove_from_db = []

        with get_db_connection() as conn:
            placeholders = ','.join(['?'] * len(file_ids))

            query_select = f"SELECT id, path FROM files WHERE id IN ({placeholders})"
            files_to_delete = conn.execute(query_select, file_ids).fetchall()

            for row in files_to_delete:
                file_path = row['path']
                file_id = row['id']

                try:
                    if os.path.exists(file_path):
                        safe_delete_file(file_path)

                    ids_to_remove_from_db.append(file_id)
                    deleted_count += 1

                except Exception as e:
                    print(f"ERROR: Could not delete {file_path}: {e}")
                    failed_files.append(os.path.basename(file_path))

            if ids_to_remove_from_db:
                db_placeholders = ','.join(['?'] * len(ids_to_remove_from_db))
                query_delete = f"DELETE FROM files WHERE id IN ({db_placeholders})"
                conn.execute(query_delete, ids_to_remove_from_db)
                conn.commit()

        action = "moved to trash" if DELETE_TO else "deleted"
        message = f'Successfully {action} {deleted_count} files.'

        status = 'success'
        if failed_files:
            message += f" Failed to delete {len(failed_files)} files."
            status = 'partial_success'

        return jsonify({'status': status, 'message': message})

    except Exception as e:
        print(f"CRITICAL ERROR in delete_batch: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@files_bp.route('/favorite_batch', methods=['POST'])
def favorite_batch():
    data = request.json
    file_ids, status = data.get('file_ids', []), data.get('status', False)
    if not file_ids: return jsonify({'status': 'error', 'message': 'No files selected'}), 400
    with get_db_connection() as conn:
        placeholders = ','.join('?' * len(file_ids))
        conn.execute(f"UPDATE files SET is_favorite = ? WHERE id IN ({placeholders})", [1 if status else 0] + file_ids)
        conn.commit()
    return jsonify({'status': 'success', 'message': f"Updated favorites for {len(file_ids)} files."})


@files_bp.route('/toggle_favorite/<string:file_id>', methods=['POST'])
def toggle_favorite(file_id):
    with get_db_connection() as conn:
        current = conn.execute("SELECT is_favorite FROM files WHERE id = ?", (file_id,)).fetchone()
        if not current: abort(404)
        new_status = 1 - current['is_favorite']
        conn.execute("UPDATE files SET is_favorite = ? WHERE id = ?", (new_status, file_id))
        conn.commit()
        return jsonify({'status': 'success', 'is_favorite': bool(new_status)})


# --- FIX: ROBUST DELETE ROUTE ---
@files_bp.route('/delete/<string:file_id>', methods=['POST'])
def delete_file(file_id):
    with get_db_connection() as conn:
        file_info = conn.execute("SELECT path FROM files WHERE id = ?", (file_id,)).fetchone()
        if not file_info:
            return jsonify({'status': 'success', 'message': 'File already deleted from database.'})

        filepath = file_info['path']

        try:
            if os.path.exists(filepath):
                safe_delete_file(filepath)
        except OSError as e:
            print(f"ERROR: Could not delete file {filepath} from disk: {e}")
            return jsonify({'status': 'error', 'message': f'Could not delete file from disk: {e}'}), 500

        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        conn.commit()
        action = "moved to trash" if DELETE_TO else "deleted"
        return jsonify({'status': 'success', 'message': f'File {action} successfully.'})


# --- RENAME FILE ---
@files_bp.route('/rename_file/<string:file_id>', methods=['POST'])
def rename_file(file_id):
    data = request.json
    new_name = data.get('new_name', '').strip()

    if not new_name or len(new_name) > 250:
        return jsonify({'status': 'error', 'message': 'Invalid filename.'}), 400
    if re.search(r'[\\/:"*?<>|]', new_name):
        return jsonify({'status': 'error', 'message': 'Invalid characters.'}), 400

    try:
        with get_db_connection() as conn:
            # 1. Fetch All Metadata
            query_fetch = """
                SELECT
                    path, name, size, has_workflow, is_favorite, type, duration, dimensions,
                    ai_last_scanned, ai_caption, ai_embedding, ai_error, workflow_files, workflow_prompt
                FROM files WHERE id = ?
            """
            file_info = conn.execute(query_fetch, (file_id,)).fetchone()

            if not file_info:
                return jsonify({'status': 'error', 'message': 'File not found.'}), 404

            old_path = file_info['path']
            old_name = file_info['name']

            # Metadata Pack
            meta = {
                'size': file_info['size'],
                'has_workflow': file_info['has_workflow'],
                'is_favorite': file_info['is_favorite'],
                'type': file_info['type'],
                'duration': file_info['duration'],
                'dimensions': file_info['dimensions'],
                'ai_last_scanned': file_info['ai_last_scanned'],
                'ai_caption': file_info['ai_caption'],
                'ai_embedding': file_info['ai_embedding'],
                'ai_error': file_info['ai_error'],
                'workflow_files': file_info['workflow_files'],
                'workflow_prompt': file_info['workflow_prompt']
            }

            # Extension logic
            _, old_ext = os.path.splitext(old_name)
            new_name_base, new_ext = os.path.splitext(new_name)
            final_new_name = new_name if new_ext else new_name + old_ext

            if final_new_name == old_name:
                return jsonify({'status': 'error', 'message': 'Name unchanged.'}), 400

            # 2. Construct Path NATIVELY using os.path.join
            dir_name = os.path.dirname(old_path)
            new_path = os.path.join(dir_name, final_new_name)

            if os.path.exists(new_path):
                 return jsonify({'status': 'error', 'message': f'File "{final_new_name}" already exists.'}), 409

            new_id = hashlib.md5(new_path.encode()).hexdigest()
            existing_db = conn.execute("SELECT id FROM files WHERE id = ?", (new_id,)).fetchone()

            os.rename(old_path, new_path)

            if existing_db:
                # MERGE SCENARIO
                query_merge = """
                    UPDATE files
                    SET path = ?, name = ?, mtime = ?,
                        size = ?, has_workflow = ?, is_favorite = ?,
                        type = ?, duration = ?, dimensions = ?,
                        ai_last_scanned = ?, ai_caption = ?, ai_embedding = ?, ai_error = ?,
                        workflow_files = ?, workflow_prompt = ?
                    WHERE id = ?
                """
                conn.execute(query_merge, (
                    new_path, final_new_name, time.time(),
                    meta['size'], meta['has_workflow'], meta['is_favorite'],
                    meta['type'], meta['duration'], meta['dimensions'],
                    meta['ai_last_scanned'], meta['ai_caption'], meta['ai_embedding'], meta['ai_error'],
                    meta['workflow_files'],
                    meta['workflow_prompt'],
                    new_id
                ))
                conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
            else:
                # STANDARD SCENARIO
                conn.execute("UPDATE files SET id = ?, path = ?, name = ? WHERE id = ?",
                            (new_id, new_path, final_new_name, file_id))

            conn.commit()

            return jsonify({
                'status': 'success',
                'message': 'File renamed.',
                'new_name': final_new_name,
                'new_id': new_id
            })

    except Exception as e:
        print(f"ERROR: Rename failed: {e}")
        return jsonify({'status': 'error', 'message': f'Error: {e}'}), 500
