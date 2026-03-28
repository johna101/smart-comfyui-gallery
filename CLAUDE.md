# CLAUDE.md

## Project Overview
SmartGallery for ComfyUI — a local, offline, browser-based gallery for managing ComfyUI-generated images and videos. Preserves workflows, extracts generation metadata, supports search/filter/compare/batch operations.

Forked for personal use and active refactoring. Not intended for upstream contribution.

## Architecture

### Current — Vue 3 SPA with Flask backend
- **Backend:** Python 3.9+ / Flask, modular package (`smartgallery/`)
- **Frontend:** Vue 3 + Vite + Pinia + Vue Router + Tailwind CSS v4 (`frontend/`)
- **Template:** Minimal Jinja2 shell (`templates/index.html`) — just CSS variables, `#vue-app` mount, `__GALLERY_DATA__` injection
- **Database:** SQLite3, schema version 27 with auto-migrations, indexed on path/mtime/name
- **Entry point:** `run.py`
- **Production build:** `cd frontend && npm run build` outputs to `static/dist/`, Flask serves via manifest

### Backend Package (`smartgallery/`)
- `__init__.py` — Flask app factory, registers all blueprints, production asset loader
- `config.py` — all constants, paths, environment variable handling
- `state.py` — mutable runtime state (caches, job trackers, scan/operation flags, watcher refs)
- `watcher.py` — watchdog filesystem observer for real-time external change detection
- `events.py` — EventBus (thread-safe pub/sub), GalleryEvent, SSE push + DB persistence
- `models.py` — database access, `get_db_connection()`, `init_db()` with migrations, thread-local connections
- `parser.py` — `ComfyMetadataParser` class, workflow/prompt JSON extraction
- `processing.py` — file scanning, thumbnail generation, parallel processing pipeline
- `folders.py` — folder management (mount, sync, config, ffprobe detection)
- `utils.py` — shared helpers (path normalization, formatting, Colors class)
- `startup.py` — server initialization, version check, network discovery banner
- `routes/` — Flask Blueprints:
  - `gallery.py` — main view, JSON API for SPA navigation, SQL path filtering, skip_folders optimization
  - `files.py` — file CRUD (move, copy, delete, rename, favourite)
  - `folders.py` — folder CRUD (create, mount, rename, delete, move, browse)
  - `media.py` — serve files, thumbnails, storyboards (incl. hi-res), video streaming with range requests
  - `ai.py` — AI search queue, indexing control (skips macOS `._*` resource forks)
  - `api.py` — search options, compare, sync status, scan status, SSE event stream
  - `batch.py` — rescan, zip preparation/download

### Frontend (`frontend/`)
- **Routing:** Vue Router with `/galleryout/view/:folderKey` — browser back/forward works
- **State:** Pinia stores:
  - `gallery` — files, folders, selection, filtered views, folder-to-key reverse lookup
  - `preferences` — localStorage-backed (focus mode, sidebar, sort, expanded folders)
  - `filters` — client-side filter state (search, extensions, prefixes, dates, favourites)
  - `ui` — lightbox, modals, storyboard state
- **API:** Typed service (`src/api/gallery.ts`) wrapping all 30+ backend endpoints
- **Components:**
  - `lightbox/` — LightboxViewer, LightboxHeader, LightboxMedia + composables (zoom, keyboard, metadata panel)
  - `gallery/` — GalleryGrid, GalleryCard, LazyImage, SelectionBar
  - `sidebar/` — FolderSidebar, FolderTree, FolderContextMenu, FolderMoveDialog
  - `toolbar/` — GalleryToolbar, FilterPanel, RescanProgress
  - `compare/` — ImageCompare (side-by-side + slider wipe mode, metadata diff)
  - `storyboard/` — StoryboardViewer (grid + zoom with HD toggle, keyboard nav, PNG download)
  - `ui/` — FolderPickerDialog (reusable, isolated expand state), ScanOverlay (progress bar during scans)
