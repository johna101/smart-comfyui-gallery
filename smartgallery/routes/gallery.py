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
from smartgallery.events import publish_event

gallery_bp = Blueprint('gallery', __name__, url_prefix='/galleryout')


def _build_folder_view(folder_key, args):
    """Shared logic for gallery_view (HTML) and api_folder (JSON).
    Returns a dict with all the data needed to render a folder view,
    or None if the folder_key is invalid.
    """
    # Use cached folder config for navigation — only refresh on folder mutations or explicit request
    folders = get_dynamic_folder_config(force_refresh=args.get('force_refresh') == 'true')
    if folder_key not in folders:
        return None

    current_folder_info = folders[folder_key]
    folder_path = current_folder_info['path']

    # 1. Capture All Request Parameters
    is_recursive = args.get('recursive', 'false').lower() == 'true'
    search_scope = args.get('scope', 'local')
    is_global_search = (search_scope == 'global')
    ai_session_id = args.get('ai_session_id')

    # Text filters
    search_term = args.get('search', '').strip()
    wf_files = args.get('workflow_files', '').strip()
    wf_prompt = args.get('workflow_prompt', '').strip()
    start_date = args.get('start_date', '').strip()
    end_date = args.get('end_date', '').strip()
    # Support both repeated params (?extension=png&extension=jpg) and comma-separated (?extensions=png,jpg)
    selected_exts = args.getlist('extension') if hasattr(args, 'getlist') else args.get('extension', [])
    if not selected_exts and args.get('extensions'):
        selected_exts = [e.strip() for e in args.get('extensions', '').split(',') if e.strip()]
    selected_prefixes = args.getlist('prefix') if hasattr(args, 'getlist') else args.get('prefix', [])
    if not selected_prefixes and args.get('prefixes'):
        selected_prefixes = [p.strip() for p in args.get('prefixes', '').split(',') if p.strip()]

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

                    files_list = []
                    for row in rows:
                        d = dict(row)
                        if 'ai_embedding' in d:
                            del d['ai_embedding']
                        files_list.append(d)

                    state.gallery_view_cache = files_list
            except Exception as e:
                print(f"AI Search Error: {e}")
                is_ai_search = False

    # --- PATH B: STANDARD VIEW / SEARCH ---
    if not is_ai_search:
        with get_db_connection() as conn:
            conditions, params = [], []

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

            if args.get('favorites') == 'true': conditions.append("is_favorite = 1")
            if args.get('hide_favorites') == 'true': conditions.append("is_favorite = 0")
            if args.get('no_workflow') == 'true': conditions.append("has_workflow = 0")
            if args.get('no_ai_caption') == 'true':
                conditions.append("(ai_caption IS NULL OR ai_caption = '')")

            if start_date:
                try: conditions.append("mtime >= ?"); params.append(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
                except ValueError: pass
            if end_date:
                try: conditions.append("mtime <= ?"); params.append(datetime.strptime(end_date, '%Y-%m-%d').timestamp() + 86399)
                except ValueError: pass

            if selected_exts:
                e_cond = [f"name LIKE ?" for e in selected_exts if e.strip()]
                params.extend([f"%.{e.lstrip('.').lower()}" for e in selected_exts if e.strip()])
                if e_cond: conditions.append(f"({' OR '.join(e_cond)})")

            if selected_prefixes:
                p_cond = [f"name LIKE ?" for p in selected_prefixes if p.strip()]
                params.extend([f"{p.strip()}_%" for p in selected_prefixes if p.strip()])
                if p_cond: conditions.append(f"({' OR '.join(p_cond)})")

            # --- PATH FILTERING IN SQL (fast) ---
            # Normalize folder path for SQL matching
            target_norm = folder_path.replace('\\', '/')
            if not target_norm.endswith('/'):
                target_norm += '/'

            if not is_global_search:
                if is_recursive:
                    # All files under this folder (any depth)
                    conditions.append("REPLACE(path, '\\', '/') LIKE ?")
                    params.append(target_norm + '%')
                else:
                    # Only direct children — path starts with folder/ but has no further /
                    # Match: folder/filename.png but not folder/sub/filename.png
                    conditions.append("REPLACE(path, '\\', '/') LIKE ?")
                    params.append(target_norm + '%')
                    conditions.append("REPLACE(path, '\\', '/') NOT LIKE ?")
                    params.append(target_norm + '%/%')

            sort_by = 'name' if args.get('sort_by') == 'name' else 'mtime'
            sort_order = "ASC" if args.get('sort_order', 'desc').lower() == 'asc' else "DESC"
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            # Exclude ai_embedding blob from results
            query = f"SELECT id, path, mtime, name, type, duration, dimensions, has_workflow, is_favorite, size, last_scanned, workflow_files, workflow_prompt, ai_last_scanned, ai_caption, ai_error FROM files {where_clause} ORDER BY {sort_by} {sort_order}"
            rows = conn.execute(query, params).fetchall()

            state.gallery_view_cache = [dict(row) for row in rows]

    # 4. Final Metadata
    active_filters_count = 0
    if search_term: active_filters_count += 1
    if wf_files: active_filters_count += 1
    if wf_prompt: active_filters_count += 1
    if start_date: active_filters_count += 1
    if end_date: active_filters_count += 1
    if selected_exts: active_filters_count += 1
    if selected_prefixes: active_filters_count += 1
    if args.get('favorites') == 'true': active_filters_count += 1
    if args.get('hide_favorites') == 'true': active_filters_count += 1
    if args.get('no_workflow') == 'true': active_filters_count += 1
    if ENABLE_AI_SEARCH and args.get('no_ai_caption') == 'true': active_filters_count += 1

    if is_global_search:
        active_filters_count += 1
    elif is_recursive:
        active_filters_count += 1

    total_folder_files, _, _ = scan_folder_and_extract_options(folder_path, recursive=is_recursive)
    total_db_files = 0
    with get_db_connection() as conn_opts:
        try:
            total_db_files = conn_opts.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        except Exception:
            total_db_files = 0

        scope_for_opts = 'global' if is_global_search else 'local'
        extensions, prefixes, pfx_limit = get_filter_options_from_db(conn_opts, scope_for_opts, folder_path, recursive=is_recursive)

    breadcrumbs, ancestor_keys = [], set()
    curr = folder_key
    while curr and curr in folders:
        f_info = folders[curr]
        breadcrumbs.append({'key': curr, 'display_name': f_info['display_name']})
        ancestor_keys.add(curr)
        curr = f_info.get('parent')
    breadcrumbs.reverse()

    return {
        'files': state.gallery_view_cache if args.get('no_pagination') == 'true' else state.gallery_view_cache[:PAGE_SIZE],
        'totalFiles': len(state.gallery_view_cache),
        'totalFolderFiles': total_folder_files,
        'totalDbFiles': total_db_files,
        # Skip folders if client already has them (saves ~500KB per request)
        'folders': None if args.get('skip_folders') == 'true' else folders,
        'currentFolderKey': folder_key,
        'currentFolderInfo': current_folder_info,
        'breadcrumbs': breadcrumbs,
        'ancestorKeys': list(ancestor_keys),
        'availableExtensions': extensions,
        'availablePrefixes': prefixes,
        'prefixLimitReached': pfx_limit,
        'selectedExtensions': selected_exts,
        'selectedPrefixes': selected_prefixes,
        'protectedFolderKeys': list(PROTECTED_FOLDER_KEYS),
        'showFavorites': args.get('favorites', 'false').lower() == 'true',
        'hideFavorites': args.get('hide_favorites', 'false').lower() == 'true',
        'enableAiSearch': ENABLE_AI_SEARCH,
        'isAiSearch': is_ai_search,
        'aiQuery': ai_query_text,
        'isGlobalSearch': is_global_search,
        'activeFiltersCount': active_filters_count,
        'currentScope': search_scope,
        'isRecursive': is_recursive,
        'appVersion': APP_VERSION,
        'ffmpegAvailable': state.FFPROBE_EXECUTABLE_PATH is not None,
        'streamThreshold': STREAM_THRESHOLD_BYTES,
    }


@gallery_bp.route('/')
def gallery_redirect_base():
    return redirect(url_for('gallery.gallery_view', folder_key='_root_'))


@gallery_bp.route('/view/<string:folder_key>')
def gallery_view(folder_key):
    data = _build_folder_view(folder_key, request.args)
    if data is None:
        return redirect(url_for('gallery.gallery_view', folder_key='_root_'))

    return render_template('index.html',
                           files=data['files'],
                           total_files=data['totalFiles'],
                           total_folder_files=data['totalFolderFiles'],
                           total_db_files=data['totalDbFiles'],
                           folders=data['folders'],
                           current_folder_key=data['currentFolderKey'],
                           current_folder_info=data['currentFolderInfo'],
                           breadcrumbs=data['breadcrumbs'],
                           ancestor_keys=data['ancestorKeys'],
                           available_extensions=data['availableExtensions'],
                           available_prefixes=data['availablePrefixes'],
                           prefix_limit_reached=data['prefixLimitReached'],
                           selected_extensions=data['selectedExtensions'],
                           selected_prefixes=data['selectedPrefixes'],
                           protected_folder_keys=data['protectedFolderKeys'],
                           show_favorites=data['showFavorites'],
                           enable_ai_search=data['enableAiSearch'],
                           is_ai_search=data['isAiSearch'],
                           ai_query=data['aiQuery'],
                           is_global_search=data['isGlobalSearch'],
                           active_filters_count=data['activeFiltersCount'],
                           current_scope=data['currentScope'],
                           is_recursive=data['isRecursive'],
                           app_version=data['appVersion'],
                           github_url=GITHUB_REPO_URL,
                           update_available=state.UPDATE_AVAILABLE,
                           remote_version=state.REMOTE_VERSION,
                           ffmpeg_available=data['ffmpegAvailable'],
                           stream_threshold=data['streamThreshold'])


@gallery_bp.route('/api/folder/<string:folder_key>')
def api_folder(folder_key):
    """JSON API for SPA-like folder navigation. Returns same data as gallery_view."""
    data = _build_folder_view(folder_key, request.args)
    if data is None:
        return jsonify({'error': 'Folder not found'}), 404
    return jsonify(data)


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
    if success_count > 0:
        sync_folder_on_demand(destination_path)
        publish_event("files_uploaded", {"folder_key": folder_key, "count": success_count})
    if errors: return jsonify({'status': 'partial_success', 'message': f'Successfully uploaded {success_count} files. The following files failed: {", ".join(errors.keys())}'}), 207
    return jsonify({'status': 'success', 'message': f'Successfully uploaded {success_count} files.'})
