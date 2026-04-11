# Smart Gallery for ComfyUI - File Processing Pipeline
# Metadata extraction, thumbnail generation, workflow parsing.

import os
import sys
import hashlib
import json
import logging
import re
import shutil
import time
import glob as glob_module
import subprocess
import cv2
from PIL import Image, ImageSequence

logger = logging.getLogger(__name__)

from smartgallery.config import (
    BASE_OUTPUT_PATH, FFPROBE_MANUAL_PATH, THUMBNAIL_WIDTH, THUMBNAIL_CACHE_DIR,
    WEBP_ANIMATED_FPS, DELETE_TO, TRASH_FOLDER, WORKFLOW_PROMPT_BLACKLIST
)
from smartgallery.utils import normalize_smart_path, format_duration, _is_garbage_text
from smartgallery import state


def _get_ffmpeg_path():
    """Resolve the ffmpeg binary path from the known ffprobe location."""
    if not state.FFPROBE_EXECUTABLE_PATH:
        return None
    ffmpeg_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    candidate = os.path.join(os.path.dirname(state.FFPROBE_EXECUTABLE_PATH), ffmpeg_name)
    return candidate if os.path.exists(candidate) else ffmpeg_name


def safe_delete_file(filepath):
    """
    Safely delete a file by either moving it to trash (if DELETE_TO is configured)
    or permanently deleting it.
    """
    if DELETE_TO and TRASH_FOLDER:
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        filename = os.path.basename(filepath)
        trash_filename = f"{timestamp}_{filename}"
        trash_path = os.path.join(TRASH_FOLDER, trash_filename)

        counter = 1
        while os.path.exists(trash_path):
            name_without_ext, ext = os.path.splitext(filename)
            trash_filename = f"{timestamp}_{name_without_ext}_{counter}{ext}"
            trash_path = os.path.join(TRASH_FOLDER, trash_filename)
            counter += 1

        shutil.move(filepath, trash_path)
        print(f"INFO: Moved file to trash: {trash_path}")
    else:
        os.remove(filepath)


