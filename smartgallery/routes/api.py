# Smart Gallery for ComfyUI - API Routes
# Sync status, search options, and file comparison endpoints.

import json
from flask import Blueprint, request, jsonify, abort, Response

from smartgallery.config import BASE_OUTPUT_PATH
from smartgallery.models import get_db_connection
from smartgallery.processing import extract_workflow
from smartgallery.utils import generate_node_summary
from smartgallery.folders import (
    get_dynamic_folder_config, sync_folder_on_demand, get_filter_options_from_db
)
from smartgallery.routes.files import get_file_info_from_db

api_bp = Blueprint('api', __name__, url_prefix='/galleryout')


@api_bp.route('/sync_status/<string:folder_key>')
def sync_status(folder_key):
    folders = get_dynamic_folder_config()
    if folder_key not in folders:
        abort(404)
    folder_path = folders[folder_key]['path']
    return Response(sync_folder_on_demand(folder_path), mimetype='text/event-stream')


@api_bp.route('/api/search_options')
def api_search_options():
    scope = request.args.get('scope', 'local')
    folder_key = request.args.get('folder_key', '_root_')
    is_rec = request.args.get('recursive', 'false').lower() == 'true' # Added

    folders = get_dynamic_folder_config()
    folder_path = folders.get(folder_key, {}).get('path', BASE_OUTPUT_PATH)

    with get_db_connection() as conn:
        # Now passing the recursive flag to the options extractor
        exts, pfxs, limit_reached = get_filter_options_from_db(conn, scope, folder_path, recursive=is_rec)

    return jsonify({'extensions': exts, 'prefixes': pfxs, 'prefix_limit_reached': limit_reached})


@api_bp.route('/api/compare_files', methods=['POST'])
def compare_files_api():
    data = request.json
    id_a = data.get('id_a')
    id_b = data.get('id_b')

    if not id_a or not id_b:
        return jsonify({'status': 'error', 'message': 'Missing file IDs'}), 400

    def get_flat_params(file_id):
        try:
            info = get_file_info_from_db(file_id)
            wf_json = extract_workflow(info['path'])
            if not wf_json: return {}

            # Reuse existing summary logic
            summary = generate_node_summary(wf_json)
            if not summary: return {}

            flat_params = {}
            for node in summary:
                node_type = node['type']
                for p in node['params']:
                    # Create a readable key like "KSampler > steps"
                    key = f"{node_type} > {p['name']}"
                    flat_params[key] = str(p['value'])
            return flat_params
        except:
            return {}

    try:
        params_a = get_flat_params(id_a)
        params_b = get_flat_params(id_b)

        # Identify all unique keys
        all_keys = sorted(list(set(params_a.keys()) | set(params_b.keys())))

        diff_table = []
        for key in all_keys:
            val_a = params_a.get(key, 'N/A')
            val_b = params_b.get(key, 'N/A')

            # Check difference (case insensitive)
            is_diff = str(val_a).lower() != str(val_b).lower()

            diff_table.append({
                'key': key,
                'val_a': val_a,
                'val_b': val_b,
                'is_diff': is_diff
            })

        # Sort: Differences at the top, then alphabetical
        diff_table.sort(key=lambda x: (not x['is_diff'], x['key']))

        return jsonify({'status': 'success', 'diff': diff_table})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
