# Smart Gallery for ComfyUI - Media Serving Routes
# File serving, thumbnails, storyboards, streaming, and metadata endpoints.

import os
import sys
import hashlib
import json
import logging
import subprocess
import uuid
import glob
import concurrent.futures
from collections import OrderedDict
from flask import Blueprint, request, jsonify, abort, send_file, send_from_directory, Response
from PIL import Image, ImageSequence
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

from smartgallery.config import (
    BASE_INPUT_PATH, BASE_OUTPUT_PATH, THUMBNAIL_CACHE_DIR
)
from smartgallery import state
from smartgallery.models import get_db_connection
from smartgallery.processing import extract_workflow, create_thumbnail, extract_parameters_chunk, parse_a1111_parameters, extract_gallery_metadata
from smartgallery.utils import generate_node_summary, clean_prompt_text
from smartgallery.parser import ComfyMetadataParser
from smartgallery.routes.files import get_file_info_from_db
from smartgallery.queries import FILES_SELECT_FOR_THUMBNAIL, FILES_SELECT_FOR_METADATA

media_bp = Blueprint('media', __name__, url_prefix='/galleryout')


def _get_ffmpeg_path():
    """Resolve the ffmpeg binary path from the known ffprobe location."""
    if not state.FFPROBE_EXECUTABLE_PATH:
        return None
    ffmpeg_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    candidate = os.path.join(os.path.dirname(state.FFPROBE_EXECUTABLE_PATH), ffmpeg_name)
    return candidate if os.path.exists(candidate) else ffmpeg_name


def _subprocess_flags():
    """Return creationflags for subprocess calls (hides console window on Windows)."""
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _probe_video_info(filepath, db_duration_str=None):
    """Probe a video file for fps, duration, and total frame count.

    Returns (fps, duration, total_frames). Falls back to DB duration string
    and sensible defaults if probing fails.
    """
    fps, duration, total_frames = 0.0, 0.0, 0

    if state.FFPROBE_EXECUTABLE_PATH:
        try:
            cmd = [
                state.FFPROBE_EXECUTABLE_PATH, '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'stream=duration,r_frame_rate,nb_frames',
                '-of', 'csv=p=0', filepath
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3,
                                 creationflags=_subprocess_flags())
            if res.stdout.strip():
                parts = res.stdout.strip().split(',')
                if len(parts) > 0 and parts[0]:
                    if '/' in parts[0]:
                        n, d = parts[0].split('/')
                        fps = float(n) / float(d)
                    else:
                        fps = float(parts[0])
                if len(parts) > 1 and parts[1]:
                    duration = float(parts[1])
                if len(parts) > 2 and parts[2]:
                    total_frames = int(parts[2])
        except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError, ValueError):
            pass

        # Fallback: format-level duration
        if duration <= 0:
            try:
                cmd2 = [
                    state.FFPROBE_EXECUTABLE_PATH, '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1', filepath
                ]
                res2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=3,
                                      creationflags=_subprocess_flags())
                if res2.stdout.strip():
                    duration = float(res2.stdout.strip())
            except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError, ValueError):
                pass

    # Fallback: parse DB duration string (e.g. "1:23" or "0:05:30")
    if duration <= 0 and db_duration_str:
        try:
            parts = db_duration_str.split(':')
            parts.reverse()
            duration = float(parts[0])
            if len(parts) > 1: duration += int(parts[1]) * 60
            if len(parts) > 2: duration += int(parts[2]) * 3600
        except (ValueError, IndexError):
            pass

    # Derive missing values
    if total_frames == 0 and duration > 0 and fps > 0:
        total_frames = int(duration * fps)
    elif fps == 0 and duration > 0 and total_frames > 0:
        fps = total_frames / duration

    return fps, duration, total_frames


@media_bp.route('/file/<string:file_id>')
def serve_file(file_id):
    filepath = get_file_info_from_db(file_id, 'path')
    if filepath.lower().endswith('.webp'): return send_file(filepath, mimetype='image/webp')
    # Enable range requests for video files (required for seeking and large files)
    ext = os.path.splitext(filepath)[1].lower()
    if ext in ('.mp4', '.webm', '.mov', '.mkv'):
        mimetype = {'.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime', '.mkv': 'video/x-matroska'}.get(ext, 'video/mp4')
        return send_file(filepath, mimetype=mimetype, conditional=True)
    return send_file(filepath)


