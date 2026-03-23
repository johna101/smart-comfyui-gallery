# CLAUDE.md

## Project Overview
SmartGallery for ComfyUI — a local, offline, browser-based gallery for managing ComfyUI-generated images and videos. Preserves workflows, extracts generation metadata, supports search/filter/compare/batch operations.

Forked for personal use and active refactoring. Not intended for upstream contribution.

## Architecture

### Current (hybrid — refactoring in progress)
- **Backend:** Python 3.9+ / Flask, refactored into modular package (`smartgallery/`)
- **Frontend (legacy):** Vanilla JS/CSS single-page app, inline in `templates/index.html` (~13K lines) — still the active UI
- **Frontend (new):** Vue 3 + Vite + Pinia + Tailwind scaffold in `frontend/` — Phase 0 complete, mounts silently alongside legacy
- **Database:** SQLite3, schema version 27 with auto-migrations
- **Entry point:** `run.py` (use this, not `smartgallery.py`)

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
  - `gallery.py` — main view, pagination, upload
  - `files.py` — file CRUD (move, copy, delete, rename, favourite)
  - `folders.py` — folder CRUD (create, mount, rename, delete, move, browse)
  - `media.py` — serve files, thumbnails, storyboards, video streaming
  - `ai.py` — AI search queue, indexing control
  - `api.py` — search options, compare, sync status
  - `batch.py` — rescan, zip preparation/download

### Frontend Scaffold (`frontend/`)
- `src/stores/` — Pinia stores: gallery, preferences (localStorage-backed), ui
- `src/api/gallery.ts` — typed API service wrapping all 30+ backend endpoints
- `src/types/gallery.ts` — TypeScript interfaces for all data models
- `src/components/` — Vue components (in progress)
- Vite dev proxy configured to Flask backend on port 8189

## Dev Setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run.py
```
Access at `http://127.0.0.1:8189/galleryout`

For Vue frontend development (alongside Flask):
```bash
cd frontend
npm install
npm run dev
```

### PyCharm Configuration
- Script path: `run.py`
- Environment variables set as defaults in `smartgallery/config.py`
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

### Frontend (Legacy — templates/index.html)
- Vanilla JS, no frameworks
- CSS variables (`--color-*`) for theming (Glass/Dark themes)
- Server data injected via `window.__GALLERY_DATA__` consolidated block
- All Jinja2 `url_for` calls use legacy aliases (no blueprint prefix)

### Frontend (New — frontend/)
- Vue 3 Composition API + TypeScript
- Pinia for state management
- Tailwind CSS with theme mapped to existing CSS variables
- Async/await throughout, typed API layer

## Testing
No automated test suite. Changes verified manually by running the app against a real ComfyUI output folder (~30GB, 180 folders).

## Refactoring Roadmap
- **Phase 0** (done): Vue scaffold, Pinia stores, API service, Tailwind — mounts silently
- **Phase 1** (next): First Vue component replacing a legacy section (e.g., lightbox/viewer)
- **Phase 2**: Gallery grid as Vue component
- **Phase 3**: Sidebar/folder tree as Vue component
- **Phase 4**: Filter bar as Vue component
- **Phase 5**: Remove legacy JS, full Vue SPA
- **Phase 6**: Vue Router replaces server-side navigation

## Recent Changes (our fork)
- Focus mode: green dot indicator for files with embedded workflows
- Filters: "Hide Favorites" option for curation workflow (mark keepers, delete rest)
- Folders: "Move Folder" option in sidebar context menu
- Backend: modular package structure with Flask Blueprints
- Debug: `FLASK_DEBUG=true` enables auto-reload

## File Support
- Images: PNG, JPG, JPEG, WebP (static and animated)
- Videos: MP4, WebM, MOV
- Metadata extracted from PNG/JPG EXIF (ComfyUI workflow JSON), MP4 via ffprobe
