# Smart Gallery for ComfyUI - Mutable Global State
# Centralized location for all mutable state shared across modules.

# Gallery view cache (list of file dicts for current view)
# Single-value cache: replaced wholesale on each folder navigation, not a growing cache.
gallery_view_cache = []

# Folder configuration cache (dict of folder_key -> folder_info)
# Single-value cache: replaced on force_refresh or folder mutations, not a growing cache.
folder_config_cache = None

# FFprobe executable path (set during initialization)
FFPROBE_EXECUTABLE_PATH = None

# Update check results
UPDATE_AVAILABLE = False
REMOTE_VERSION = None

# Background job tracking
rescan_jobs = {}
zip_jobs = {}
