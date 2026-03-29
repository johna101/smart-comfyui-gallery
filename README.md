<div align="center">

  <h1>SmartGallery for ComfyUI (Personal Fork)</h1>

  <p>
    A local, offline, browser-based gallery for managing ComfyUI-generated images and videos.<br>
    Preserves workflows, extracts generation metadata, supports search/filter/compare/batch operations.
  </p>

  <p>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"></a>
    <img src="https://img.shields.io/badge/Python-3.9+-blue.svg" alt="Python">
  </p>

</div>

---

## Attribution

This is a personal fork of [**SmartGallery for ComfyUI**](https://github.com/biagiomaf/smart-comfyui-gallery) by [Biagio Maffettone](https://github.com/biagiomaf). The original project is excellent — if you're looking for the actively maintained, community-supported version, **go there**.

This fork is for my own use. The architecture has diverged significantly. I keep the repo public out of respect for open source, but have no intention of maintaining it.

---

## What Changed

The codebase has been substantially rewritten. The core idea and domain are the same, but the implementation is different:

**Architecture**
- Frontend rewritten as a **Vue 3 SPA** (Composition API + TypeScript + Pinia + Vue Router + Tailwind CSS v4), replacing the original vanilla JS UI
- Backend refactored into a **modular Flask package** (`smartgallery/` — 17 files, Blueprints, separated concerns)
- Production build pipeline via Vite with manifest-based asset serving

**Features added or re-implemented in this fork**
- Image compare: slider wipe + side-by-side + metadata diff panel
- Storyboard viewer: grid overview, zoom navigation, HD toggle, PNG frame download
- Interactive client-side filtering: instant name/extension/prefix/date/favourite filtering
- Lightbox metadata panel with prompt display, workflow files, copy-to-clipboard
- Focus mode with workflow indicator
- Folder move/rename in sidebar context menu
- Background startup scan with progress overlay (server available immediately)
- Filesystem watcher coordination for folder operations (stop/restart cycle)

**Performance**
- Two-tier filtering: SQL for scope, client-side for instant interaction
- LazyImage with debounced IntersectionObserver and AbortController cancellation
- Thumbnail blob URL cache (2000-entry LRU) with HTTP immutable headers
- SQL optimization: path filtering in queries, indexed columns, explicit column lists
- Payload reduction: `skip_folders` param saves ~500KB on repeat navigations

---

## Setup

```bash
git clone https://github.com/johna101/smart-comfyui-gallery.git
cd smart-comfyui-gallery
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `settings.json` in the project root:

```json
{
  "comfyui_output_path": "/path/to/comfyui/output",
  "comfyui_input_path": "/path/to/comfyui/input"
}
```

Run:

```bash
python run.py
```

Open `http://127.0.0.1:8189/galleryout`

### Frontend Development

```bash
cd frontend
npm install
npm run dev
```

Set `FLASK_DEBUG=true` for Flask auto-reload and Vite dev server injection.

### Production Build

```bash
cd frontend && npm install && npm run build
cd .. && python run.py
```

FFmpeg/ffprobe required for video support.

---

## Configuration

Config resolution (highest priority wins):
1. **Environment variables** — for Docker, scripts, CI
2. **settings.json** — primary config for local use
3. **Smart defaults** — derived from working directory

| Setting | Default | Description |
|---|---|---|
| `comfyui_output_path` | *(required)* | ComfyUI output folder |
| `comfyui_input_path` | *(optional)* | ComfyUI input folder |
| `data_path` | `./data` | DB, thumbnails, caches |
| `server_host` | `0.0.0.0` | Bind address |
| `server_port` | `8189` | Port |
| `delete_mode` | `permanent` | Trash path or `"permanent"` |
| `ffprobe_path` | `auto` | Path to ffprobe |

Environment variable overrides: `BASE_OUTPUT_PATH`, `BASE_INPUT_PATH`, `BASE_SMARTGALLERY_PATH`, `SERVER_HOST`, `SERVER_PORT`, `FLASK_DEBUG`.

---

## License

MIT License — see [LICENSE](LICENSE).

Original work copyright (c) 2025-2026 [Biagio Maffettone](https://github.com/biagiomaf).

---

<p align="center">
  <em>Built on the shoulders of <a href="https://github.com/biagiomaf/smart-comfyui-gallery">SmartGallery</a></em>
</p>