def find_ffprobe_path():
    """Locate the ffprobe executable."""
    if FFPROBE_MANUAL_PATH and os.path.isfile(FFPROBE_MANUAL_PATH):
        try:
            subprocess.run([FFPROBE_MANUAL_PATH, "-version"], capture_output=True, check=True,
                           timeout=10,
                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            return FFPROBE_MANUAL_PATH
        except (subprocess.SubprocessError, OSError, subprocess.TimeoutExpired): pass
    base_name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
    try:
        subprocess.run([base_name, "-version"], capture_output=True, check=True,
                       timeout=10,
                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        return base_name
    except (subprocess.SubprocessError, OSError, subprocess.TimeoutExpired): pass
    print("WARNING: ffprobe not found. Video metadata analysis will be disabled.")
    return None


def _validate_and_get_workflow(json_string):
    try:
        data = json.loads(json_string)
        workflow_data = data.get('workflow', data.get('prompt', data))

        if isinstance(workflow_data, dict):
            if 'nodes' in workflow_data:
                return json.dumps(workflow_data), 'ui'

            is_api = False
            for k, v in workflow_data.items():
                if isinstance(v, dict) and 'class_type' in v:
                    is_api = True
                    break
            if is_api:
                return json.dumps(workflow_data), 'api'

    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    return None, None


def _scan_bytes_for_workflow(content_bytes):
    """Generator that yields all valid JSON objects found in the byte stream."""
    try:
        stream_str = content_bytes.decode('utf-8', errors='ignore')
    except (UnicodeDecodeError, AttributeError):
        return

    start_pos = 0
    while True:
        first_brace = stream_str.find('{', start_pos)
        if first_brace == -1:
            break

        open_braces = 0
        start_index = first_brace

        for i in range(start_index, len(stream_str)):
            char = stream_str[i]
            if char == '{':
                open_braces += 1
            elif char == '}':
                open_braces -= 1

            if open_braces == 0:
                candidate = stream_str[start_index : i + 1]
                try:
                    json.loads(candidate)
                    yield candidate
                except (json.JSONDecodeError, ValueError):
                    pass

                start_pos = i + 1
                break
        else:
            break


def extract_workflow(filepath, target_type='ui'):
    """
    Extracts workflow JSON from image/video files.

    Args:
        filepath: Path to the file.
        target_type: 'ui' (for visual node graph) or 'api' (for real execution values).
    """
    ext = os.path.splitext(filepath)[1].lower()
    video_exts = ['.mp4', '.mkv', '.webm', '.mov']
    image_exts = ['.png', '.jpg', '.jpeg', '.webp', '.gif']

    found_workflows = {}

    def analyze_json(json_str):
        wf, wf_type = _validate_and_get_workflow(json_str)
        if wf and wf_type:
            if wf_type not in found_workflows:
                found_workflows[wf_type] = wf

    if ext not in video_exts and ext not in image_exts:
        return None

    if ext in video_exts:
        current_ffprobe_path = state.FFPROBE_EXECUTABLE_PATH
        if not current_ffprobe_path:
            current_ffprobe_path = find_ffprobe_path()

        if current_ffprobe_path:
            try:
                cmd = [current_ffprobe_path, '-v', 'quiet', '-print_format', 'json', '-show_format', filepath]
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                                        check=True, timeout=30,
                                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
                data = json.loads(result.stdout)
                if 'format' in data and 'tags' in data['format']:
                    for value in data['format']['tags'].values():
                        if isinstance(value, str) and value.strip().startswith('{'):
                            analyze_json(value)
            except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError,
                    json.JSONDecodeError, ValueError) as e:
                logger.debug("Workflow extraction via ffprobe failed for %s: %s", os.path.basename(filepath), e)
    else:
        try:
            with Image.open(filepath) as img:
                for key in ['workflow', 'prompt']:
                    val = img.info.get(key)
                    if val: analyze_json(val)

                exif_data = img.info.get('exif')
                if exif_data and isinstance(exif_data, bytes):
                    try:
                        exif_str = exif_data.decode('utf-8', errors='ignore')
                        if 'workflow:{' in exif_str:
                            start = exif_str.find('workflow:{') + len('workflow:')
                            for json_candidate in _scan_bytes_for_workflow(exif_str[start:].encode('utf-8')):
                                analyze_json(json_candidate)
                    except (UnicodeDecodeError, ValueError): pass

                    for json_str in _scan_bytes_for_workflow(exif_data):
                        analyze_json(json_str)
        except (OSError, Image.DecompressionBombError) as e:
            logger.warning("Image workflow extraction failed for %s: %s", os.path.basename(filepath), e)

    # Raw byte scan (ultimate fallback)
    if not found_workflows:
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            for json_str in _scan_bytes_for_workflow(content):
                analyze_json(json_str)
                if target_type in found_workflows: break
        except OSError as e:
            logger.warning("Raw byte scan failed for %s: %s", os.path.basename(filepath), e)

    if target_type in found_workflows:
        return found_workflows[target_type]

    if found_workflows:
        return list(found_workflows.values())[0]

    return None


def extract_gallery_metadata(filepath):
    """
    Extract the 'gallery_metadata' JSON text chunk from a PNG file.
    Written by our Image Saver fork — structured JSON, no parsing needed.
    Returns parsed dict or None.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext != '.png':
        return None
    try:
        with Image.open(filepath) as img:
            raw = img.info.get('gallery_metadata')
            if raw:
                return json.loads(raw)
    except (OSError, Image.DecompressionBombError, json.JSONDecodeError, ValueError):
        pass
    return None


def extract_parameters_chunk(filepath):
    """
    Extract the A1111/CivitAI 'parameters' text chunk from a PNG file.
    This chunk is written by CivitAI-aware save nodes (e.g. Image Saver)
    and contains clean prompts, generation params, and CivitAI resource links.
    Returns the raw string or None.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext != '.png':
        return None
    try:
        with Image.open(filepath) as img:
            return img.info.get('parameters')
    except (OSError, Image.DecompressionBombError):
        return None


def parse_a1111_parameters(text):
    """
    Parse an A1111-format parameters string into structured metadata.
    Format:
        <positive prompt>
        Negative prompt: <negative prompt>
        Steps: 20, Sampler: Euler a, CFG scale: 4.0, Seed: 123, Size: 720x1248, Model: name, ...
        Civitai resources: [{...}]

    Returns dict with convenience keys (steps, sampler, etc.) for DB pipeline,
    plus generation_params list of typed dicts for the frontend.
    """
    from smartgallery.parameters import parse_params_line

    result = {
        'positive_prompt': '', 'negative_prompt': '',
        'steps': None, 'sampler': None, 'cfg': None,
        'seed': None, 'size': None, 'model': None,
        'civitai_resources': '',
        'generation_params': []
    }

    if not text or not isinstance(text, str):
        return result

    # Split positive prompt from the rest
    neg_marker = '\nNegative prompt: '
    if neg_marker in text:
        result['positive_prompt'] = text[:text.index(neg_marker)].strip()
        remainder = text[text.index(neg_marker) + len(neg_marker):]
    else:
        # No negative prompt — look for Steps: line directly
        remainder = text
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if line.startswith('Steps: '):
                result['positive_prompt'] = '\n'.join(lines[:i]).strip()
                remainder = '\n'.join(lines[i:])
                break
        else:
            result['positive_prompt'] = text.strip()
            return result

    # Find the params line (starts with "Steps: ")
    lines = remainder.split('\n')
    params_line = None
    neg_lines = []
    for i, line in enumerate(lines):
        if line.startswith('Steps: '):
            params_line = line
            neg_lines = lines[:i]
            break
    else:
        result['negative_prompt'] = remainder.strip()
        return result

    result['negative_prompt'] = '\n'.join(neg_lines).strip()

    # Extract CivitAI resources JSON before parsing key-value pairs
    civitai_match = re.search(r'Civitai resources: (\[.*\])', params_line)
    if civitai_match:
        result['civitai_resources'] = civitai_match.group(1)
        params_line = params_line[:civitai_match.start()].rstrip(', ')

    # Parse ALL key-value pairs via the data dictionary
    generation_params = parse_params_line(params_line)
    result['generation_params'] = generation_params

    # Populate convenience keys for backward compatibility (DB pipeline, scan)
    convenience_map = {
        'Steps': 'steps', 'Sampler': 'sampler', 'CFG scale': 'cfg',
        'Seed': 'seed', 'Size': 'size', 'Model': 'model',
    }
    for param in generation_params:
        field = convenience_map.get(param['key'])
        if field:
            result[field] = param['value']

    return result


def is_webp_animated(filepath):
    try:
        with Image.open(filepath) as img: return getattr(img, 'is_animated', False)
    except (OSError, Image.DecompressionBombError): return False


def analyze_file_metadata(filepath):
    """Extract dimensions, duration, file type from media."""
    details = {'type': 'unknown', 'duration': '', 'dimensions': '', 'has_workflow': 0}
    ext_lower = os.path.splitext(filepath)[1].lower()
    type_map = {
        '.png': 'image', '.jpg': 'image', '.jpeg': 'image',
        '.bmp': 'image', '.tiff': 'image', '.tif': 'image',
        '.gif': 'animated_image',
        '.mp4': 'video', '.webm': 'video', '.mov': 'video',
        '.mkv': 'video', '.avi': 'video', '.m4v': 'video',
        '.wmv': 'video', '.flv': 'video', '.mts': 'video', '.ts': 'video',
        '.mp3': 'audio', '.wav': 'audio', '.ogg': 'audio', '.flac': 'audio', '.m4a': 'audio'
    }
    details['type'] = type_map.get(ext_lower, 'unknown')
    if details['type'] == 'unknown' and ext_lower == '.webp':
        details['type'] = 'animated_image' if is_webp_animated(filepath) else 'image'
    if 'image' in details['type']:
        try:
            with Image.open(filepath) as img: details['dimensions'] = f"{img.width}x{img.height}"
        except (OSError, Image.DecompressionBombError) as e:
            logger.warning("Could not read image dimensions for %s: %s", os.path.basename(filepath), e)
    if extract_workflow(filepath): details['has_workflow'] = 1
    total_duration_sec = 0
    if details['type'] == 'video':
        try:
            cap = cv2.VideoCapture(filepath)
            if cap.isOpened():
                fps, count = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
                if fps > 0 and count > 0: total_duration_sec = count / fps
                details['dimensions'] = f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}"
                cap.release()
        except (OSError, cv2.error) as e:
            logger.warning("Video metadata extraction failed for %s: %s", os.path.basename(filepath), e)
    elif details['type'] == 'animated_image':
        try:
            with Image.open(filepath) as img:
                if getattr(img, 'is_animated', False):
                    if ext_lower == '.gif':
                        total_duration_sec = sum(frame.info.get('duration', 100) for frame in ImageSequence.Iterator(img)) / 1000
                    elif ext_lower == '.webp':
                        total_duration_sec = getattr(img, 'n_frames', 1) / WEBP_ANIMATED_FPS
        except (OSError, Image.DecompressionBombError) as e:
            logger.warning("Animated image metadata failed for %s: %s", os.path.basename(filepath), e)
    if total_duration_sec > 0: details['duration'] = format_duration(total_duration_sec)
    return details


