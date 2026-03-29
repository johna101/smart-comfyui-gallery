# Smart Gallery for ComfyUI - Configuration Module
# Settings resolution: env vars > settings.json > smart defaults.

import os
import sys
import json
import secrets
import base64

# --- CONSOLE STYLING ---
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'


# ============================================================================
# SETTINGS.JSON LOADER
# ============================================================================

def _load_settings():
    """Load settings from SMART_GALLERY_ROOT/settings.json if it exists."""
    root = os.environ.get('SMART_GALLERY_ROOT', os.getcwd())
    settings_path = os.path.join(root, 'settings.json')
    settings = {}
    if os.path.isfile(settings_path):
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
        except json.JSONDecodeError as e:
            print(f"{Colors.RED}{Colors.BOLD}ERROR: Failed to parse {settings_path}: {e}{Colors.RESET}")
            sys.exit(1)
        except OSError as e:
            print(f"{Colors.RED}{Colors.BOLD}ERROR: Cannot read {settings_path}: {e}{Colors.RESET}")
            sys.exit(1)
    return root, settings, settings_path

SMART_GALLERY_ROOT, _settings, _settings_path = _load_settings()

# Track where each config value came from (for print_configuration)
_config_sources = {}


def _resolve(env_name, json_key, default, cast=str):
    """Three-tier config resolution: env var > settings.json > default."""
    env_val = os.environ.get(env_name)
    if env_val is not None and env_val != '':
        _config_sources[env_name] = 'env'
        return cast(env_val)
    if json_key and json_key in _settings:
        _config_sources[env_name] = 'settings.json'
        val = _settings[json_key]
        # JSON values are already typed (bool, int, etc.) — only cast strings
        if isinstance(val, str) or not isinstance(val, type(default if default is not None else '')):
            return cast(val)
        return val
    _config_sources[env_name] = 'default'
    if default is None:
        return None
    return cast(default) if isinstance(default, str) else default


def _bool_cast(v):
    """Handle both string 'true'/'false' (env) and native bool (JSON)."""
    if isinstance(v, bool):
        return v
    return str(v).lower() == 'true'


def _optional_int(v):
    """Handle None-or-int values like MAX_PARALLEL_WORKERS."""
    if v is None or v == '' or v == 'null':
        return None
    return int(v)


# ============================================================================
# USER CONFIGURATION — resolved from env > settings.json > defaults
# ============================================================================

# Base ComfyUI path — specific paths derive from this unless explicitly overridden
COMFYUI_PATH = _resolve('COMFYUI_PATH', 'comfyui_path', None)

# Specific paths: explicit setting > derived from COMFYUI_PATH > None
_default_output = os.path.join(COMFYUI_PATH, 'output') if COMFYUI_PATH else None
_default_input = os.path.join(COMFYUI_PATH, 'input') if COMFYUI_PATH else None
_default_workflows = os.path.join(COMFYUI_PATH, 'user', 'default', 'workflows') if COMFYUI_PATH else None

BASE_OUTPUT_PATH = _resolve('BASE_OUTPUT_PATH', 'comfyui_output_path', _default_output)
BASE_INPUT_PATH = _resolve('BASE_INPUT_PATH', 'comfyui_input_path', _default_input)
COMFYUI_WORKFLOWS_PATH = _resolve('COMFYUI_WORKFLOWS_PATH', 'comfyui_workflows_path', _default_workflows)

# Data path defaults to SMART_GALLERY_ROOT/data (not inside ComfyUI output)
_default_data_path = os.path.join(SMART_GALLERY_ROOT, 'data')
BASE_SMARTGALLERY_PATH = _resolve('BASE_SMARTGALLERY_PATH', 'data_path', _default_data_path)

FFPROBE_MANUAL_PATH = _resolve('FFPROBE_MANUAL_PATH', 'ffprobe_path', None)
if FFPROBE_MANUAL_PATH == 'auto':
    FFPROBE_MANUAL_PATH = None

SERVER_HOST = _resolve('SERVER_HOST', 'server_host', '0.0.0.0')
SERVER_PORT = _resolve('SERVER_PORT', 'server_port', 8189, cast=int)
THUMBNAIL_WIDTH = _resolve('THUMBNAIL_WIDTH', 'thumbnail_width', 300, cast=int)
WEBP_ANIMATED_FPS = _resolve('WEBP_ANIMATED_FPS', 'webp_animated_fps', 16.0, cast=float)
PAGE_SIZE = _resolve('PAGE_SIZE', 'page_size', 100, cast=int)
SPECIAL_FOLDERS = ['video', 'audio']
BATCH_SIZE = _resolve('BATCH_SIZE', 'batch_size', 500, cast=int)
STREAM_THRESHOLD_MB = _resolve('STREAM_THRESHOLD_MB', 'stream_threshold_mb', 20, cast=int)
STREAM_THRESHOLD_BYTES = STREAM_THRESHOLD_MB * 1024 * 1024
MAX_PARALLEL_WORKERS = _resolve('MAX_PARALLEL_WORKERS', 'max_parallel_workers', None, cast=_optional_int)
SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))
MAX_PREFIX_DROPDOWN_ITEMS = 100

