# Smart Gallery for ComfyUI - Batch Operations Routes
# Rescan folders and batch zip download functionality.

import os
import time
import uuid
import zipfile
import threading
import concurrent.futures
from flask import Blueprint, request, jsonify, url_for, send_from_directory

from smartgallery.config import MAX_PARALLEL_WORKERS, ZIP_CACHE_DIR
from smartgallery import state
from smartgallery.models import get_db_connection
from smartgallery.processing import process_single_file
from smartgallery.folders import get_dynamic_folder_config
from smartgallery.events import publish_event
from smartgallery.queries import FILES_UPSERT, FILES_SELECT_PATH_NAME_BATCH, FILES_SELECT_PATH_LASTSCAN_FOLDER

batch_bp = Blueprint('batch', __name__, url_prefix='/galleryout')


def background_rescan_worker(job_id, files_to_process):
    """
    Background worker that updates a global job status so the UI can poll for progress.
    """
    if not files_to_process:
        state.rescan_jobs[job_id]['status'] = 'done'
        return

    print(f"INFO: [Background] Job {job_id}: Rescanning {len(files_to_process)} files...")

    try:
        total = len(files_to_process)
        state.rescan_jobs[job_id]['total'] = total

        with get_db_connection() as conn:
            processed_count = 0
            results = []

            with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
                futures = {executor.submit(process_single_file, path): path for path in files_to_process}

                for future in concurrent.futures.as_completed(futures):
                    try:
                        result = future.result()
                        if result:
                            results.append(result)

                        processed_count += 1
                        # UPDATE PROGRESS
                        state.rescan_jobs[job_id]['current'] = processed_count

                    except Exception as e:
                        print(f"ERROR: Worker failed for a file: {e}")

            if results:
                conn.executemany(FILES_UPSERT, results)
                conn.commit()

        print(f"INFO: [Background] Job {job_id} finished.")
        state.rescan_jobs[job_id]['status'] = 'done'
        publish_event("rescan_completed", {
            "folder_key": state.rescan_jobs[job_id].get('folder_key'),
            "job_id": job_id,
        }, source="system")

    except Exception as e:
        print(f"CRITICAL ERROR in Background Rescan: {e}")
        state.rescan_jobs[job_id]['status'] = 'error'
        state.rescan_jobs[job_id]['error'] = str(e)


def background_zip_task(job_id, file_ids):
    try:
        try:
            os.makedirs(ZIP_CACHE_DIR, exist_ok=True)
        except OSError as e:
            print(f"ERROR: Could not create zip directory: {e}")
            state.zip_jobs[job_id] = {'status': 'error', 'message': f'Server permission error: {e}'}
            return

        zip_filename = f"smartgallery_{job_id}.zip"
        zip_filepath = os.path.join(ZIP_CACHE_DIR, zip_filename)

        with get_db_connection() as conn:
            placeholders = ','.join(['?'] * len(file_ids))
            query = FILES_SELECT_PATH_NAME_BATCH.format(placeholders=placeholders)
            files_to_zip = conn.execute(query, file_ids).fetchall()

        if not files_to_zip:
            state.zip_jobs[job_id] = {'status': 'error', 'message': 'No valid files found.'}
            return

        with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file_row in files_to_zip:
                file_path = file_row['path']
                file_name = file_row['name']
                # Check the file exists
                if os.path.exists(file_path):
                    # Add file to zip
                    zf.write(file_path, file_name)

        # Job completed successfully
        state.zip_jobs[job_id] = {
            'status': 'ready',
            'filename': zip_filename
        }

        # Clean automatic: delete zip older than 24 hours
        try:
            now = time.time()
            for f in os.listdir(ZIP_CACHE_DIR):
                fp = os.path.join(ZIP_CACHE_DIR, f)
                if os.path.isfile(fp) and os.stat(fp).st_mtime < now - 86400:
                    os.remove(fp)
        except Exception:
            pass

    except Exception as e:
        print(f"Zip Error: {e}")
        state.zip_jobs[job_id] = {'status': 'error', 'message': str(e)}


@batch_bp.route('/rescan_folder', methods=['POST'])
def rescan_folder():
    data = request.json
    folder_key = data.get('folder_key')
    mode = data.get('mode', 'all')

    if not folder_key: return jsonify({'status': 'error', 'message': 'No folder provided.'}), 400
    folders = get_dynamic_folder_config()
    if folder_key not in folders: return jsonify({'status': 'error', 'message': 'Folder not found.'}), 404

    folder_path = folders[folder_key]['path']
    folder_name = folders[folder_key]['display_name']

    try:
        files_to_process = []
        with get_db_connection() as conn:
            query = FILES_SELECT_PATH_LASTSCAN_FOLDER
            rows = conn.execute(query, (folder_path + os.sep + '%',)).fetchall()

            folder_path_norm = os.path.normpath(folder_path)
            files_in_folder = [
                {'path': row['path'], 'last_scanned': row['last_scanned']}
                for row in rows
                if os.path.normpath(os.path.dirname(row['path'])) == folder_path_norm
            ]

            current_time = time.time()
            if mode == 'recent':
                cutoff_time = current_time - 3600
                files_to_process = [f['path'] for f in files_in_folder if (f['last_scanned'] or 0) < cutoff_time]
            else:
                files_to_process = [f['path'] for f in files_in_folder]

        if not files_to_process:
            return jsonify({'status': 'success', 'message': 'No files needed rescanning.', 'count': 0})

        # --- JOB CREATION ---
        job_id = str(uuid.uuid4())
        state.rescan_jobs[job_id] = {
            'status': 'processing',
            'current': 0,
            'total': len(files_to_process),
            'folder_key': folder_key,
            'folder_name': folder_name
        }

        # Start Worker with Job ID
        threading.Thread(target=background_rescan_worker, args=(job_id, files_to_process), daemon=True).start()
        publish_event("rescan_started", {
            "folder_key": folder_key,
            "job_id": job_id,
            "total": len(files_to_process),
        }, source="system")

        return jsonify({
            'status': 'started',
            'job_id': job_id,
            'total': len(files_to_process),
            'message': 'Background process started.'
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@batch_bp.route('/check_rescan_status/<job_id>')
def check_rescan_status(job_id):
    job = state.rescan_jobs.get(job_id)
    if not job:
        return jsonify({'status': 'not_found'})

    # Return copy of job data
    return jsonify(job)


@batch_bp.route('/prepare_batch_zip', methods=['POST'])
def prepare_batch_zip():
    data = request.json
    file_ids = data.get('file_ids', [])
    if not file_ids:
        return jsonify({'status': 'error', 'message': 'No files specified.'}), 400

    job_id = str(uuid.uuid4())
    state.zip_jobs[job_id] = {'status': 'processing'}

    thread = threading.Thread(target=background_zip_task, args=(job_id, file_ids))
    thread.daemon = True
    thread.start()

    return jsonify({'status': 'success', 'job_id': job_id, 'message': 'Zip generation started.'})


@batch_bp.route('/check_zip_status/<job_id>')
def check_zip_status(job_id):
    job = state.zip_jobs.get(job_id)
    if not job:
        return jsonify({'status': 'error', 'message': 'Job not found'}), 404
    response_data = job.copy()
    if job['status'] == 'ready' and 'filename' in job:
        response_data['download_url'] = url_for('batch.serve_zip_file', filename=job['filename'])

    return jsonify(response_data)


@batch_bp.route('/serve_zip/<filename>')
def serve_zip_file(filename):
    return send_from_directory(ZIP_CACHE_DIR, filename, as_attachment=True)
