# Smart Gallery for ComfyUI - AI Search & Indexing Routes
# AI queue, status checking, indexing management, and watched folders.

import os
import json
import time
import uuid
import threading
from flask import Blueprint, request, jsonify

from smartgallery.config import BASE_OUTPUT_PATH, ENABLE_AI_SEARCH
from smartgallery.models import get_db_connection
from smartgallery.utils import get_standardized_path
from smartgallery.folders import get_dynamic_folder_config

ai_bp = Blueprint('ai', __name__, url_prefix='/galleryout')


# AI QUEUE SUBMISSION ROUTE
@ai_bp.route('/ai_queue', methods=['POST'])
def ai_queue_search():
    """
    Receives a search query from the frontend and adds it to the DB queue.
    Also performs basic housekeeping (cleaning old requests).
    """
    data = request.json
    query = data.get('query', '').strip()
    # FIX: Leggi il limite dal JSON (default 100 se non presente)
    limit = int(data.get('limit', 100))

    if not query:
        return jsonify({'status': 'error', 'message': 'Query cannot be empty'}), 400

    session_id = str(uuid.uuid4())

    try:
        with get_db_connection() as conn:
            # 1. Housekeeping
            conn.execute("DELETE FROM ai_search_queue WHERE created_at < datetime('now', '-1 hour')")
            conn.execute("DELETE FROM ai_search_results WHERE session_id NOT IN (SELECT session_id FROM ai_search_queue)")

            # 2. Insert new request WITH LIMIT
            conn.execute('''
                INSERT INTO ai_search_queue (session_id, query, limit_results, status)
                VALUES (?, ?, ?, 'pending')
            ''', (session_id, query, limit))
            conn.commit()

        return jsonify({'status': 'queued', 'session_id': session_id})
    except Exception as e:
        print(f"AI Queue Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


# AI STATUS CHECK ROUTE (POLLING)
@ai_bp.route('/ai_check/<session_id>', methods=['GET'])
def ai_check_status(session_id):
    """Checks the status of a specific search session."""
    with get_db_connection() as conn:
        row = conn.execute("SELECT status FROM ai_search_queue WHERE session_id = ?", (session_id,)).fetchone()

        if not row:
            return jsonify({'status': 'not_found'})

        return jsonify({'status': row['status']})


# --- AI MANAGER API ROUTES ---
@ai_bp.route('/ai_indexing/reset', methods=['POST'])
def ai_indexing_reset():
    """
    Resets AI metadata (caption, embedding, timestamp) for specific files or a whole folder.
    CRITICAL: Also removes these files from the indexing queue to prevent re-processing.
    """
    if not ENABLE_AI_SEARCH: return jsonify({'status':'error'})
    data = request.json

    # Mode 1: Batch IDs
    file_ids = data.get('file_ids', [])

    # Mode 2: Folder Path
    folder_key = data.get('folder_key')
    recursive = data.get('recursive', False)

    count = 0

    try:
        with get_db_connection() as conn:
            ids_to_wipe = []

            # Case A: Specific File IDs (Selection or Lightbox)
            if file_ids:
                ids_to_wipe = file_ids

            # Case B: Folder (Recursive or Flat)
            elif folder_key:
                folders = get_dynamic_folder_config()
                if folder_key in folders:
                    folder_path = folders[folder_key]['path']
                    # Normalize for robust DB lookup
                    target_norm = os.path.normpath(folder_path).replace('\\', '/').lower()
                    if not target_norm.endswith('/'): target_norm += '/'

                    # Fetch candidates to wipe
                    cursor = conn.execute("SELECT id, path FROM files WHERE ai_caption IS NOT NULL OR ai_embedding IS NOT NULL")
                    for row in cursor:
                        f_path = row['path']
                        # Normalize DB path
                        f_path_norm = os.path.normpath(f_path).replace('\\', '/').lower()

                        is_match = False
                        if recursive:
                            if f_path_norm.startswith(target_norm): is_match = True
                        else:
                            # Strict parent check
                            parent_norm = os.path.dirname(f_path_norm).replace('\\', '/').lower() + '/'
                            if parent_norm == target_norm: is_match = True

                        if is_match:
                            ids_to_wipe.append(row['id'])

            if ids_to_wipe:
                # Process in chunks to avoid SQL limits
                chunk_size = 500
                for i in range(0, len(ids_to_wipe), chunk_size):
                    chunk = ids_to_wipe[i:i + chunk_size]
                    placeholders = ','.join(['?'] * len(chunk))

                    # 1. WIPE METADATA (Instant)
                    conn.execute(f"""
                        UPDATE files
                        SET ai_caption=NULL, ai_embedding=NULL, ai_last_scanned=0, ai_error=NULL
                        WHERE id IN ({placeholders})
                    """, chunk)

                    # 2. REMOVE FROM PROCESSING QUEUE (Critical fix)
                    conn.execute(f"""
                        DELETE FROM ai_indexing_queue
                        WHERE file_id IN ({placeholders})
                    """, chunk)

                count = len(ids_to_wipe)
                conn.commit()

        return jsonify({'status': 'success', 'count': count, 'message': f'AI data erased and queue cleared for {count} files.'})

    except Exception as e:
        print(f"AI Reset Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@ai_bp.route('/ai_indexing/add_files', methods=['POST'])
def ai_indexing_add_files():
    if not ENABLE_AI_SEARCH: return jsonify({'status':'error'})
    data = request.json
    file_ids = data.get('file_ids', [])
    force_index = data.get('force', False)
    params = json.dumps({'beams': data.get('beams', 3), 'precision': data.get('precision', 'fp16')})

    count = 0
    skipped = 0

    with get_db_connection() as conn:
        # --- NEW: WIPE DATA IF FORCED ---
        if force_index and file_ids:
            placeholders = ','.join(['?'] * len(file_ids))
            conn.execute(f"""
                UPDATE files
                SET ai_caption=NULL, ai_embedding=NULL, ai_last_scanned=0, ai_error=NULL
                WHERE id IN ({placeholders})
            """, file_ids)

        for fid in file_ids:
            # Check current status
            row = conn.execute("SELECT path, ai_last_scanned FROM files WHERE id=?", (fid,)).fetchone()
            if row:
                # --- INCREMENTAL LOGIC ---
                has_ai_data = row['ai_last_scanned'] and row['ai_last_scanned'] > 0

                if not force_index and has_ai_data:
                    skipped += 1
                    continue

                p_key = get_standardized_path(row['path'])
                # FIX: Use "ON CONFLICT DO UPDATE" to reset status to 'pending'
                conn.execute("""
                    INSERT INTO ai_indexing_queue (file_path, file_id, status, created_at, force_index, params)
                    VALUES (?, ?, 'pending', ?, ?, ?)
                    ON CONFLICT(file_path) DO UPDATE SET
                        status = 'pending',
                        force_index = excluded.force_index,
                        created_at = excluded.created_at,
                        params = excluded.params
                """, (p_key, fid, time.time(), 1 if force_index else 0, params))
                count += 1
        conn.commit()

    # --- FEEDBACK MESSAGES ---
    if count == 0 and skipped > 0:
        return jsonify({
            'status': 'warning',
            'message': "All selected files are already indexed. Enable 'Force Re-Index' to overwrite.",
            'count': 0
        })

    msg = f"Queued {count} files."
    if skipped > 0:
        msg += f" (Skipped {skipped} already indexed)"

    return jsonify({'status': 'success', 'count': count, 'message': msg})


@ai_bp.route('/ai_indexing/add_folder', methods=['POST'])
def ai_indexing_add_folder():
    if not ENABLE_AI_SEARCH: return jsonify({'status':'error'})
    data = request.json

    folder_key = data.get('folder_key')
    recursive = data.get('recursive', False)
    watch = data.get('watch', False)
    force = data.get('force', False)

    folders = get_dynamic_folder_config()
    if folder_key not in folders:
        return jsonify({'status':'error', 'message':'Folder not found'}), 404

    raw_path = folders[folder_key]['path']
    std_path = get_standardized_path(raw_path)

    params = json.dumps({'beams': data.get('beams', 3), 'precision': data.get('precision', 'fp16')})
    msg = "Indexing queued."

    # 1. HANDLE WATCH LIST UPDATE
    with get_db_connection() as conn:
        if watch:
            existing = conn.execute("SELECT path, recursive FROM ai_watched_folders").fetchall()
            should_add = True
            for row in existing:
                exist_std = get_standardized_path(row['path'])
                if exist_std == std_path:
                    # Update recursion if needed
                    if recursive and not row['recursive']:
                        conn.execute("UPDATE ai_watched_folders SET recursive=1 WHERE path=?", (row['path'],))
                    should_add = False
                    break
                if std_path.startswith(exist_std + '/') and row['recursive']:
                    should_add = False
                    msg = "Covered by parent watcher."
                    break
            if should_add:
                conn.execute("INSERT OR REPLACE INTO ai_watched_folders (path, recursive, added_at) VALUES (?, ?, ?)", (raw_path, 1 if recursive else 0, time.time()))
                msg = "Folder added to Watch List & Queued."
        conn.commit()

    # --- CRITICAL FIX: REFRESH SERVER CACHE IMMEDIATELY ---
    if watch:
        get_dynamic_folder_config(force_refresh=True)

    # 2. BACKGROUND SCAN & QUEUE
    def _scan():
        valid = {'.png','.jpg','.jpeg','.webp','.gif','.mp4','.mov','.avi','.webm'}
        exc = {'.thumbnails_cache', '.sqlite_cache', '.zip_downloads', '.AImodels', 'venv', '.git'}
        files_found = []
        try:
            if recursive:
                for r, d, f in os.walk(raw_path, topdown=True, followlinks=False):
                    d[:] = [x for x in d if not x.startswith('.') and x not in exc]
                    for x in f:
                        if not x.startswith('._') and os.path.splitext(x)[1].lower() in valid: files_found.append(os.path.join(r, x))
            else:
                for entry in os.scandir(raw_path):
                    if entry.is_file() and not entry.name.startswith('._') and os.path.splitext(entry.name)[1].lower() in valid: files_found.append(entry.path)
        except OSError: return

        # Optimize: Batch Operations
        with get_db_connection() as conn:

            ids_to_wipe = []
            queue_entries = []

            for fp in files_found:
                pk = get_standardized_path(fp)

                # --- ROBUST LOOKUP START ---
                # 1. Try exact match
                row = conn.execute("SELECT id, mtime, ai_last_scanned FROM files WHERE path=?", (fp,)).fetchone()

                # 2. Try standardized match (case insensitive on Windows)
                if not row:
                    row = conn.execute("SELECT id, mtime, ai_last_scanned FROM files WHERE path=?", (pk,)).fetchone()

                # 3. Try Normalized Slash match
                if not row:
                    norm_p = fp.replace('\\', '/')
                    row = conn.execute("SELECT id, mtime, ai_last_scanned FROM files WHERE REPLACE(path, '\\', '/') = ?", (norm_p,)).fetchone()
                # --- ROBUST LOOKUP END ---

                should_queue = False
                fid = None

                if row:
                    fid = row['id']
                    if force:
                        ids_to_wipe.append(fid)
                        should_queue = True
                    elif (row['ai_last_scanned'] or 0) < row['mtime']:
                        should_queue = True # Needs update (Incremental logic)
                else:
                    # New file not in DB yet - queue it, worker will retry later
                    should_queue = True

                if should_queue:
                    queue_entries.append((pk, fid, time.time(), 1 if force else 0, params))

            # 3. WIPE OLD DATA IF FORCED
            if ids_to_wipe:
                chunk_size = 500
                for i in range(0, len(ids_to_wipe), chunk_size):
                    chunk = ids_to_wipe[i:i + chunk_size]
                    placeholders = ','.join(['?'] * len(chunk))
                    conn.execute(f"""
                        UPDATE files
                        SET ai_caption=NULL, ai_embedding=NULL, ai_last_scanned=0, ai_error=NULL
                        WHERE id IN ({placeholders})
                    """, chunk)

            # 4. BATCH INSERT INTO QUEUE (UPSERT)
            if queue_entries:
                conn.executemany("""
                    INSERT INTO ai_indexing_queue (file_path, file_id, status, created_at, force_index, params)
                    VALUES (?, ?, 'pending', ?, ?, ?)
                    ON CONFLICT(file_path) DO UPDATE SET
                        status = 'pending',
                        force_index = excluded.force_index,
                        created_at = excluded.created_at,
                        params = excluded.params
                """, queue_entries)

            conn.commit()

    threading.Thread(target=_scan, daemon=True).start()
    return jsonify({'status': 'success', 'message': msg})


@ai_bp.route('/ai_indexing/watched', methods=['GET', 'DELETE'])
def ai_watched_folders():
    if not ENABLE_AI_SEARCH: return jsonify({})
    with get_db_connection() as conn:
        if request.method == 'DELETE':
            path = request.json.get('folder_path')
            if not path:
                key = request.json.get('folder_key')
                folders = get_dynamic_folder_config()
                if key in folders: path = folders[key]['path']

            if path:
                # 1. Stop Watching
                conn.execute("DELETE FROM ai_watched_folders WHERE path=?", (path,))

                # 2. CLEAR QUEUE (Critical Fix)
                std_path = get_standardized_path(path)
                conn.execute("DELETE FROM ai_indexing_queue WHERE file_path = ? OR file_path LIKE ?", (std_path, std_path + '/%'))

                # 3. WIPE DATA (Optional User Choice)
                if request.json.get('reset_data'):
                    std_target = get_standardized_path(path)
                    rows = conn.execute("SELECT id, path FROM files WHERE ai_caption IS NOT NULL OR ai_embedding IS NOT NULL").fetchall()
                    ids_to_wipe = []
                    for r in rows:
                        p_std = get_standardized_path(r['path'])
                        if p_std == std_target or p_std.startswith(std_target + '/'):
                            ids_to_wipe.append(r['id'])

                    if ids_to_wipe:
                        chunk_size = 500
                        for i in range(0, len(ids_to_wipe), chunk_size):
                            chunk = ids_to_wipe[i:i+chunk_size]
                            ph = ','.join(['?'] * len(chunk))
                            conn.execute(f"UPDATE files SET ai_caption=NULL, ai_embedding=NULL, ai_last_scanned=0, ai_error=NULL WHERE id IN ({ph})", chunk)
                            conn.execute(f"DELETE FROM ai_indexing_queue WHERE file_id IN ({ph})", chunk)

                conn.commit()
                # --- FORCE CONFIG REFRESH TO UPDATE UI COLORS IMMEDIATELY ---
                get_dynamic_folder_config(force_refresh=True)

                return jsonify({'status': 'success'})
            return jsonify({'status': 'error'})

        rows = conn.execute("SELECT path, recursive FROM ai_watched_folders").fetchall()
        folders = get_dynamic_folder_config()
        pmap = {info['path']: {'key': k, 'name': info['display_name']} for k, info in folders.items()}
        res = []
        for r in rows:
            m = pmap.get(r['path'])
            rel = r['path']
            try: rel = os.path.relpath(r['path'], BASE_OUTPUT_PATH)
            except ValueError: pass
            if m: res.append({'path': r['path'], 'rel_path': rel, 'key': m['key'], 'display_name': m['name'], 'recursive': bool(r['recursive'])})
            else: res.append({'path': r['path'], 'rel_path': rel, 'key': '_unknown', 'display_name': os.path.basename(r['path']), 'recursive': bool(r['recursive'])})
        return jsonify({'folders': res})


@ai_bp.route('/ai_indexing/status')
def ai_indexing_status():
    if not ENABLE_AI_SEARCH: return jsonify({})
    try:
        with get_db_connection() as conn:
            pending = conn.execute("SELECT COUNT(*) FROM ai_indexing_queue WHERE status='pending'").fetchone()[0]
            processing = conn.execute("SELECT file_path FROM ai_indexing_queue WHERE status='processing'").fetchone()

            # Preview Next 10 files with PRIORITY INFO
            next_rows = conn.execute("SELECT file_path, force_index FROM ai_indexing_queue WHERE status='pending' ORDER BY force_index DESC, created_at ASC LIMIT 10").fetchall()

            avg = conn.execute("SELECT value FROM ai_metadata WHERE key='avg_processing_time'").fetchone()
            paused = conn.execute("SELECT value FROM ai_metadata WHERE key='indexing_paused'").fetchone()
            waiting = conn.execute("SELECT COUNT(*) FROM ai_indexing_queue WHERE status='waiting_gpu'").fetchone()[0]

            status = "Idle"
            if paused and paused['value'] == '1': status = "Paused"
            elif waiting > 0: status = "waiting_gpu"
            elif processing: status = "Indexing"
            elif pending > 0: status = "Queued"

            curr_file = ""
            if processing:
                try: curr_file = os.path.relpath(processing['file_path'], BASE_OUTPUT_PATH)
                except ValueError: curr_file = os.path.basename(processing['file_path'])

            next_files = []
            for r in next_rows:
                try: p = os.path.relpath(r['file_path'], BASE_OUTPUT_PATH)
                except ValueError: p = os.path.basename(r['file_path'])

                next_files.append({
                    'path': p,
                    'is_priority': bool(r['force_index'])
                })

            return jsonify({
                'global_status': status, 'pending_count': pending, 'current_file': curr_file,
                'gpu_usage': 0, 'avg_time': float(avg['value']) if avg else 0.0,
                'current_job_progress': 0, 'current_job_total': pending + (1 if processing else 0),
                'next_files': next_files
            })
    except Exception as e: return jsonify({'error': str(e)}), 500


@ai_bp.route('/ai_indexing/control', methods=['POST'])
def ai_indexing_control():
    if not ENABLE_AI_SEARCH: return jsonify({'status':'error'})
    action = request.json.get('action')
    with get_db_connection() as conn:
        if action == 'pause': conn.execute("INSERT OR REPLACE INTO ai_metadata (key, value) VALUES ('indexing_paused', '1')")
        elif action == 'resume':
            conn.execute("INSERT OR REPLACE INTO ai_metadata (key, value) VALUES ('indexing_paused', '0')")
            conn.execute("UPDATE ai_indexing_queue SET status='pending' WHERE status='waiting_gpu'")
        elif action == 'clear': conn.execute("DELETE FROM ai_indexing_queue WHERE status != 'processing'")
        conn.commit()
    return jsonify({'status': 'success', 'message': f'Queue {action}d'})