# --- DELETE / TRASH CONFIG ---
DELETE_TO = _resolve('DELETE_TO', 'delete_mode', None)
TRASH_FOLDER = None

# "permanent" in settings.json means no trash — same as None
if DELETE_TO and DELETE_TO.strip() and DELETE_TO.strip().lower() != 'permanent':
    DELETE_TO = DELETE_TO.strip()
    TRASH_FOLDER = os.path.join(DELETE_TO, 'SmartGallery')

    if not os.path.exists(DELETE_TO):
        print(f"{Colors.RED}{Colors.BOLD}CRITICAL ERROR: DELETE_TO path does not exist: {DELETE_TO}{Colors.RESET}")
        print(f"{Colors.RED}Please create the directory or remove 'delete_mode' from settings.json.{Colors.RESET}")
        sys.exit(1)

    if not os.access(DELETE_TO, os.W_OK):
        print(f"{Colors.RED}{Colors.BOLD}CRITICAL ERROR: DELETE_TO path is not writable: {DELETE_TO}{Colors.RESET}")
        print(f"{Colors.RED}Please check permissions or remove 'delete_mode' from settings.json.{Colors.RESET}")
        sys.exit(1)

    if not os.path.exists(TRASH_FOLDER):
        try:
            os.makedirs(TRASH_FOLDER)
            print(f"{Colors.GREEN}Created trash folder: {TRASH_FOLDER}{Colors.RESET}")
        except OSError as e:
            print(f"{Colors.RED}{Colors.BOLD}CRITICAL ERROR: Cannot create trash folder: {TRASH_FOLDER}{Colors.RESET}")
            print(f"{Colors.RED}Error: {e}{Colors.RESET}")
            sys.exit(1)
else:
    DELETE_TO = None
    TRASH_FOLDER = None

# --- WORKFLOW PROMPT EXTRACTION SETTINGS ---
WORKFLOW_PROMPT_BLACKLIST = {
    "The white dragon warrior stands still, eyes full of determination and strength. The camera slowly moves closer or circles around the warrior, highlighting the powerful presence and heroic spirit of the character.",
    "undefined",
    "null",
    "None"
}

# --- AI SEARCH CONFIGURATION ---
ENABLE_AI_SEARCH = _resolve('ENABLE_AI_SEARCH', 'enable_ai_search', False, cast=_bool_cast)

# --- CACHE AND FOLDER NAMES ---
THUMBNAIL_CACHE_FOLDER_NAME = '.thumbnails_cache'
SQLITE_CACHE_FOLDER_NAME = '.sqlite_cache'
DATABASE_FILENAME = 'gallery_cache.sqlite'
ZIP_CACHE_FOLDER_NAME = '.zip_downloads'
AI_MODELS_FOLDER_NAME = '.AImodels'

# --- APP INFO ---
APP_VERSION = "1.55"
APP_VERSION_DATE = "Febraury 5, 2026"
GITHUB_REPO_URL = "https://github.com/biagiomaf/smart-comfyui-gallery"
GITHUB_RAW_URL = "https://raw.githubusercontent.com/biagiomaf/smart-comfyui-gallery/main/smartgallery.py"

# --- HELPER FUNCTIONS ---
def path_to_key(relative_path):
    if not relative_path: return '_root_'
    return base64.urlsafe_b64encode(relative_path.replace(os.sep, '/').encode()).decode()

def key_to_path(key):
    if key == '_root_': return ''
    try:
        return base64.urlsafe_b64decode(key.encode()).decode().replace('/', os.sep)
    except Exception: return None

# --- DERIVED SETTINGS ---
DB_SCHEMA_VERSION = 28
THUMBNAIL_CACHE_DIR = os.path.join(BASE_SMARTGALLERY_PATH, THUMBNAIL_CACHE_FOLDER_NAME)
SQLITE_CACHE_DIR = os.path.join(BASE_SMARTGALLERY_PATH, SQLITE_CACHE_FOLDER_NAME)
DATABASE_FILE = os.path.join(SQLITE_CACHE_DIR, DATABASE_FILENAME)
ZIP_CACHE_DIR = os.path.join(BASE_SMARTGALLERY_PATH, ZIP_CACHE_FOLDER_NAME)
PROTECTED_FOLDER_KEYS = {path_to_key(f) for f in SPECIAL_FOLDERS}
PROTECTED_FOLDER_KEYS.add('_root_')

