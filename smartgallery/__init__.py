# Smart Gallery for ComfyUI - App Factory
# Creates and configures the Flask application.

import os
import json
from flask import Flask, redirect, url_for
from smartgallery.config import SECRET_KEY


def _load_vue_assets():
    """Read Vite manifest and generate <script>/<link> tags for production."""
    manifest_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'dist', '.vite', 'manifest.json')
    if not os.path.exists(manifest_path):
        return '<!-- Vue build not found — run: cd frontend && npm run build -->'

    with open(manifest_path) as f:
        manifest = json.load(f)

    tags = []
    # Find the entry point
    for key, entry in manifest.items():
        if entry.get('isEntry'):
            # CSS files
            for css in entry.get('css', []):
                tags.append(f'<link rel="stylesheet" href="/static/dist/{css}">')
            # JS entry
            tags.append(f'<script type="module" src="/static/dist/{entry["file"]}"></script>')

    return '\n    '.join(tags)


def create_app():
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder='../templates',
        static_folder='../static'
    )
    app.secret_key = SECRET_KEY

    # Load Vue production assets once at startup
    _vue_assets_html = _load_vue_assets()

    @app.context_processor
    def inject_vue_assets():
        return {'vue_assets': _vue_assets_html}

    # Register all blueprints
    from smartgallery.routes import ALL_BLUEPRINTS
    for bp in ALL_BLUEPRINTS:
        app.register_blueprint(bp)

    # Root redirect (outside blueprints since it's '/')
    @app.route('/')
    def root_redirect():
        return redirect(url_for('gallery.gallery_view', folder_key='_root_'))

    # Suppress noisy per-request logs from werkzeug (GET /galleryout/api/folder/... 200)
    import logging as _logging
    _logging.getLogger('werkzeug').setLevel(_logging.WARNING)

    return app