def create_thumbnail(filepath, file_hash, file_type):
    """Generate thumbnail for an image or video file."""
    Image.MAX_IMAGE_PIXELS = None

    if file_type in ['image', 'animated_image']:
        try:
            with Image.open(filepath) as img:
                fmt = 'gif' if img.format == 'GIF' else 'webp' if img.format == 'WEBP' else 'jpeg'
                cache_path = os.path.join(THUMBNAIL_CACHE_DIR, f"{file_hash}.{fmt}")

                if file_type == 'animated_image' and getattr(img, 'is_animated', False):
                    frames = [fr.copy() for fr in ImageSequence.Iterator(img)]
                    if frames:
                        for frame in frames:
                            frame.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 2), Image.Resampling.LANCZOS)

                        processed_frames = [frame.convert('RGBA').convert('RGB') for frame in frames]
                        if processed_frames:
                            processed_frames[0].save(
                                cache_path,
                                save_all=True,
                                append_images=processed_frames[1:],
                                duration=img.info.get('duration', 100),
                                loop=img.info.get('loop', 0),
                                optimize=True
                            )
                            return cache_path
                else:
                    img.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 2), Image.Resampling.LANCZOS)
                    if img.mode != 'RGB': img = img.convert('RGB')
                    img.save(cache_path, 'JPEG', quality=85)
                    return cache_path

        except Exception as e:
            print(f"ERROR (Pillow): Thumbnail failed for {os.path.basename(filepath)}: {e}")

    elif file_type == 'video':
        cache_path = os.path.join(THUMBNAIL_CACHE_DIR, f"{file_hash}.jpeg")

        try:
            cap = cv2.VideoCapture(filepath)
            if cap.isOpened():
                success, frame = cap.read()
                cap.release()
                if success:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame_rgb)
                    img.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 2), Image.Resampling.LANCZOS)
                    img.save(cache_path, 'JPEG', quality=80)
                    return cache_path
        except (OSError, cv2.error) as e:
            logger.debug("cv2 thumbnail failed for %s, trying ffmpeg: %s", os.path.basename(filepath), e)

        if state.FFPROBE_EXECUTABLE_PATH:
            try:
                ffmpeg_bin = _get_ffmpeg_path()
                cmd = [
                    ffmpeg_bin, '-y',
                    '-i', filepath,
                    '-ss', '00:00:00',
                    '-vframes', '1',
                    '-vf', f'scale={THUMBNAIL_WIDTH}:-1',
                    '-q:v', '2',
                    cache_path
                ]

                creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
                               timeout=30, creationflags=creation_flags)

                if os.path.exists(cache_path):
                    return cache_path
            except Exception as e:
                print(f"ERROR (FFmpeg): Thumbnail failed for {os.path.basename(filepath)}: {e}")

    return None