@media_bp.route('/download/<string:file_id>')
def download_file(file_id):
    filepath = get_file_info_from_db(file_id, 'path')
    return send_file(filepath, as_attachment=True)


@media_bp.route('/workflow/<string:file_id>')
def download_workflow(file_id):
    info = get_file_info_from_db(file_id)
    filepath = info['path']
    original_filename = info['name']

    # EXPLICITLY request 'ui' format to ensure Groups, Notes and Positions are preserved.
    workflow_json = extract_workflow(filepath, target_type='ui')

    if workflow_json:
        base_name, _ = os.path.splitext(original_filename)
        new_filename = f"{base_name}.json"
        headers = {'Content-Disposition': f'attachment;filename="{new_filename}"'}
        return Response(workflow_json, mimetype='application/json', headers=headers)
    abort(404)


@media_bp.route('/node_summary/<string:file_id>')
def get_node_summary(file_id):
    try:
        # 1. Fetch basic info from DB
        file_info = get_file_info_from_db(file_id)
        filepath = file_info['path']
        db_dimensions = file_info.get('dimensions')

        # 2. Extract UI version for the Raw Node List (Always reliable)
        ui_json = extract_workflow(filepath, target_type='ui')
        if not ui_json:
            return jsonify({'status': 'error', 'message': 'Workflow not found for this file.'}), 404

        summary_data = generate_node_summary(ui_json)

        # 3. Try gallery_metadata JSON chunk first (our Image Saver — native JSON, no parsing)
        meta_data = {}
        gallery_meta = extract_gallery_metadata(filepath)
        if gallery_meta and gallery_meta.get('positive'):
            try:
                from smartgallery.parameters import cast_param

                positive = gallery_meta['positive']
                cleaned = clean_prompt_text(positive)
                size = gallery_meta.get('size', [])
                w = str(size[0]) if len(size) >= 2 else None
                h = str(size[1]) if len(size) >= 2 else None

                if not w and db_dimensions and 'x' in db_dimensions:
                    w, h = db_dimensions.split('x')
                    w, h = w.strip(), h.strip()

                # Build generation_params from structured JSON via data dictionary
                generation_params = []
                field_map = {
                    'model': 'Model', 'sampler': 'Sampler', 'scheduler': 'Scheduler',
                    'cfg': 'CFG scale', 'steps': 'Steps', 'seed': 'Seed',
                }
                for json_key, param_key in field_map.items():
                    val = gallery_meta.get(json_key)
                    if val is not None:
                        generation_params.append(cast_param(param_key, str(val)))
                if w and h:
                    generation_params.append(cast_param('Size', f'{w}x{h}'))
                # Optional extended params
                if gallery_meta.get('denoise') is not None and gallery_meta['denoise'] != 1.0:
                    generation_params.append(cast_param('Denoising strength', str(gallery_meta['denoise'])))
                if gallery_meta.get('clip_skip'):
                    generation_params.append(cast_param('Clip skip', str(gallery_meta['clip_skip'])))
                if gallery_meta.get('model_hash'):
                    generation_params.append(cast_param('Model hash', str(gallery_meta['model_hash'])))
                generation_params.sort(key=lambda p: p['order'])

                meta_data = {
                    'positive_prompt': positive,
                    'negative_prompt': gallery_meta.get('negative', ''),
                    'positive_prompt_clean': cleaned['text'],
                    'seed': gallery_meta.get('seed'),
                    'steps': gallery_meta.get('steps'),
                    'cfg': gallery_meta.get('cfg'),
                    'sampler': gallery_meta.get('sampler'),
                    'model': gallery_meta.get('model'),
                    'width': w,
                    'height': h,
                    'loras': cleaned['loras'],
                    'civitai_resources': gallery_meta.get('civitai_resources', []),
                    'generation_params': generation_params,
                }
            except Exception as e:
                print(f"gallery_metadata parse warning: {e}")

        # 4. Fall back to A1111 parameters chunk (legacy, downloaded images)
        if not meta_data:
            params_raw = extract_parameters_chunk(filepath)
            if params_raw:
                try:
                    parsed_params = parse_a1111_parameters(params_raw)
                    if parsed_params.get('positive_prompt') and len(parsed_params['positive_prompt']) > 5:
                        w, h = None, None
                        size_str = parsed_params.get('size', '')
                        if size_str and 'x' in size_str:
                            parts = size_str.split('x')
                            w, h = parts[0].strip(), parts[1].strip()
                        elif db_dimensions and 'x' in db_dimensions:
                            w, h = db_dimensions.split('x')
                            w, h = w.strip(), h.strip()

                        civitai_list = []
                        if parsed_params.get('civitai_resources'):
                            try:
                                civitai_list = json.loads(parsed_params['civitai_resources'])
                            except (json.JSONDecodeError, ValueError):
                                pass

                        cleaned = clean_prompt_text(parsed_params['positive_prompt'])
                        meta_data = {
                            'positive_prompt': parsed_params['positive_prompt'],
                            'negative_prompt': parsed_params.get('negative_prompt', ''),
                            'positive_prompt_clean': cleaned['text'],
                            'seed': parsed_params.get('seed'),
                            'steps': parsed_params.get('steps'),
                            'cfg': parsed_params.get('cfg'),
                            'sampler': parsed_params.get('sampler'),
                            'model': parsed_params.get('model'),
                            'width': w,
                            'height': h,
                            'loras': cleaned['loras'],
                            'civitai_resources': civitai_list,
                            'generation_params': parsed_params.get('generation_params', []),
                        }
                except Exception as e:
                    print(f"Parameters chunk parse warning: {e}")

        # 5. Fall back to workflow graph parsing
        if not meta_data:
            api_json = extract_workflow(filepath, target_type='api')

            try:
                json_source = api_json if api_json else ui_json
                wf_data = json.loads(json_source)
                if isinstance(wf_data, list):
                    wf_data = {str(i): n for i, n in enumerate(wf_data)}

                parser = ComfyMetadataParser(wf_data)
                parsed_meta = parser.parse()

                # --- STRICT VALIDATION LOGIC ---
                tech_count = 0
                if parsed_meta.get('seed'): tech_count += 1
                if parsed_meta.get('model'): tech_count += 1
                if parsed_meta.get('steps'): tech_count += 1
                if parsed_meta.get('sampler'): tech_count += 1

                has_prompt = len(parsed_meta.get('positive_prompt', '')) > 5

                if has_prompt and tech_count >= 2:
                    meta_data = parsed_meta
                    meta_data['civitai_resources'] = []
                    meta_data['generation_params'] = []
                    if not meta_data.get('width') or not meta_data.get('height'):
                        if db_dimensions and 'x' in db_dimensions:
                            w, h = db_dimensions.split('x')
                            meta_data['width'], meta_data['height'] = w.strip(), h.strip()
                else:
                    meta_data = {}

            except Exception as e:
                print(f"Metadata Validation Warning: {e}")
                meta_data = {}

        return jsonify({
            'status': 'success',
            'summary': summary_data, # Raw Node List (Always shown)
            'meta': meta_data        # Dashboard Data (Only if valid/complete)
        })

    except Exception as e:
        print(f"ERROR generating node summary: {e}")
        return jsonify({'status': 'error', 'message': str(e)})


