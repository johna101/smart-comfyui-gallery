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

    # Register endpoint aliases so templates using unqualified names still work.
    # The original monolithic app used e.g. url_for('gallery_view') — with blueprints
    # the endpoint becomes 'gallery.gallery_view'. Rather than rewriting 13K lines of
    # template, we create duplicate URL rules with the old unqualified endpoint names.
    from werkzeug.routing import Rule
    for rule in list(app.url_map.iter_rules()):
        if '.' in rule.endpoint:
            short_name = rule.endpoint.split('.', 1)[1]
            if short_name not in app.view_functions:
                app.view_functions[short_name] = app.view_functions[rule.endpoint]
                app.url_map.add(Rule(rule.rule, endpoint=short_name, methods=rule.methods))

    return app
