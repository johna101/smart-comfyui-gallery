# Smart Gallery for ComfyUI - Entry Point
# Run this file to start the gallery server.
#
# Usage:
#   python run.py
#
# This replaces the old `python smartgallery.py` command.
# The original smartgallery.py is preserved as a backup.

from smartgallery.startup import run_app

if __name__ == '__main__':
    run_app()