- **Composables:** useFolderNavigation, useLightboxZoom, useLightboxKeys, useSelection, useThumbnailCache, useEventStream (SSE + scan progress)
- **Tailwind v4:** scoped `<style>` blocks need `@reference "tailwindcss"` for `@apply` to work

### Performance Architecture
- **Two-tier filtering:** Server fetches dataset (scope/recursive), client filters instantly (name, extensions, prefixes, dates, favourites)
- **LazyImage:** IntersectionObserver + 150ms debounce, AbortController cancellation, blob URL cache (2000 entries LRU)
- **SQL optimization:** Path filtering in SQL WHERE (not Python), explicit column lists (no ai_embedding BLOB), indexed columns
- **Thumbnail caching:** HTTP Cache-Control immutable, in-memory path cache, thread-local DB connections
- **Payload optimization:** `skip_folders` param omits 500KB folders map on repeat navigations, folder config cached between mutations

### File Change Detection & Folder Operations
Three layers detect and propagate file/folder changes:

| Source | Detects | Updates DB | Notifies frontend |
|---|---|---|---|
| **Route handlers** (move/rename/delete) | User action | `_rebase_file_records` or direct SQL | `publish_event` → SSE |
| **Watcher** (watchdog/FSEvents) | External changes (ComfyUI output, manual copies) | `process_single_file` + upsert | `publish_event` → SSE |
| **Startup scan** (`full_sync_database`) | Boot-time reconciliation | Chunked `executemany` via `ProcessPoolExecutor` | `scan_progress` → SSE overlay |

**Startup flow** (`startup.py`):
1. `initialize_db()` — fast DB migrations (blocking, before Flask starts)
2. `create_app()` — Flask starts serving immediately with stale DB
3. Background thread: `run_startup_scan()` → `full_sync_database()` with SSE progress
4. Frontend shows `ScanOverlay` until scan completes

**Folder operation coordination** (`routes/folders.py`):
- `_begin_folder_operation()` — stops watcher (observer.stop), cancels pending timers, sets `state.folder_operation_in_progress` flag
- Filesystem op runs first (shutil.move/os.rename) — if it fails, nothing to roll back
- DB paths rewritten via `_rebase_file_records` — if DB fails, next scan reconciles
- `_end_folder_operation()` — restarts watcher immediately, clears flag after 3s timer (absorbs macOS FSEvents replay buffer)
- Startup scan yields to folder ops (pauses DB writes while flag is set)

**Watcher suppression** (`watcher.py`):
- All event handlers check `_suppressed()` (reads `state.folder_operation_in_progress`)
- Debounced callbacks re-check flag at fire time via guarded wrapper
- `cancel_all_timers()` kills pending callbacks when an operation starts
- Restart timer is cancellable — rapid operations don't race

**Critical: Flask debug mode** (`FLASK_DEBUG=true`):
- Werkzeug reloader spawns a child process — both parent and child run `run_app()`
- Background threads (watcher, scan, AI watcher) must only start in the child process
- Check `os.environ.get('WERKZEUG_RUN_MAIN')` — only truthy in the child
- Without this, `state` flags set in child are invisible to parent's watcher (separate memory)

