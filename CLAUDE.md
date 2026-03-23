# CLAUDE.md

## Project Overview
SmartGallery for ComfyUI — a local, offline, browser-based gallery for managing ComfyUI-generated images and videos. Preserves workflows, extracts generation metadata, supports search/filter/compare/batch operations.

Forked for personal use and active refactoring. Not intended for upstream contribution.

## Architecture

### Current — Vue 3 SPA with Flask backend
- **Backend:** Python 3.9+ / Flask, modular package (`smartgallery/`)
- **Frontend:** Vue 3 + Vite + Pinia + Vue Router + Tailwind CSS v4 (`frontend/`)
- **Template:** Minimal Jinja2 shell (`templates/index.html`) — just CSS variables, `#vue-app` mount, `__GALLERY_DATA__` injection
- **Database:** SQLite3, schema version 27 with auto-migrations
- **Entry point:** `run.py` (use this, not `smartgallery.py`)
- **Legacy reference:** Original monolithic files preserved in `legacy-reference/` for reference

### Backend Package (`smartgallery/`)
- `__init__.py` — Flask app factory, registers all blueprints
- `config.py` — all constants, paths, environment variable handling
- `state.py` — mutable runtime state (caches, job trackers, globals)
- `models.py` — database access, `get_db_connection()`, `init_db()` with migrations
- `parser.py` — `ComfyMetadataParser` class, workflow/prompt JSON extraction
- `processing.py` — file scanning, thumbnail generation, parallel processing pipeline
- `folders.py` — folder management (mount, sync, config, ffprobe detection)
- `utils.py` — shared helpers (path normalization, formatting, Colors class)
- `startup.py` — server initialization, version check, banner
- `routes/` — Flask Blueprints:
  - `gallery.py` — main view, pagination, upload, JSON API for SPA navigation
  - `files.py` — file CRUD (move, copy, delete, rename, favourite)
  - `folders.py` — folder CRUD (create, mount, rename, delete, move, browse)
  - `media.py` — serve files, thumbnails, storyboards (incl. hi-res), video streaming
  - `ai.py` — AI search queue, indexing control
  - `api.py` — search options, compare, sync status
  - `batch.py` — rescan, zip preparation/download

### Frontend (`frontend/`)
- **Routing:** Vue Router with `/galleryout/view/:folderKey` — browser back/forward works
- **State:** Pinia stores — gallery (files, folders, selection), preferences (localStorage-backed), ui (lightbox, modals)
- **API:** Typed service (`src/api/gallery.ts`) wrapping all 30+ backend endpoints
- **Components:**
  - `lightbox/` — LightboxViewer, LightboxHeader, LightboxMedia + composables (zoom, keyboard)
  - `gallery/` — GalleryGrid, GalleryCard, SelectionBar
  - `sidebar/` — FolderSidebar, FolderTree, FolderContextMenu, FolderMoveDialog
  - `toolbar/` — GalleryToolbar, FilterPanel, RescanProgress
  - `compare/` — ImageCompare (side-by-side + slider wipe mode, metadata diff)
  - `storyboard/` — StoryboardViewer (grid + zoom with HD toggle, keyboard nav)
- **Composables:** useFolderNavigation, useLightboxZoom, useLightboxKeys, useSelection
- **Tailwind v4:** scoped `<style>` blocks need `@reference "tailwindcss"` for `@apply` to work

## Dev Setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run.py
```
Access at `http://192.168.1.12:8189/galleryout` (or `127.0.0.1:8189`)

For Vue frontend development (alongside Flask):
```bash
cd frontend
npm install
npm run dev
```

### PyCharm Configuration
- Script path: `run.py`
- Environment variables: defaults hardcoded in `smartgallery/config.py`
- Debug mode: `FLASK_DEBUG=true` enables auto-reload and Vite dev script injection

### Key Environment Variables
- `BASE_OUTPUT_PATH` — ComfyUI output folder
- `BASE_INPUT_PATH` — ComfyUI input folder
- `BASE_SMARTGALLERY_PATH` — cache/DB location
- `SERVER_HOST` — default `127.0.0.1`
- `SERVER_PORT` — default `8189`
- `FLASK_DEBUG` — enables debug mode, auto-reload, Vite dev injection

FFmpeg/FFprobe required for video support (thumbnails, storyboards, streaming).

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

### Frontend (Vue 3)
- Vue 3 Composition API + TypeScript throughout
- Pinia for state management, localStorage for user preferences
- Tailwind CSS v4 with theme mapped to legacy CSS variables
- Async/await throughout, typed API layer
- Composable return values are plain objects — use `.value` when passing refs as props
- Keyboard handlers: always check `e.metaKey || e.ctrlKey || e.altKey` before intercepting single keys
- Modal/overlay keyboard handlers use capture phase (`addEventListener('keydown', fn, true)`) to prevent event leaking to underlying handlers
- Data bridge: Flask injects `window.__GALLERY_DATA__` in template, Vue reads on mount

## Testing
No automated test suite. Changes verified manually by running the app against a real ComfyUI output folder (~30GB, 180 folders).

## Refactoring Roadmap
- **Phase 0** (done): Vue scaffold, Pinia stores, API service, Tailwind
- **Phase 1** (done): Vue lightbox — LightboxViewer/Header/Media + composables
- **Phase 2** (done): Gallery grid — GalleryCard, SelectionBar, infinite scroll
- **Phase 3** (done): Folder sidebar — FolderTree, context menu, move dialog
- **Phase 4** (done): Toolbar — filters, sort, upload, rescan, focus mode
- **Phase 5** (done): Legacy cleanup — stripped `index.html` to minimal shell
- **Phase 6** (done): Vue Router — client-side navigation, back/forward support
- **Features** (done): Image compare (slider + side-by-side), storyboard viewer (HD toggle)

## Recent Changes (our fork)
- Full Vue 3 SPA replacing legacy vanilla JS UI
- Backend refactored from 5K-line monolith into modular Flask package
- Focus mode with green workflow indicator dot
- Hide Favorites filter for curation workflow
- Move Folder in sidebar context menu
- Image compare: slider wipe + side-by-side + metadata diff panel
- Storyboard viewer: grid overview, zoom navigation, HD toggle (native resolution on demand)
- Vue Router for SPA navigation with browser history support
- Debug mode: `FLASK_DEBUG=true` enables Flask auto-reload + Vite dev injection

## Known Issues
- Sidebar: collapsing parent when child is selected doesn't always collapse visually
- Sidebar: initial scroll-to-active-folder unreliable on first load for deep folders
- Filter panel: server round-trip on apply (future: client-side interactive filtering)
- Focus mode toggle button (legacy top bar) doesn't sync with Vue state

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