def extract_workflow_files_string(workflow_json_string):
    """
    Parses workflow and returns a normalized string containing ONLY filenames
    (models, images, videos) used in the workflow.
    """
    if not workflow_json_string: return ""

    try:
        data = json.loads(workflow_json_string)
    except (json.JSONDecodeError, ValueError):
        return ""

    nodes = []
    if isinstance(data, dict):
        if 'nodes' in data and isinstance(data['nodes'], list):
            nodes = data['nodes']
        else:
            nodes = list(data.values())
    elif isinstance(data, list):
        nodes = data

    ignored_types = {'Note', 'NotePrimitive', 'Reroute', 'PrimitiveNode'}

    valid_extensions = {
        '.safetensors', '.ckpt', '.pt', '.pth', '.bin', '.gguf', '.lora', '.sft',
        '.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tiff',
        '.mp4', '.mov', '.webm', '.mkv', '.avi', '.mp3', '.wav', '.ogg', '.flac', '.m4a'
    }

    found_tokens = set()

    for node in nodes:
        if not isinstance(node, dict): continue

        node_type = node.get('type', node.get('class_type', ''))

        if node_type in ignored_types:
            continue

        values_to_check = []

        w_vals = node.get('widgets_values')
        if isinstance(w_vals, list):
            values_to_check.extend(w_vals)

        inputs = node.get('inputs')
        if isinstance(inputs, dict):
            values_to_check.extend(inputs.values())
        elif isinstance(inputs, list):
            values_to_check.extend(inputs)

        for val in values_to_check:
            if isinstance(val, str) and val.strip():
                norm_val = normalize_smart_path(val.strip())

                has_valid_ext = any(norm_val.endswith(ext) for ext in valid_extensions)

                is_abs_path = (len(norm_val) < 260) and (
                    (len(norm_val) > 2 and norm_val[1] == ':') or
                    norm_val.startswith('/')
                )

                if has_valid_ext or is_abs_path:
                    found_tokens.add(norm_val)

    return " ||| ".join(sorted(list(found_tokens)))


