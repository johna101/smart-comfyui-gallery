# CLAUDE.md

## Project Overview
SmartGallery for ComfyUI — a local, offline, browser-based gallery for managing ComfyUI-generated images and videos. Preserves workflows, extracts generation metadata, supports search/filter/compare/batch operations.

## Architecture
- **Backend:** Python 3.9+ / Flask, single file `smartgallery.py` (~5K lines)
- **Frontend:** Vanilla JS/CSS single-page app, inline in `templates/index.html` (~13K lines)
- **Database:** SQLite3, schema version 27 with auto-migrations
- **No build step** — frontend is served directly by Flask

## Dev Setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python smartgallery.py
```
Access at `http://127.0.0.1:8189/galleryout`

FFmpeg/FFprobe optional but recommended for video support.

## Key Files
- `smartgallery.py` — all backend logic: Flask routes, DB schema, file processing, metadata extraction
- `templates/index.html` — entire frontend: HTML structure, CSS styles, JS application logic
- `requirements.txt` — Python dependencies
- `Dockerfile` / `compose.yaml` — container setup (not used for local dev)

## Conventions

### Backend (Python)
- snake_case for functions and variables, PascalCase for classes
- All Flask routes prefixed with `/galleryout/`
- DB access via `get_db_connection()`, schema migrations in `init_db()`
- Background tasks use `threading` and `concurrent.futures`
- Type hints used in newer code
- Key classes: `Colors` (console output), `ComfyMetadataParser` (workflow parsing)

### Frontend (JavaScript/CSS)
- Vanilla JS — no frameworks or build tools
- CSS variables (`--color-*`) for theming (Glass/Dark themes)
- Module pattern with self-executing functions
- Async/await for modal dialogs and API calls
- IntersectionObserver for lazy-loading
- Canvas API for video frame extraction

## Testing
No automated test suite. Changes are verified manually by running the app.

## File Support
- Images: PNG, JPG, JPEG, WebP (static and animated)
- Videos: MP4, WebM, MOV
- Metadata extracted from PNG/JPG EXIF (ComfyUI workflow JSON), MP4 via ffprobe

## Config (Environment Variables)
- `BASE_OUTPUT_PATH` — ComfyUI output folder
- `BASE_INPUT_PATH` — ComfyUI input folder
- `BASE_SMARTGALLERY_PATH` — cache/DB location
- `SERVER_PORT` — default 8189
- `THUMBNAIL_WIDTH` — default 300px
- `PAGE_SIZE` — initial grid load, default 100
