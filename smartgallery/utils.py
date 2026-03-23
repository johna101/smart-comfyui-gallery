# Smart Gallery for ComfyUI - Utility Functions
# Path helpers, node analysis, text cleaning, and general utilities.

import os
import re
import json
import colorsys
from typing import Dict, Any

from smartgallery.config import (
    BASE_INPUT_PATH, NODE_CATEGORIES, NODE_CATEGORIES_ORDER, NODE_PARAM_NAMES
)

# --- Cache for node colors ---
_node_colors_cache = {}


def get_standardized_path(filepath):
    """
    Converts path to absolute, forces forward slashes, and handles case sensitivity for Windows.
    Used ONLY for AI Queue uniqueness to prevent loops on mixed-path systems.
    """
    if not filepath: return ""
    try:
        abs_path = os.path.abspath(filepath)
        std_path = abs_path.replace('\\', '/')
        if os.name == 'nt':
            return std_path.lower()
        return std_path
    except:
        return str(filepath)


def normalize_smart_path(path_str):
    """
    Normalizes a path string for search comparison:
    1. Converts to lowercase.
    2. Replaces all backslashes with forward slashes.
    """
    if not path_str: return ""
    return str(path_str).lower().replace('\\', '/')


def get_node_color(node_type):
    """Generates a unique and consistent color for a node type."""
    if node_type not in _node_colors_cache:
        hue = (hash(node_type + "a_salt_string") % 360) / 360.0
        rgb = [int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.7, 0.85)]
        _node_colors_cache[node_type] = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
    return _node_colors_cache[node_type]


def filter_enabled_nodes(workflow_data):
    """Filters and returns only active nodes and links (mode=0) from a workflow."""
    if not isinstance(workflow_data, dict): return {'nodes': [], 'links': []}

    active_nodes = [n for n in workflow_data.get("nodes", []) if n.get("mode", 0) == 0]
    active_node_ids = {str(n["id"]) for n in active_nodes}

    active_links = [
        l for l in workflow_data.get("links", [])
        if str(l[1]) in active_node_ids and str(l[3]) in active_node_ids
    ]
    return {"nodes": active_nodes, "links": active_links}


def generate_node_summary(workflow_json_string):
    """
    Analyzes a workflow JSON, extracts active nodes, and identifies input media.
    Robust version: handles ComfyUI specific suffixes like ' [output]'.
    """
    try:
        workflow_data = json.loads(workflow_json_string)
    except json.JSONDecodeError:
        return None

    nodes = []
    is_api_format = False

    if 'nodes' in workflow_data and isinstance(workflow_data['nodes'], list):
        active_workflow = filter_enabled_nodes(workflow_data)
        nodes = active_workflow.get('nodes', [])
    else:
        is_api_format = True
        for node_id, node_data in workflow_data.items():
            if isinstance(node_data, dict) and 'class_type' in node_data:
                node_entry = node_data.copy()
                node_entry['id'] = node_id
                node_entry['type'] = node_data['class_type']
                node_entry['inputs'] = node_data.get('inputs', {})
                nodes.append(node_entry)

    if not nodes:
        return []

    def get_id_safe(n):
        try: return int(n.get('id', 0))
        except: return str(n.get('id', 0))

    sorted_nodes = sorted(nodes, key=lambda n: (
        NODE_CATEGORIES_ORDER.index(NODE_CATEGORIES.get(n.get('type'), 'others')),
        get_id_safe(n)
    ))

    summary_list = []

    valid_media_exts = {
        '.png', '.jpg', '.jpeg', '.webp', '.gif', '.jfif', '.bmp', '.tiff',
        '.mp4', '.mov', '.webm', '.mkv', '.avi',
        '.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac'
    }

    base_input_norm = os.path.normpath(BASE_INPUT_PATH)

    for node in sorted_nodes:
        node_type = node.get('type', 'Unknown')
        params_list = []

        raw_params = {}
        if is_api_format:
            raw_params = node.get('inputs', {})
        else:
            widgets_values = node.get('widgets_values', [])
            param_names_list = NODE_PARAM_NAMES.get(node_type, [])
            for i, value in enumerate(widgets_values):
                name = param_names_list[i] if i < len(param_names_list) else f"param_{i+1}"
                raw_params[name] = value

        for name, value in raw_params.items():
            display_value = value
            is_input_file = False
            input_url = None

            if isinstance(value, list):
                if len(value) == 2 and isinstance(value[0], str):
                    display_value = f"(Link to {value[0]})"
                else:
                    display_value = str(value)

            if isinstance(value, str) and value.strip():
                clean_value = value.replace('\\', '/').strip()
                clean_value = re.sub(r'\s*\[.*?\]$', '', clean_value)

                _, ext = os.path.splitext(clean_value)

                if ext.lower() in valid_media_exts:
                    filename_only = os.path.basename(clean_value)

                    candidates = [
                        os.path.join(BASE_INPUT_PATH, clean_value),
                        os.path.join(BASE_INPUT_PATH, filename_only),
                        os.path.normpath(os.path.join(BASE_INPUT_PATH, clean_value))
                    ]

                    for candidate_path in candidates:
                        try:
                            if os.path.isfile(candidate_path):
                                abs_candidate = os.path.abspath(candidate_path)
                                abs_base = os.path.abspath(BASE_INPUT_PATH)

                                if abs_candidate.startswith(abs_base):
                                    is_input_file = True
                                    rel_path = os.path.relpath(abs_candidate, abs_base).replace('\\', '/')
                                    input_url = f"/galleryout/input_file/{rel_path}"
                                    display_value = clean_value
                                    break
                        except Exception:
                            continue

            params_list.append({
                "name": name,
                "value": display_value,
                "is_input_file": is_input_file,
                "input_url": input_url
            })

        summary_list.append({
            "id": node.get('id', 'N/A'),
            "type": node_type,
            "category": NODE_CATEGORIES.get(node_type, 'others'),
            "color": get_node_color(node_type),
            "params": params_list
        })

    return summary_list


