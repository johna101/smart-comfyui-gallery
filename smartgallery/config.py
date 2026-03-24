# Smart Gallery for ComfyUI - Configuration Module
# All environment variable parsing, constants, and derived settings.

import os
import sys
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
# USER CONFIGURATION
# ============================================================================

BASE_OUTPUT_PATH = os.environ.get('BASE_OUTPUT_PATH', '/Volumes/Titan/Files/comfyui-images/arch-comfyui-output-2025-01-16')
BASE_INPUT_PATH = os.environ.get('BASE_INPUT_PATH', '/Volumes/Titan/Files/comfyui-images')
BASE_SMARTGALLERY_PATH = os.environ.get('BASE_SMARTGALLERY_PATH', BASE_OUTPUT_PATH)
FFPROBE_MANUAL_PATH = os.environ.get('FFPROBE_MANUAL_PATH', "/opt/homebrew/bin/ffprobe")
SERVER_PORT = int(os.environ.get('SERVER_PORT', 8189))
THUMBNAIL_WIDTH = int(os.environ.get('THUMBNAIL_WIDTH', 300))
WEBP_ANIMATED_FPS = float(os.environ.get('WEBP_ANIMATED_FPS', 16.0))
PAGE_SIZE = int(os.environ.get('PAGE_SIZE', 100))
SPECIAL_FOLDERS = ['video', 'audio']
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', 500))
STREAM_THRESHOLD_MB = int(os.environ.get('STREAM_THRESHOLD_MB', 20))
STREAM_THRESHOLD_BYTES = STREAM_THRESHOLD_MB * 1024 * 1024
MAX_PARALLEL_WORKERS = os.environ.get('MAX_PARALLEL_WORKERS', None)
if MAX_PARALLEL_WORKERS is not None and MAX_PARALLEL_WORKERS != "":
    MAX_PARALLEL_WORKERS = int(MAX_PARALLEL_WORKERS)
else:
    MAX_PARALLEL_WORKERS = None
SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))
MAX_PREFIX_DROPDOWN_ITEMS = 100

# --- DELETE / TRASH CONFIG ---
DELETE_TO = os.environ.get('DELETE_TO', None)
TRASH_FOLDER = None

if DELETE_TO and DELETE_TO.strip():
    DELETE_TO = DELETE_TO.strip()
    TRASH_FOLDER = os.path.join(DELETE_TO, 'SmartGallery')

    if not os.path.exists(DELETE_TO):
        print(f"{Colors.RED}{Colors.BOLD}CRITICAL ERROR: DELETE_TO path does not exist: {DELETE_TO}{Colors.RESET}")
        print(f"{Colors.RED}Please create the directory or unset the DELETE_TO environment variable.{Colors.RESET}")
        sys.exit(1)

    if not os.access(DELETE_TO, os.W_OK):
        print(f"{Colors.RED}{Colors.BOLD}CRITICAL ERROR: DELETE_TO path is not writable: {DELETE_TO}{Colors.RESET}")
        print(f"{Colors.RED}Please check permissions or unset the DELETE_TO environment variable.{Colors.RESET}")
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
ENABLE_AI_SEARCH = os.environ.get('ENABLE_AI_SEARCH', 'false').lower() == 'true'

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
DB_SCHEMA_VERSION = 27
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


def print_configuration():
    """Prints the current configuration in a neat, aligned table."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}--- CURRENT CONFIGURATION ---{Colors.RESET}")

    def print_row(key, value, is_path=False):
        color = Colors.CYAN if is_path else Colors.GREEN
        print(f" {Colors.BOLD}{key:<25}{Colors.RESET} : {color}{value}{Colors.RESET}")

    print_row("Server Port", SERVER_PORT)
    print_row("Output Path", BASE_OUTPUT_PATH, True)
    print_row("Input Path", BASE_INPUT_PATH, True)
    print_row("Data Path", BASE_SMARTGALLERY_PATH, True)
    print_row("FFprobe", FFPROBE_MANUAL_PATH if FFPROBE_MANUAL_PATH else "auto-detect", True)
    print_row("Delete Mode", DELETE_TO if DELETE_TO else "Permanent Delete")
    print_row("Thumbnail Width", f"{THUMBNAIL_WIDTH}px")
    print_row("Video Streaming", f"Files > {STREAM_THRESHOLD_MB} MB use range requests")
    if ENABLE_AI_SEARCH:
        print_row("AI Search", "Enabled")
    print(f"{Colors.HEADER}-----------------------------{Colors.RESET}\n")
