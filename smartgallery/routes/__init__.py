from smartgallery.routes.gallery import gallery_bp
from smartgallery.routes.files import files_bp
from smartgallery.routes.folders import folders_bp
from smartgallery.routes.media import media_bp
from smartgallery.routes.ai import ai_bp
from smartgallery.routes.api import api_bp
from smartgallery.routes.batch import batch_bp

ALL_BLUEPRINTS = [gallery_bp, files_bp, folders_bp, media_bp, ai_bp, api_bp, batch_bp]