# --- Regex Patterns for Prompt Parsing ---
RE_LORA_PROMPT = re.compile(r"<lora:([\w_\s.-]+)(?::([\d.]+))*>", re.IGNORECASE)
RE_LYCO_PROMPT = re.compile(r"<lyco:([\w_\s.]+):([\d.]+)>", re.IGNORECASE)
RE_PARENS = re.compile(r"[\\/\[\](){}]+")
RE_LORA_CLOSE = re.compile(r">\s+")


def clean_prompt_text(x: str) -> Dict[str, Any]:
    """
    Cleans a raw prompt string: removes LoRA tags, normalizes whitespace,
    and extracts LoRA usage into a separate list.
    """
    if not x:
        return {"text": "", "loras": []}

    x = re.sub(r'\sBREAK\s', ' , BREAK , ', x)
    x = re.sub(RE_LORA_CLOSE, "> , ", x)
    x = x.replace("，", ",").replace("-", " ").replace("_", " ")

    clean_text = re.sub(RE_PARENS, "", x)

    tag_list = [t.strip() for t in x.split(",")]
    lora_list = []
    final_tags = []

    for tag in tag_list:
        if not tag: continue

        lora_match = re.search(RE_LORA_PROMPT, tag)
        lyco_match = re.search(RE_LYCO_PROMPT, tag)

        if lora_match:
            val = float(lora_match.group(2)) if lora_match.group(2) else 1.0
            lora_list.append({"name": lora_match.group(1), "value": val})
        elif lyco_match:
            lora_list.append({"name": lyco_match.group(1), "value": float(lyco_match.group(2))})
        else:
            clean_tag = re.sub(RE_PARENS, "", tag).strip()
            if clean_tag:
                final_tags.append(clean_tag)

    return {
        "text": ", ".join(final_tags),
        "loras": lora_list
    }


def format_duration(seconds):
    if not seconds or seconds < 0: return ""
    m, s = divmod(int(seconds), 60); h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def _is_garbage_text(text):
    """Helper to filter out garbage text (Markdown, Stats, Instructions, UI values)."""
    if not text: return True
    t = text.strip()
    if len(t) < 3: return True

    if '|' in t and ('---' in t or 'VRAM' in t or 'Model' in t): return True
    if 'GPU:' in t or 'RTX' in t or 'it/s' in t: return True

    t_lower = t.lower()

    GARBAGE_MARKERS = (
        "ctrl +", "box-select", "don't forget to use", "partial - execution",
        "creative prompt", "bad quality", "embedding:", "🟢", "select wildcard",
        "by percentage", "what is art?", "send none", "you are an ai artist",
        "jpeg压缩残留", "/", "select the wildcard"
    )

    if any(marker in t_lower for marker in GARBAGE_MARKERS):
        return True

    if "http://" in t_lower or "https://" in t_lower: return True

    if len(t) > 3 and t[0].isdigit() and t[1] == '.' and t[2] == ' ': return True

    ui_keywords = {
        'enable', 'disable', 'fixed', 'randomize', 'auto', 'simple', 'always',
        'center', 'left', 'top', 'bottom', 'right', 'nearest', 'bilinear',
        'bicubic', 'lanczos', 'keep proportion', 'image', 'default', 'comfyui',
        'wan', 'crop', 'input', 'output', 'float', 'int', 'boolean',
        'euler', 'euler_a', 'heun', 'dpm_2', 'dpmpp_2m', 'dpmpp_sde', 'ddim',
        'uni_pc', 'lms', 'karras', 'exponential', 'sgd', 'normal'
    }

    if t_lower in ui_keywords: return True

    if t.startswith('%') or '${' in t: return True

    return False