def extract_workflow_prompt_string(workflow_json_string):
    """
    Broad extraction for Database Indexing (Searchable Keywords).
    Scans ALL nodes while filtering out known UI noise.
    """
    if not workflow_json_string: return ""

    try:
        data = json.loads(workflow_json_string)
    except (json.JSONDecodeError, ValueError):
        return ""

    nodes = []
    if isinstance(data, dict):
        if 'nodes' in data and isinstance(data['nodes'], list):
            nodes = data['nodes']
        else:
            nodes = list(data.values())
    elif isinstance(data, list):
        nodes = data

    found_texts = set()

    ignored_types = {
        'Note', 'NotePrimitive', 'Reroute', 'PrimitiveNode',
        'ShowText', 'Display Text', 'Simple Text', 'Text Box', 'ComfyUI', 'ExtraMetadata',
        'SaveImage', 'PreviewImage', 'VHS_VideoCombine', 'VHS_LoadVideo'
    }

    for node in nodes:
        if not isinstance(node, dict): continue
        node_type = node.get('type', node.get('class_type', '')).strip()

        if node_type in ignored_types: continue

        values_to_check = []
        if 'widgets_values' in node and isinstance(node['widgets_values'], list):
            values_to_check.extend(node['widgets_values'])
        if 'inputs' in node and isinstance(node['inputs'], dict):
            values_to_check.extend(node['inputs'].values())

        for val in values_to_check:
            if isinstance(val, str) and val.strip():
                text = val.strip()

                if text in WORKFLOW_PROMPT_BLACKLIST: continue
                if _is_garbage_text(text): continue
                if text.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.safetensors', '.ckpt', '.pt')):
                    continue
                if len(text) < 3: continue

                found_texts.add(text)

    return " , ".join(list(found_texts))


def process_single_file(filepath):
    """
    Worker function to perform all heavy processing for a single file.
    Designed to be run in a parallel process pool.
    """
    try:
        mtime = os.path.getmtime(filepath)
        metadata = analyze_file_metadata(filepath)
        file_hash_for_thumbnail = hashlib.md5((filepath + str(mtime)).encode()).hexdigest()

        if not glob_module.glob(os.path.join(THUMBNAIL_CACHE_DIR, f"{file_hash_for_thumbnail}.*")):
            create_thumbnail(filepath, file_hash_for_thumbnail, metadata['type'])

        file_id = hashlib.md5(filepath.encode()).hexdigest()
        file_size = os.path.getsize(filepath)

        workflow_files_content = ""
        workflow_prompt_content = ""
        civitai_resources_content = ""

        # Priority 1: gallery_metadata JSON chunk (our Image Saver fork)
        gallery_meta = extract_gallery_metadata(filepath)
        if gallery_meta:
            positive = gallery_meta.get('positive', '')
            if positive and len(positive) > 5:
                workflow_prompt_content = positive

            # Merge CivitAI resources from top-level + per-LoRA civitai data
            all_civitai = list(gallery_meta.get('civitai_resources', []))
            for lora in gallery_meta.get('loras', []):
                civitai_data = lora.get('civitai')
                if civitai_data:
                    # Add weight from the LoRA itself
                    resource = dict(civitai_data)
                    if 'weight' not in resource and lora.get('weight') is not None:
                        resource['weight'] = lora['weight']
                    all_civitai.append(resource)
            if all_civitai:
                civitai_resources_content = json.dumps(all_civitai)

        # Priority 2: A1111/CivitAI parameters chunk (legacy, downloaded images)
        if not workflow_prompt_content:
            params_raw = extract_parameters_chunk(filepath)
            if params_raw:
                parsed_params = parse_a1111_parameters(params_raw)
                if parsed_params.get('positive_prompt') and len(parsed_params['positive_prompt']) > 5:
                    workflow_prompt_content = parsed_params['positive_prompt']
                    civitai_resources_content = parsed_params.get('civitai_resources', '')

        # Fall back to workflow graph scanning for prompt/files
        if metadata['has_workflow']:
            wf_json = extract_workflow(filepath, target_type='api')

            if wf_json:
                workflow_files_content = extract_workflow_files_string(wf_json)
                # Only use workflow scan for prompt if parameters chunk didn't provide one
                if not workflow_prompt_content:
                    workflow_prompt_content = extract_workflow_prompt_string(wf_json)

        return (
            file_id, filepath, mtime, os.path.basename(filepath),
            metadata['type'], metadata['duration'], metadata['dimensions'],
            metadata['has_workflow'], file_size, time.time(),
            workflow_files_content,
            workflow_prompt_content,
            civitai_resources_content
        )
    except Exception as e:
        print(f"ERROR: Failed to process file {os.path.basename(filepath)} in worker: {e}")
        return None
