# Smart Gallery for ComfyUI - App Factory
# Creates and configures the Flask application.

from flask import Flask, redirect, url_for
from smartgallery.config import SECRET_KEY


def create_app():
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder='../templates',
        static_folder='../static'
    )
    app.secret_key = SECRET_KEY

    # Register all blueprints
    from smartgallery.routes import ALL_BLUEPRINTS
    for bp in ALL_BLUEPRINTS:
        app.register_blueprint(bp)

    # Root redirect (outside blueprints since it's '/')
    @app.route('/')
    def root_redirect():
        return redirect(url_for('gallery.gallery_view', folder_key='_root_'))

    return app
