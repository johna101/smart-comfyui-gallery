# Smart Gallery for ComfyUI - Gallery Routes
# Main gallery view, load_more, upload, and redirect routes.

import os
from datetime import datetime
from flask import Blueprint, redirect, url_for, request, jsonify, render_template
from werkzeug.utils import secure_filename

from smartgallery.config import (
    BASE_OUTPUT_PATH, PAGE_SIZE, ENABLE_AI_SEARCH, PROTECTED_FOLDER_KEYS,
    APP_VERSION, GITHUB_REPO_URL, STREAM_THRESHOLD_BYTES
)
from smartgallery import state
from smartgallery.models import get_db_connection
from smartgallery.utils import normalize_smart_path
from smartgallery.folders import (
    get_dynamic_folder_config, sync_folder_on_demand,
    scan_folder_and_extract_options, get_filter_options_from_db
)

gallery_bp = Blueprint('gallery', __name__, url_prefix='/galleryout')


@gallery_bp.route('/')
def gallery_redirect_base():
    return redirect(url_for('gallery.gallery_view', folder_key='_root_'))


@gallery_bp.route('/view/<string:folder_key>')
def gallery_view(folder_key):
    folders = get_dynamic_folder_config(force_refresh=True)
    if folder_key not in folders:
        return redirect(url_for('gallery.gallery_view', folder_key='_root_'))

    current_folder_info = folders[folder_key]
    folder_path = current_folder_info['path']

    # 1. Capture All Request Parameters
    is_recursive = request.args.get('recursive', 'false').lower() == 'true'
    search_scope = request.args.get('scope', 'local')
    is_global_search = (search_scope == 'global')
    ai_session_id = request.args.get('ai_session_id')

    # Text filters
    search_term = request.args.get('search', '').strip()
    wf_files = request.args.get('workflow_files', '').strip()
    wf_prompt = request.args.get('workflow_prompt', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    selected_exts = request.args.getlist('extension')
    selected_prefixes = request.args.getlist('prefix')

    is_ai_search = False
    ai_query_text = ""

    # --- PATH A: AI SEARCH RESULTS ---
    if ENABLE_AI_SEARCH and ai_session_id:
        with get_db_connection() as conn:
            try:
                queue_info = conn.execute("SELECT query, status FROM ai_search_queue WHERE session_id = ?", (ai_session_id,)).fetchone()
                if queue_info and queue_info['status'] == 'completed':
                    is_ai_search = True
                    ai_query_text = queue_info['query']
                    rows = conn.execute('''
                        SELECT f.*, r.score FROM ai_search_results r
                        JOIN files f ON r.file_id = f.id
                        WHERE r.session_id = ? ORDER BY r.score DESC
                    ''', (ai_session_id,)).fetchall()

                    # FIX: Clean up BLOB data (ai_embedding) which is not JSON serializable
                    files_list = []
                    for row in rows:
                        d = dict(row)
                        if 'ai_embedding' in d:
                            del d['ai_embedding'] # Remove binary data
                        files_list.append(d)

                    state.gallery_view_cache = files_list
            except Exception as e:
                print(f"AI Search Error: {e}")
                is_ai_search = False

    # --- PATH B: STANDARD VIEW / SEARCH (Cross-Platform Robust) ---
    if not is_ai_search:
        with get_db_connection() as conn:
            conditions, params = [], []

            # 2. Apply Metadata Filters first (Generic fields)
            if search_term:
                conditions.append("name LIKE ?")
                params.append(f"%{search_term}%")

            if wf_files:
                for kw in [k.strip() for k in wf_files.split(',') if k.strip()]:
                    conditions.append("workflow_files LIKE ?")
                    params.append(f"%{normalize_smart_path(kw)}%")

            if wf_prompt:
                for kw in [k.strip() for k in wf_prompt.split(',') if k.strip()]:
                    conditions.append("workflow_prompt LIKE ?")
                    params.append(f"%{kw}%")

            if request.args.get('favorites') == 'true': conditions.append("is_favorite = 1")
            if request.args.get('hide_favorites') == 'true': conditions.append("is_favorite = 0")
            if request.args.get('no_workflow') == 'true': conditions.append("has_workflow = 0")
            if request.args.get('no_ai_caption') == 'true':
                conditions.append("(ai_caption IS NULL OR ai_caption = '')")

            if start_date:
                try: conditions.append("mtime >= ?"); params.append(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
                except: pass
            if end_date:
                try: conditions.append("mtime <= ?"); params.append(datetime.strptime(end_date, '%Y-%m-%d').timestamp() + 86399)
                except: pass

            if selected_exts:
                e_cond = [f"name LIKE ?" for e in selected_exts if e.strip()]
                params.extend([f"%.{e.lstrip('.').lower()}" for e in selected_exts if e.strip()])
                if e_cond: conditions.append(f"({' OR '.join(e_cond)})")

            if selected_prefixes:
                p_cond = [f"name LIKE ?" for p in selected_prefixes if p.strip()]
                params.extend([f"{p.strip()}_%" for p in selected_prefixes if p.strip()])
                if p_cond: conditions.append(f"({' OR '.join(p_cond)})")

            # 3. Execution: We fetch files matching metadata, then filter paths in Python
            # This is the only way to guarantee 100% slash-agnostic behavior
            sort_by = 'name' if request.args.get('sort_by') == 'name' else 'mtime'
            sort_order = "ASC" if request.args.get('sort_order', 'desc').lower() == 'asc' else "DESC"
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            query = f"SELECT * FROM files {where_clause} ORDER BY {sort_by} {sort_order}"
            rows = conn.execute(query, params).fetchall()

            # --- ULTRA-ROBUST MIXED-PATH FILTERING ---
            final_files = []

            # Helper to normalize ANY path (mixed slashes, case, trailing)
            def safe_path_norm(p):
                if not p: return ""
                # 1. Force all backslashes to forward slashes immediately
                # 2. Lowercase for cross-platform case-insensitivity
                # 3. Clean up and remove trailing slashes
                return os.path.normpath(str(p).replace('\\', '/')).replace('\\', '/').lower().rstrip('/')

            target_norm = safe_path_norm(folder_path)

            for row in rows:
                f_data = dict(row)
                if 'ai_embedding' in f_data: del f_data['ai_embedding']

                # Normalize the DB path which might be mixed (e.g., c:/folder\img.png)
                f_path_norm = safe_path_norm(f_data['path'])
                f_dir_norm = safe_path_norm(os.path.dirname(f_path_norm))

                if is_global_search:
                    final_files.append(f_data)
                elif is_recursive:
                    # Check if the file is inside the target folder tree
                    # Adding a '/' ensures we don't match 'folder_backup' when looking for 'folder'
                    if f_path_norm.startswith(target_norm + '/'):
                        final_files.append(f_data)
                else:
                    # Strict match: must be exactly in the target folder
                    if f_dir_norm == target_norm:
                        final_files.append(f_data)

            state.gallery_view_cache = final_files

    # 4. Final Metadata for Template
    # --- RIGOROUS FILTER COUNTING LOGIC ---
    active_filters_count = 0
    if search_term: active_filters_count += 1
    if wf_files: active_filters_count += 1
    if wf_prompt: active_filters_count += 1
    if start_date: active_filters_count += 1
    if end_date: active_filters_count += 1
    if selected_exts: active_filters_count += 1
    if selected_prefixes: active_filters_count += 1
    if request.args.get('favorites') == 'true': active_filters_count += 1
    if request.args.get('hide_favorites') == 'true': active_filters_count += 1
    if request.args.get('no_workflow') == 'true': active_filters_count += 1
    if ENABLE_AI_SEARCH and request.args.get('no_ai_caption') == 'true': active_filters_count += 1

    # Scope/Recursive Logic:
    if is_global_search:
        # Global search is a major state change, counts as 1 filter
        active_filters_count += 1
    elif is_recursive:
        # Recursive only counts as a filter if we are in Local mode (modifying the default folder view)
        active_filters_count += 1

    # Important: count files correctly on disk for the badge
    total_folder_files, _, _ = scan_folder_and_extract_options(folder_path, recursive=is_recursive)
    # Initialize DB Total
    total_db_files = 0
    with get_db_connection() as conn_opts:
        # NEW: Get the grand total of files in the database (for Global/AI context)
        try:
            total_db_files = conn_opts.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        except:
            total_db_files = 0

        scope_for_opts = 'global' if is_global_search else 'local'
        # FIX: Added recursive=is_recursive to ensure dropdowns match current view on load
        extensions, prefixes, pfx_limit = get_filter_options_from_db(conn_opts, scope_for_opts, folder_path, recursive=is_recursive)

    breadcrumbs, ancestor_keys = [], set()
    curr = folder_key
    while curr and curr in folders:
        f_info = folders[curr]
        breadcrumbs.append({'key': curr, 'display_name': f_info['display_name']})
        ancestor_keys.add(curr)
        curr = f_info.get('parent')
    breadcrumbs.reverse()
    return render_template('index.html',
                           files=state.gallery_view_cache[:PAGE_SIZE],
                           total_files=len(state.gallery_view_cache),
                           total_folder_files=total_folder_files,
                           total_db_files=total_db_files,
                           folders=folders,
                           current_folder_key=folder_key,
                           current_folder_info=current_folder_info,
                           breadcrumbs=breadcrumbs,
                           ancestor_keys=list(ancestor_keys),
                           available_extensions=extensions,
                           available_prefixes=prefixes,
                           prefix_limit_reached=pfx_limit,
                           selected_extensions=selected_exts,
                           selected_prefixes=selected_prefixes,
                           protected_folder_keys=list(PROTECTED_FOLDER_KEYS),
                           show_favorites=request.args.get('favorites', 'false').lower() == 'true',
                           enable_ai_search=ENABLE_AI_SEARCH,
                           is_ai_search=is_ai_search,
                           ai_query=ai_query_text,
                           is_global_search=is_global_search,
                           active_filters_count=active_filters_count,
                           current_scope=search_scope,
                           is_recursive=is_recursive,
                           app_version=APP_VERSION,
                           github_url=GITHUB_REPO_URL,
                           update_available=state.UPDATE_AVAILABLE,
                           remote_version=state.REMOTE_VERSION,
                           ffmpeg_available=(state.FFPROBE_EXECUTABLE_PATH is not None),
                           stream_threshold=STREAM_THRESHOLD_BYTES)


@gallery_bp.route('/load_more')
def load_more():
    offset = request.args.get('offset', 0, type=int)
    if offset >= len(state.gallery_view_cache): return jsonify(files=[])
    return jsonify(files=state.gallery_view_cache[offset:offset + PAGE_SIZE])


@gallery_bp.route('/upload', methods=['POST'])
def upload_files():
    folder_key = request.form.get('folder_key')
    if not folder_key: return jsonify({'status': 'error', 'message': 'No destination folder provided.'}), 400
    folders = get_dynamic_folder_config()
    if folder_key not in folders: return jsonify({'status': 'error', 'message': 'Destination folder not found.'}), 404
    destination_path = folders[folder_key]['path']
    if 'files' not in request.files: return jsonify({'status': 'error', 'message': 'No files were uploaded.'}), 400
    uploaded_files, errors, success_count = request.files.getlist('files'), {}, 0
    for file in uploaded_files:
        if file and file.filename:
            filename = secure_filename(file.filename)
            try:
                file.save(os.path.join(destination_path, filename))
                success_count += 1
            except Exception as e: errors[filename] = str(e)
    if success_count > 0: sync_folder_on_demand(destination_path)
    if errors: return jsonify({'status': 'partial_success', 'message': f'Successfully uploaded {success_count} files. The following files failed: {", ".join(errors.keys())}'}), 207
    return jsonify({'status': 'success', 'message': f'Successfully uploaded {success_count} files.'})
