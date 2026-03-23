# Backend Architecture Guide

## Overview

The Python backend was originally a single 4,938-line file (`smartgallery.py`). It's now split into a package (`smartgallery/`) with modules organized by responsibility. The original file is preserved untouched for backward compatibility.

**Entry point:** `python run.py` (replaces `python smartgallery.py`)

## Module Map

```
smartgallery/
├── __init__.py        Flask app factory
├── config.py          All configuration in one place
├── state.py           Mutable runtime state
├── utils.py           Shared helper functions
├── parser.py          ComfyUI workflow graph tracer
├── models.py          Database schema and connections
├── processing.py      File processing pipeline
├── folders.py         Folder tree management and sync
├── startup.py         Server initialization and launch
└── routes/
    ├── __init__.py    Blueprint registry
    ├── gallery.py     Main gallery view and pagination
    ├── files.py       File CRUD (move, copy, delete, rename, favorites)
    ├── folders.py     Folder CRUD (create, mount, unmount, rename, delete)
    ├── media.py       Serving files, thumbnails, storyboards, video streaming
    ├── ai.py          AI search and indexing endpoints (future feature)
    ├── api.py         Search options, file comparison, sync status
    └── batch.py       Background jobs (rescan, zip export)
```

## Modules in Detail

### `config.py` — Configuration

Everything that was hardcoded at the top of the original file. Environment variable parsing, path defaults, constants (thumbnail width, page size, batch size), node categorization tables, and the `Colors` class for terminal output. Also contains `path_to_key()` / `key_to_path()` which convert folder paths to base64 URL-safe keys used throughout the app.

**Why separate:** Config is imported by almost every other module. Having it in one place means you only edit one file when changing defaults (like you did with your local paths).

### `state.py` — Mutable Runtime State

Just a handful of module-level variables that change during runtime:
- `gallery_view_cache` — the current list of files for the gallery view (populated on each page load, consumed by `load_more` for pagination)
- `folder_config_cache` — cached folder tree structure
- `FFPROBE_EXECUTABLE_PATH` — detected at startup
- `UPDATE_AVAILABLE` / `REMOTE_VERSION` — set by update checker
- `rescan_jobs` / `zip_jobs` — background job tracking dicts

**Why separate:** These globals are shared across routes and utility modules. Centralizing them avoids circular imports and makes it obvious what mutable state exists.

### `utils.py` — Shared Helpers

Three categories of functions:

1. **Path normalization** — `get_standardized_path()`, `normalize_smart_path()`. These exist because ComfyUI generates paths with mixed slashes on Windows, and the DB might store `C:/folder\image.png`. Every path comparison needs normalization.

2. **Node analysis** — `generate_node_summary()`, `filter_enabled_nodes()`, `get_node_color()`. These parse a ComfyUI workflow JSON and produce the visual node summary shown in the UI. They categorize nodes (input/model/processing/output) and extract parameter values.

3. **Text cleaning** — `clean_prompt_text()`, `_is_garbage_text()`. ComfyUI workflows contain a lot of noise — UI parameter values, markdown notes, sampler names. These functions filter that out to build a searchable prompt index.

### `parser.py` — ComfyMetadataParser

The most interesting code in the project. ComfyUI workflows are directed graphs where nodes are connected by typed links. To extract "what seed was used?" you can't just look at the KSampler node — the seed value might be linked from a separate PrimitiveNode, which itself might be linked from another node.

`ComfyMetadataParser` traces these links recursively:
- Finds the KSampler node
- Follows the `positive`/`negative` links to find prompt text
- Follows the `model` link to find the checkpoint name
- Follows the `latent_image` link to find dimensions
- Resolves linked values recursively via `_get_real_value()`
- Falls back to scanning all nodes if tracing misses data

Supports both "UI format" (has `nodes` array with visual positions) and "API format" (dict of node_id → node_data with `class_type`).

### `models.py` — Database

SQLite with WAL mode for concurrent reads. Single table `files` stores the metadata cache. Several AI-related tables exist for a future feature. Schema migrations are handled by checking column existence and adding missing ones — simple but effective.

**Key point:** The database is a cache, not the source of truth. The filesystem is authoritative. Every sync operation compares disk state to DB state and reconciles.

### `processing.py` — File Pipeline

The heavy lifting module. When a new file is discovered:

1. `analyze_file_metadata()` — determines type (image/video/animated), extracts dimensions via Pillow or OpenCV, checks for embedded workflow
2. `create_thumbnail()` — generates a cached thumbnail (handles static images, animated GIF/WebP, and video first-frame extraction via OpenCV or FFmpeg)
3. `extract_workflow()` — pulls workflow JSON from PNG metadata, JPEG EXIF, or MP4 tags. Falls back to raw byte scanning for edge cases
4. `extract_workflow_files_string()` / `extract_workflow_prompt_string()` — index the workflow content for search

`process_single_file()` orchestrates all of the above and returns a tuple ready for DB insertion. It's designed to run in a `ProcessPoolExecutor` for parallel processing.

### `folders.py` — Folder Management

Manages the folder tree that appears in the sidebar:

- `get_dynamic_folder_config()` — walks `BASE_OUTPUT_PATH`, builds a dict of folder_key → folder_info (display name, path, parent, children, mount status, AI watch status). Cached and refreshed on demand.
- `full_sync_database()` — compares every file on disk to the DB, processes new/modified files in parallel, removes orphaned records. Has a safety guard that skips deletion for files on disconnected drives.
- `sync_folder_on_demand()` — SSE generator that streams sync progress to the browser.
- `initialize_gallery()` — startup sequence: find FFprobe, create cache dirs, init DB, run full sync.

### `startup.py` — Server Launch

The `run_app()` function is the main entry point. Prints the banner, checks for updates against GitHub, validates paths, initializes the gallery, starts the AI background watcher thread if enabled, then runs Flask.

### Routes

All routes use Flask Blueprints with the `/galleryout` prefix. They're organized by the resource they operate on:

- **gallery.py** — The main view (`/view/<folder_key>`) is the most complex route. It handles filtering (search, date range, extension, prefix, favorites, workflow), sorting, recursive mode, global search, and AI search results. Builds the full file list and passes it to the template.
- **files.py** — CRUD operations on files. Move/copy handle path uniqueness (auto-rename conflicts), preserve metadata including AI data, and update DB IDs (which are MD5 hashes of the file path).
- **folders.py** (routes) — Folder operations. Mount/unmount creates symlinks/junctions to external folders. The filesystem browser endpoint lets users pick folders via the UI.
- **media.py** — Serves files, thumbnails, and storyboard frames. The storyboard extraction is complex — it handles corruption detection, optional transcoding, and parallel frame extraction. Video streaming transcodes on-the-fly via FFmpeg.
- **batch.py** — Background jobs using threads. Rescan reprocesses files in a folder. Zip export creates downloadable archives. Both use polling endpoints for progress tracking.
- **ai.py** — Endpoints for a future AI search feature (queue management, indexing, watched folders). Currently disabled by default.
- **api.py** — Search filter options, file comparison (diffs two workflows side by side), and SSE sync status.