# In-memory cache: file_id → thumbnail path (avoids DB + glob on every request)
# Bounded LRU to prevent unbounded growth on large galleries (49K+ files)
class _LRUCache:
    def __init__(self, maxsize=5000):
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key):
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(self, key, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

_thumb_path_cache = _LRUCache(maxsize=5000)

@media_bp.route('/thumbnail/<string:file_id>')
def serve_thumbnail(file_id):
    # Fast path: check in-memory cache first
    cached_path = _thumb_path_cache.get(file_id)
    if cached_path and os.path.exists(cached_path):
        response = send_file(cached_path)
        response.headers['Cache-Control'] = 'public, max-age=86400, immutable'
        return response

    # Only fetch what we need, not the full row
    with get_db_connection() as conn:
        row = conn.execute(FILES_SELECT_FOR_THUMBNAIL, (file_id,)).fetchone()
    if not row:
        abort(404)
    info = dict(row)
    filepath, mtime = info['path'], info['mtime']
    file_hash = hashlib.md5((filepath + str(mtime)).encode()).hexdigest()

    # Check common extensions directly instead of glob
    for ext in ('.jpg', '.png', '.webp', '.gif'):
        candidate = os.path.join(THUMBNAIL_CACHE_DIR, file_hash + ext)
        if os.path.exists(candidate):
            _thumb_path_cache.set(file_id, candidate)
            response = send_file(candidate)
            response.headers['Cache-Control'] = 'public, max-age=86400, immutable'
            return response

    print(f"WARN: Thumbnail not found for {os.path.basename(filepath)}, generating...")
    cache_path = create_thumbnail(filepath, file_hash, info['type'])
    if cache_path and os.path.exists(cache_path):
        _thumb_path_cache.set(file_id, cache_path)
        response = send_file(cache_path)
        response.headers['Cache-Control'] = 'public, max-age=86400, immutable'
        return response
    return "Thumbnail generation failed", 404


# --- STORYBOARD (GRID SYSTEM) - FAST + SMART CORRUPTION DETECTION ---
@media_bp.route('/storyboard/<string:file_id>')
def get_storyboard(file_id):
    # 1. Validation
    has_ffmpeg = state.FFPROBE_EXECUTABLE_PATH is not None

    try:
        info = get_file_info_from_db(file_id)
        if info['type'] not in ['video', 'animated_image']:
            return jsonify({'status': 'error', 'message': 'Not a video or animated file'}), 400

        if info['type'] == 'video' and not has_ffmpeg:
             return jsonify({'status': 'error', 'message': 'FFmpeg not available'}), 501

        filepath = info['path']
        mtime = info['mtime']

        # 2. Cache Strategy
        file_hash = hashlib.md5((filepath + str(mtime)).encode()).hexdigest()
        cache_subdir = os.path.join(THUMBNAIL_CACHE_DIR, file_hash)

        # Return cached results immediately if available
        if os.path.exists(cache_subdir):
            cached_files = sorted(glob.glob(os.path.join(cache_subdir, "frame_*.jpg")))
            if len(cached_files) > 0:
                urls = [f"/galleryout/storyboard_frame/{file_hash}/{os.path.basename(f)}" for f in cached_files]
                _fps, _duration, _total_frames = _probe_video_info(filepath, info.get('duration')) if info['type'] == 'video' else (0, 0, 0)
                return jsonify({'status': 'success', 'cached': True, 'frames': urls,
                                'totalVideoFrames': _total_frames, 'fps': round(_fps, 2), 'duration': round(_duration, 2)})

        os.makedirs(cache_subdir, exist_ok=True)

        # 3. Get Duration + FPS + Frame Count
        if info['type'] == 'video' and has_ffmpeg:
            fps, duration, total_video_frames = _probe_video_info(filepath, info.get('duration'))
        else:
            fps, duration, total_video_frames = 0, 0, 0

        # Final fallback for videos with no probe data
        if duration <= 0 and info['type'] == 'video':
            duration = 60
        if fps <= 0 and info['type'] == 'video':
            fps = 25

        # 4. SMART CORRUPTION TEST - Test at 50% instead of end (faster + reliable)
        needs_transcode = False

        if info['type'] == 'video' and has_ffmpeg and duration > 15:
            print(f"Quick test...")

            ffmpeg_bin = _get_ffmpeg_path()
            test_path = os.path.join(cache_subdir, "test.jpg")
            test_timestamp = duration * 0.5
            creation_flags = _subprocess_flags()

            # Adaptive timeout based on duration
            test_timeout = min(20, max(8, int(duration / 100)))  # 8-20s range

            cmd_test = [
                ffmpeg_bin, '-y',
                '-ss', f"{test_timestamp:.3f}",
                '-i', filepath,
                '-frames:v', '1',
                '-vf', 'scale=-2:240:flags=fast_bilinear',
                '-q:v', '5',
                test_path
            ]

            try:
                subprocess.run(
                    cmd_test,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=test_timeout,
                    creationflags=creation_flags
                )

                if os.path.exists(test_path) and os.path.getsize(test_path) > 100:
                    print(f"Healthy")
                    needs_transcode = False
                else:
                    print(f"Corrupted!")
                    needs_transcode = True

            except subprocess.TimeoutExpired:
                print(f"Slow seek (normal for large files)")
                needs_transcode = False
            except Exception as e:
                print(f"Corrupted: {e}")
                needs_transcode = True

            if os.path.exists(test_path):
                try: os.remove(test_path)
                except OSError: pass

        # 5. TRANSCODING if needed
        source_for_extraction = filepath
        temp_transcoded = None

        if needs_transcode:
            print(f"Transcoding...")

            try:
                ffmpeg_bin = _get_ffmpeg_path()
                temp_transcoded = os.path.join(cache_subdir, f"temp_proxy_{uuid.uuid4().hex}.mp4")

                cmd_transcode = [
                    ffmpeg_bin, '-y',
                    '-i', filepath,
                    '-vf', 'scale=-2:480',
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-crf', '28',
                    '-an',
                    '-movflags', '+faststart',
                    temp_transcoded
                ]

                subprocess.run(
                    cmd_transcode,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    creationflags=_subprocess_flags()
                )

                if os.path.exists(temp_transcoded) and os.path.getsize(temp_transcoded) > 1000:
                    print(f"Transcoded")
                    source_for_extraction = temp_transcoded
                    fps, duration, total_video_frames = _probe_video_info(temp_transcoded)

            except Exception as e:
                print(f"Transcode failed: {e}")
                if temp_transcoded and os.path.exists(temp_transcoded):
                    try: os.remove(temp_transcoded)
                    except OSError: pass
                temp_transcoded = None

        # 6. Worker Function (OPTIMIZED)
        def extract_and_save_frame(index, timestamp):
            out_filename = f"frame_{index:02d}.jpg"
            out_path = os.path.join(cache_subdir, out_filename)

            try:
                img = None
                actual_timestamp = timestamp
                actual_frame_number = None

                # A. Video Extraction
                if info['type'] == 'video' and has_ffmpeg:
                    actual_timestamp = timestamp

                    if fps > 0:
                        actual_frame_number = int(timestamp * fps)

                    ffmpeg_bin = _get_ffmpeg_path()
                    creation_flags = _subprocess_flags()

                    # Fast extraction
                    cmd = [
                        ffmpeg_bin, '-y',
                        '-ss', f"{timestamp:.3f}",
                        '-i', source_for_extraction,
                        '-frames:v', '1',
                        '-vf', 'scale=-2:360:flags=fast_bilinear',
                        '-q:v', '4',
                        '-preset', 'ultrafast',
                        out_path
                    ]

                    try:
                        subprocess.run(
                            cmd,
                            check=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=8,
                            creationflags=creation_flags
                        )

                        if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
                            img = Image.open(out_path)

                    except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError):
                        if os.path.exists(out_path):
                            try: os.remove(out_path)
                            except OSError: pass

                        # Slow seek fallback
                        cmd_slow = [
                            ffmpeg_bin, '-y',
                            '-i', source_for_extraction,
                            '-ss', f"{timestamp:.3f}",
                            '-frames:v', '1',
                            '-vf', 'scale=-2:360:flags=fast_bilinear',
                            '-q:v', '4',
                            out_path
                        ]

                        try:
                            subprocess.run(
                                cmd_slow,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                timeout=40,
                                creationflags=creation_flags
                            )

                            if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
                                img = Image.open(out_path)
                        except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError):
                            pass

                # B. Animation Extraction
                elif info['type'] == 'animated_image':
                    with Image.open(filepath) as source_img:
                        is_anim = getattr(source_img, 'is_animated', False)
                        total_frames = source_img.n_frames if is_anim else 1
                        pct = index / 10.0
                        target_frame_idx = int(pct * (total_frames - 1))
                        source_img.seek(target_frame_idx)
                        img = source_img.copy().convert('RGB')
                        img.thumbnail((640, 360))

                        actual_timestamp = None
                        actual_frame_number = target_frame_idx + 1

                # C. Professional Overlay
                if img:
                    from PIL import ImageDraw, ImageFont
                    draw = ImageDraw.Draw(img)

                    # Calculate text
                    if actual_timestamp is None:
                        # Animation
                        with Image.open(filepath) as temp_img:
                            total_frames = temp_img.n_frames if getattr(temp_img, 'is_animated', False) else 1
                        time_str = f"#{actual_frame_number}/{total_frames}"
                    else:
                        # Video: timestamp + frame
                        display_ts = round(actual_timestamp)
                        m, s = int(display_ts // 60), int(display_ts % 60)

                        if actual_frame_number is not None and total_video_frames > 0:
                            display_frame_number = actual_frame_number + 1
                            time_str = f"{m:02d}:{s:02d} | #{display_frame_number}/{total_video_frames}"
                        else:
                            time_str = f"{m:02d}:{s:02d}"

                    # Font
                    font_size = 24
                    font = None
                    try:
                        font = ImageFont.load_default(size=font_size)
                    except (OSError, TypeError):
                        font = ImageFont.load_default()

                    # Measure
                    left, top, right, bottom = draw.textbbox((0, 0), time_str, font=font)
                    txt_w = right - left
                    txt_h = bottom - top

                    # Box
                    pad_x = 6
                    pad_y = 4
                    box_w = txt_w + (pad_x * 2)
                    box_h = txt_h + (pad_y * 2)

                    # Draw
                    draw.rectangle([0, 0, box_w, box_h], fill="black", outline=None)
                    draw.text((pad_x - left, pad_y - top), time_str, font=font, fill="#ffffff")

                    # Save
                    img.save(out_path, quality=85)
                    img.close()

                    return f"/galleryout/storyboard_frame/{file_hash}/{out_filename}"

            except Exception as e:
                print(f"Worker error {index}: {e}")

            return None

        # 7. Parallel Execution
        timestamps = []

        if info['type'] == 'video':
            safe_end = max(0, duration - 0.1)
            base_timestamps = [(i, (safe_end / 10) * i) for i in range(11)]
            if total_video_frames > 0 and fps > 0:
                last_frame_timestamp = (total_video_frames - 1) / fps
                last_frame_timestamp = min(last_frame_timestamp, duration - 0.001)
                base_timestamps[-1] = (10, last_frame_timestamp)
            else:
                base_timestamps[-1] = (10, duration - 0.001)
            timestamps = base_timestamps
        else:
            timestamps = [(i, 0) for i in range(11)]

        frame_urls = [None] * 11

        print(f"Extracting...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=11) as executor:
            futures = {executor.submit(extract_and_save_frame, i, ts): i for i, ts in timestamps}
            for future in concurrent.futures.as_completed(futures):
                idx = futures[future]
                res = future.result()
                if res:
                    frame_urls[idx] = res

        success_count = sum(1 for url in frame_urls if url is not None)
        print(f"{success_count}/11")

        # Cleanup
        if temp_transcoded and os.path.exists(temp_transcoded):
            try:
                os.remove(temp_transcoded)
            except OSError:
                pass

        final_urls = [url for url in frame_urls if url is not None]

        if not final_urls:
             return jsonify({'status': 'error', 'message': 'Extraction failed completely.'}), 500

        return jsonify({'status': 'success', 'cached': False, 'frames': final_urls,
                        'totalVideoFrames': total_video_frames, 'fps': round(fps, 2), 'duration': round(duration, 2)})

    except Exception as e:
        print(f"Storyboard error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@media_bp.route('/storyboard_frame/<string:file_hash>/<string:filename>')
def serve_storyboard_frame(file_hash, filename):
    safe_name = secure_filename(filename)
    directory = os.path.join(THUMBNAIL_CACHE_DIR, file_hash)
    return send_from_directory(directory, safe_name)


@media_bp.route('/storyboard_hires/<string:file_id>/<int:frame_index>')
def storyboard_hires(file_id, frame_index):
    """Extract a single frame at native resolution on demand."""
    has_ffmpeg = state.FFPROBE_EXECUTABLE_PATH is not None
    if not has_ffmpeg:
        return jsonify({'status': 'error', 'message': 'FFmpeg not available'}), 501

    try:
        info = get_file_info_from_db(file_id)
        if info['type'] not in ['video', 'animated_image']:
            return jsonify({'status': 'error', 'message': 'Not a video'}), 400

        filepath = info['path']
        mtime = info['mtime']

        _, duration, _ = _probe_video_info(filepath, info.get('duration'))
        if duration <= 0:
            duration = 60

        # Calculate timestamp for this frame (11 frames, evenly spaced)
        safe_end = max(0, duration - 0.1)
        frame_index = max(0, min(10, frame_index))
        timestamp = (safe_end / 10) * frame_index

        # Extract at native resolution (no scale filter)
        file_hash = hashlib.md5((filepath + str(mtime)).encode()).hexdigest()
        cache_subdir = os.path.join(THUMBNAIL_CACHE_DIR, file_hash)
        os.makedirs(cache_subdir, exist_ok=True)
        out_path = os.path.join(cache_subdir, f"hires_{frame_index:02d}.jpg")

        # Return cached if exists
        if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
            return send_file(out_path, mimetype='image/jpeg')

        cmd = [
            _get_ffmpeg_path(), '-y',
            '-ss', f"{timestamp:.3f}",
            '-i', filepath,
            '-frames:v', '1',
            '-q:v', '2',
            out_path
        ]

        subprocess.run(
            cmd, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=10,
            creationflags=_subprocess_flags()
        )

        if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
            return send_file(out_path, mimetype='image/jpeg')

        return jsonify({'status': 'error', 'message': 'Frame extraction failed'}), 500

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@media_bp.route('/input_file/<path:filename>')
def serve_input_file(filename):
    """Serves input files directly from the ComfyUI Input folder."""
    try:
        # Path traversal prevention via abspath containment check
        # (secure_filename would mangle subdirectory paths from <path:> converter)
        filepath = os.path.abspath(os.path.join(BASE_INPUT_PATH, filename))
        if not filepath.startswith(os.path.abspath(BASE_INPUT_PATH)):
            abort(403)

        # For webp, forcing the correct mimetype
        if filename.lower().endswith('.webp'):
            return send_from_directory(BASE_INPUT_PATH, filename, mimetype='image/webp', as_attachment=False)

        return send_from_directory(BASE_INPUT_PATH, filename, as_attachment=False)
    except Exception as e:
        abort(404)


@media_bp.route('/check_metadata/<string:file_id>')
def check_metadata(file_id):
    """
    Lightweight endpoint to check real-time status of metadata.
    Now includes Real Path resolution for mounted folders.
    """
    try:
        with get_db_connection() as conn:
            row = conn.execute(FILES_SELECT_FOR_METADATA, (file_id,)).fetchone()

        if not row:
            return jsonify({'status': 'error', 'message': 'File not found'}), 404

        # Resolve Real Path (Handles Windows Junctions and Linux Symlinks)
        internal_path = row['path']
        real_path_resolved = os.path.realpath(internal_path)

        # Check if they differ (ignore case on Windows for safety)
        is_different = False
        if os.name == 'nt':
            if internal_path.lower() != real_path_resolved.lower():
                is_different = True
        else:
            if internal_path != real_path_resolved:
                is_different = True

        return jsonify({
            'status': 'success',
            'has_workflow': bool(row['has_workflow']),
            'real_path': real_path_resolved if is_different else None
        })
    except Exception as e:
        print(f"Metadata Check Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@media_bp.route('/stream/<string:file_id>')
def stream_video(file_id):
    """
    Streams video files by transcoding them on-the-fly using FFmpeg.
    This allows professional formats like ProRes to be viewed in any browser.
    Includes a safety scale filter to ensure smooth playback even for 4K+ sources.
    """
    filepath = get_file_info_from_db(file_id, 'path')

    if not state.FFPROBE_EXECUTABLE_PATH:
        abort(404, description="FFmpeg/FFprobe not found on system.")

    # Determine ffmpeg executable path based on ffprobe location
    ffmpeg_dir = os.path.dirname(state.FFPROBE_EXECUTABLE_PATH)
    ffmpeg_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    ffmpeg_path = os.path.join(ffmpeg_dir, ffmpeg_name) if ffmpeg_dir else ffmpeg_name

    # FFmpeg command for fast on-the-fly transcoding
    cmd = [
        ffmpeg_path,
        '-i', filepath,
        '-vcodec', 'libx264',
        '-preset', 'ultrafast',
        '-tune', 'zerolatency',
        '-vf', "scale='min(1280,iw)':-2",
        '-acodec', 'aac',
        '-b:a', '128k',
        '-f', 'mp4',
        '-movflags', 'frag_keyframe+empty_moov+default_base_moof',
        'pipe:1'
    ]

    def generate():
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        try:
            while True:
                data = process.stdout.read(16384)
                if not data:
                    break
                yield data
        finally:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()

    return Response(generate(), mimetype='video/mp4')