# --- NODE CATEGORIZATION ---
NODE_CATEGORIES_ORDER = ["input", "model", "processing", "output", "others"]
NODE_CATEGORIES = {
    "Load Checkpoint": "input", "CheckpointLoaderSimple": "input", "Empty Latent Image": "input",
    "CLIPTextEncode": "input", "Load Image": "input",
    "ModelMerger": "model",
    "KSampler": "processing", "KSamplerAdvanced": "processing", "VAEDecode": "processing",
    "VAEEncode": "processing", "LatentUpscale": "processing", "ConditioningCombine": "processing",
    "PreviewImage": "output", "SaveImage": "output",
    "LoadImageOutput": "input"
}
NODE_PARAM_NAMES = {
    "CLIPTextEncode": ["text"],
    "KSampler": ["seed", "control_after_generate", "steps", "cfg", "sampler_name", "scheduler", "denoise"],
    "KSamplerAdvanced": ["add_noise", "noise_seed", "control_after_generate", "steps", "cfg", "sampler_name", "scheduler", "start_at_step", "end_at_step", "return_with_leftover_noise"],
    "Load Checkpoint": ["ckpt_name"],
    "CheckpointLoaderSimple": ["ckpt_name"],
    "Empty Latent Image": ["width", "height", "batch_size"],
    "LatentUpscale": ["upscale_method", "width", "height"],
    "SaveImage": ["filename_prefix"],
    "ModelMerger": ["ckpt_name1", "ckpt_name2", "ratio"],
    "Load Image": ["image"],
    "LoadImageMask": ["image"],
    "VHS_LoadVideo": ["video"],
    "LoadAudio": ["audio"],
    "AudioLoader": ["audio"],
    "LoadImageOutput": ["image"]
}


# ============================================================================
# CONFIGURATION DISPLAY
# ============================================================================

def _check_path_status(path):
    """Check if a path exists and is accessible. Returns (ok, detail)."""
    if not path:
        return False, "not configured"
    if not os.path.exists(path):
        return False, "NOT FOUND"
    if os.path.isdir(path) and not os.access(path, os.R_OK):
        return False, "no read permission"
    if os.path.isfile(path) and not os.access(path, os.X_OK):
        return False, "not executable"
    return True, None


def _check_ffprobe_status(path):
    """Check if ffprobe path is valid and executable."""
    if not path:
        return True, "auto-detect"  # Will be resolved later during init
    if not os.path.isfile(path):
        return False, "NOT FOUND"
    if not os.access(path, os.X_OK):
        return False, "not executable"
    return True, None


def _source_tag(env_name):
    """Format the source of a config value for display."""
    src = _config_sources.get(env_name, '')
    if src == 'env':
        return f" {Colors.DIM}(env){Colors.RESET}"
    elif src == 'settings.json':
        return f" {Colors.DIM}(settings.json){Colors.RESET}"
    return ""


def print_configuration():
    """Prints the current configuration in a neat, aligned table with status checks."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}--- CURRENT CONFIGURATION ---{Colors.RESET}")

    OK = f"{Colors.GREEN}✓{Colors.RESET}"
    FAIL = f"{Colors.RED}✗{Colors.RESET}"

    def print_row(key, value, is_path=False, status=None, env_name=None):
        color = Colors.CYAN if is_path else Colors.GREEN
        status_str = ""
        if status is not None:
            ok, detail = status
            if ok:
                status_str = f"  {OK}"
            else:
                status_str = f"  {FAIL} {Colors.RED}{detail}{Colors.RESET}"
        src = _source_tag(env_name) if env_name else ""
        print(f" {Colors.BOLD}{key:<25}{Colors.RESET} : {color}{value}{Colors.RESET}{status_str}{src}")

    # Show settings file status
    if os.path.isfile(_settings_path):
        print_row("Settings File", _settings_path, True, (True, None))
    else:
        print_row("Settings File", _settings_path, True, (False, "NOT FOUND"))

    print_row("Server Port", SERVER_PORT, env_name='SERVER_PORT')
    if COMFYUI_PATH:
        print_row("ComfyUI Path", COMFYUI_PATH, True,
                  _check_path_status(COMFYUI_PATH), 'COMFYUI_PATH')
    print_row("Output Path", BASE_OUTPUT_PATH or "(not set)", True,
              _check_path_status(BASE_OUTPUT_PATH), 'BASE_OUTPUT_PATH')
    print_row("Input Path", BASE_INPUT_PATH or "(not set)", True,
              _check_path_status(BASE_INPUT_PATH), 'BASE_INPUT_PATH')
    print_row("Workflows Path", COMFYUI_WORKFLOWS_PATH or "(not set)", True,
              _check_path_status(COMFYUI_WORKFLOWS_PATH), 'COMFYUI_WORKFLOWS_PATH')
    print_row("Data Path", BASE_SMARTGALLERY_PATH, True,
              _check_path_status(BASE_SMARTGALLERY_PATH), 'BASE_SMARTGALLERY_PATH')

    ffprobe_display = FFPROBE_MANUAL_PATH if FFPROBE_MANUAL_PATH else "auto-detect"
    ffprobe_status = _check_ffprobe_status(FFPROBE_MANUAL_PATH)
    print_row("FFprobe", ffprobe_display, True, ffprobe_status, 'FFPROBE_MANUAL_PATH')

    print_row("Delete Mode", DELETE_TO if DELETE_TO else "Permanent Delete",
              env_name='DELETE_TO')
    print_row("Thumbnail Width", f"{THUMBNAIL_WIDTH}px")
    print_row("Video Streaming", f"Files > {STREAM_THRESHOLD_MB} MB use range requests")
    if ENABLE_AI_SEARCH:
        print_row("AI Search", "Enabled")
    print(f"{Colors.HEADER}-----------------------------{Colors.RESET}\n")