## Dev Setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run.py
```

On first run with no config, the app prints a helpful message and exits. Create a `settings.json` in the working directory:
```json
{
  "comfyui_output_path": "/path/to/comfyui/output",
  "comfyui_input_path": "/path/to/comfyui/input"
}
```

For Vue frontend development (alongside Flask):
```bash
cd frontend
npm install
npm run dev
```
Then set `FLASK_DEBUG=true` — Flask auto-reloads and injects Vite dev server script.

### Production Deployment
```bash
cd frontend && npm install && npm run build
cd .. && python run.py
```
Built assets in `static/dist/` are served via Vite manifest. No Vite dev server needed.

### Configuration System
Config resolution order (highest priority wins):
1. **Environment variables** — for Docker, scripts, CI
2. **settings.json** — primary config method for local use
3. **Smart defaults** — derived from `SMART_GALLERY_ROOT` (env var or CWD)

`settings.json` lives in `SMART_GALLERY_ROOT/settings.json`. The `data/` subdir is auto-created for DB, thumbnails, and caches.

Available settings.json keys:
- `comfyui_output_path` — ComfyUI output folder (required)
- `comfyui_input_path` — ComfyUI input folder (optional)
- `data_path` — cache/DB location (default: `SMART_GALLERY_ROOT/data`)
- `ffprobe_path` — path to ffprobe, or `"auto"` (default: auto-detect)
- `server_host` — default `0.0.0.0`
- `server_port` — default `8189`
- `delete_mode` — trash folder path, or `"permanent"` (default: permanent)
- `thumbnail_width` — default `300`
- `enable_ai_search` — default `false`

### Environment Variables (override settings.json)
- `SMART_GALLERY_ROOT` — root directory for settings.json and data/ (default: CWD)
- `BASE_OUTPUT_PATH` — ComfyUI output folder
- `BASE_INPUT_PATH` — ComfyUI input folder
- `BASE_SMARTGALLERY_PATH` — cache/DB location
- `SERVER_HOST` — default `0.0.0.0` (all interfaces)
- `SERVER_PORT` — default `8189`
- `FLASK_DEBUG` — enables debug mode, auto-reload, Vite dev injection (env-only)

### PyCharm Configuration
- Script path: `run.py`
- Create a `settings.json` in the project root, or set env vars in run configuration
- Debug mode: `FLASK_DEBUG=true` enables auto-reload and Vite dev script injection

FFmpeg/FFprobe required for video support (thumbnails, storyboards, streaming).
Linux: ensure firewall allows SERVER_PORT (e.g., `firewall-cmd --add-port=8189/tcp`).

## Conventions

### Backend (Python)
- snake_case for functions and variables, PascalCase for classes
- All Flask routes prefixed with `/galleryout/`
- Routes use Flask Blueprints — `url_for` needs blueprint prefix (e.g., `gallery.gallery_view`)
- Legacy `url_for` aliases registered in `__init__.py` for template compatibility
- DB access via `get_db_connection()`, schema migrations in `init_db()`
- Mutable globals accessed via `state` module, not Python `global` keyword
- Background tasks use `threading` and `concurrent.futures`
- Backend supports comma-separated extension/prefix params as well as repeated params
- File scanning skips macOS resource fork files (`._*` prefix)

### Frontend (Vue 3)
- Vue 3 Composition API + TypeScript throughout
- Pinia for state management, localStorage for user preferences
- Tailwind CSS v4 with theme mapped to legacy CSS variables
- Async/await throughout, typed API layer
- Composable return values are plain objects — use `.value` when passing refs as props
- Keyboard handlers: always check `e.metaKey || e.ctrlKey || e.altKey` before intercepting single keys
- Modal/overlay keyboard handlers use capture phase (`addEventListener('keydown', fn, true)`) to prevent event leaking to underlying handlers
- Data bridge: Flask injects `window.__GALLERY_DATA__` in template, Vue reads on mount
- Gallery grid uses `select-none` to prevent text selection on shift-click
- LazyImage handles its own fetch lifecycle (observe → debounce → fetch → blob → display → cancel on unmount)

## Testing
No automated test suite. Changes verified manually by running the app against real ComfyUI output folders:
- Mac: ~30GB, 180 folders (development)
- Linux (Arch): ~50GB, 49K+ files, 300+ folders (production)

## Refactoring Roadmap
- **Phase 0** (done): Vue scaffold, Pinia stores, API service, Tailwind
- **Phase 1** (done): Vue lightbox — LightboxViewer/Header/Media + composables
- **Phase 2** (done): Gallery grid — GalleryCard, SelectionBar, dimension-aware aspect ratios
- **Phase 3** (done): Folder sidebar — FolderTree, context menu, move dialog, new folder
- **Phase 4** (done): Toolbar — filters, sort, upload, rescan, focus mode
- **Phase 5** (done): Legacy cleanup — stripped `index.html` to 97-line shell, removed monolith
- **Phase 6** (done): Vue Router — client-side navigation, back/forward support
- **Features** (done): Image compare, storyboard viewer, metadata panel, interactive filters
- **Performance** (done): SQL optimization, thumbnail caching, lazy loading, payload reduction

## Recent Changes (our fork)
- Full Vue 3 SPA replacing legacy vanilla JS UI (18K lines of legacy removed)
- Backend refactored from 5K-line monolith into 17-file modular Flask package
- Focus mode with green workflow indicator dot
- Hide Favorites filter for curation workflow
- Move Folder in sidebar context menu, New Folder in context menu
- Image compare: slider wipe + side-by-side + metadata diff panel
- Storyboard viewer: grid overview, zoom navigation, HD toggle (native resolution on demand), PNG frame download
- Vue Router for SPA navigation with browser history support
- Interactive client-side filtering: instant name/extension/prefix/date/favourite filtering on 49K+ files
- LazyImage with debounced IntersectionObserver and AbortController cancellation
- Thumbnail caching: HTTP immutable headers + in-memory blob URL cache (2000 LRU)
- SQL query optimization: path filtering in SQL, indexed columns, explicit column lists
- Payload reduction: skip_folders param saves ~500KB on repeat navigations
- Lightbox metadata panel: prompt display, workflow files with copy-to-clipboard, folder breadcrumbs
- Sidebar folder indicators: amber highlight for selected files, focused folder dot with auto-scroll
- Dimension-aware gallery cards: 5 aspect ratio buckets (16:9, 4:3, 1:1, 3:4, 9:16)
- Production build pipeline: Vite → static/dist/, Flask serves via manifest
- Network discovery: startup banner shows all accessible URLs
- macOS resource fork filtering: `._*` files skipped during scanning
- Video streaming: range request support for large files
- Debug mode: `FLASK_DEBUG=true` enables Flask auto-reload + Vite dev injection
- Background startup scan with ScanOverlay progress bar (Flask serves immediately)
- Folder move/rename: watcher stop/restart cycle prevents FSEvents CPU storm
- Folder collapse: `ancestorKeys` excludes current folder, one-click collapse works
- Context menu viewport clamping (no more clipping at bottom of screen)
- API error messages include server response body (not just HTTP status)
- Chunked scan: DB writes interleaved with file processing, not batched at end
- Scan executor uses incremental job submission (pausable during folder ops)

## Known Issues
- Sidebar: initial scroll-to-active-folder unreliable on first load for deep folders
- Workflow keyword search uses `LIKE '%keyword%'` which forces full table scan at 49K+ files — FTS5 virtual table is the correct future solution

## File Support
- Images: PNG, JPG, JPEG, WebP (static and animated)
- Videos: MP4, WebM, MOV
- Metadata extracted from PNG/JPG EXIF (ComfyUI workflow JSON), MP4 via ffprobe

## Candidate Settings (future settings panel)
- **Storyboard HD default** — whether HD mode is on by default in storyboard zoom (currently: on)

## Candidate Features
- **Storyboard burst frames** — from zoom view, request N additional frames around current timestamp (e.g., 10 frames, 5 either side, every 2nd frame). For finding the perfect frame in fast-moving video (avoiding blinks, catching expressions). Backend: ffmpeg can extract at any timestamp, so burst = parallel extraction of N timestamps around the current one
- **Save storyboard frame to ComfyUI input** — save HD frame directly to BASE_INPUT_PATH for use as reference in further generations
- **Idle pre-fetch thumbnails** — when scroll is idle, speculatively load the next row of thumbnails using requestIdleCallback or scroll-idle detection. Currently thumbnails only load when visible for 150ms
- **Video compare** — two videos selected, synchronised side-by-side playback with shared transport controls
- **Workflow provenance graph** — select a file, trace all associated models, LoRAs, source images via workflow_files field. "Show me everything that contributed to this image"
- **Collections/workspaces** — favourite folders, curated virtual collections, input/output file associations
- **Database schema cleanup** — relative paths instead of absolute, separate path/filename columns
