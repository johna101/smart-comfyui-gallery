# Smart Gallery for ComfyUI - Filesystem Watcher
# Detects external file changes (ComfyUI output, manual edits) and pushes events
# through the EventBus for real-time client updates.

import os
import hashlib
import logging
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from smartgallery.config import (
    BASE_OUTPUT_PATH,
    THUMBNAIL_CACHE_FOLDER_NAME, SQLITE_CACHE_FOLDER_NAME,
    ZIP_CACHE_FOLDER_NAME, AI_MODELS_FOLDER_NAME
)
from smartgallery.models import get_db_connection
from smartgallery.processing import process_single_file
from smartgallery.events import publish_event
from smartgallery.utils import folder_key_from_filepath
from smartgallery.queries import FILES_UPSERT, FILES_EXISTS_BY_ID, FILES_DELETE_BY_ID

logger = logging.getLogger(__name__)

# Same extensions as full_sync_database() in folders.py
VALID_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp', '.gif',
    '.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v', '.wmv', '.flv', '.mts', '.ts',
    '.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac'
}

EXCLUDED_DIRS = {
    THUMBNAIL_CACHE_FOLDER_NAME, SQLITE_CACHE_FOLDER_NAME,
    ZIP_CACHE_FOLDER_NAME, AI_MODELS_FOLDER_NAME,
    'venv', 'venv-ai', '.git', 'node_modules', '__pycache__'
}


def _should_ignore(path):
    """Check if a path should be ignored (cache dirs, hidden dirs, non-media)."""
    basename = os.path.basename(path)

    # Skip macOS resource forks
    if basename.startswith('._'):
        return True

    # Skip hidden files
    if basename.startswith('.'):
        return True

    # Check path components for excluded directories
    parts = path.replace('\\', '/').split('/')
    for part in parts:
        if part in EXCLUDED_DIRS or (part.startswith('.') and part != '.'):
            return True

    return False


def _is_valid_media(path):
    """Check if file has a valid media extension."""
    _, ext = os.path.splitext(path)
    return ext.lower() in VALID_EXTENSIONS


def _process_and_upsert(filepath):
    """Process a file and upsert into DB. Returns file_id or None."""
    try:
        if not os.path.isfile(filepath):
            return None

        result = process_single_file(filepath)
        if not result:
            return None

        with get_db_connection() as conn:
            conn.execute(FILES_UPSERT, result)
            conn.commit()

        return result[0]  # file_id

    except Exception as e:
        logger.warning("Watcher: failed to process %s: %s", os.path.basename(filepath), e)
        return None


class SmartGalleryHandler(FileSystemEventHandler):
    """Watchdog event handler with per-file debouncing."""

    def __init__(self):
        super().__init__()
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _cancel_timer(self, path):
        with self._lock:
            timer = self._timers.pop(path, None)
            if timer:
                timer.cancel()

    def _debounce(self, path, callback, delay=1.0):
        """Schedule a callback after `delay` seconds, resetting on repeated events."""
        self._cancel_timer(path)
        timer = threading.Timer(delay, callback)
        timer.daemon = True
        with self._lock:
            self._timers[path] = timer
        timer.start()

    def on_created(self, event):
        if event.is_directory:
            # New folder — refresh folder tree
            if not _should_ignore(event.src_path):
                self._debounce(event.src_path, lambda: self._handle_folder_created(event.src_path))
            return
        path = event.src_path
        if _should_ignore(path) or not _is_valid_media(path):
            return
        self._debounce(path, lambda p=path: self._handle_file_created(p))

    def on_deleted(self, event):
        if event.is_directory:
            if not _should_ignore(event.src_path):
                self._debounce(event.src_path + ':dir_del', lambda: self._handle_folder_changed())
            return
        path = event.src_path
        if _should_ignore(path) or not _is_valid_media(path):
            return
        self._cancel_timer(path)  # No point processing a deleted file
        self._handle_file_deleted(path)

    def on_moved(self, event):
        if event.is_directory:
            if not _should_ignore(event.dest_path):
                self._debounce(event.dest_path + ':dir_mv', lambda: self._handle_folder_changed())
            return
        src = event.src_path
        dest = event.dest_path
        if _should_ignore(dest):
            # Moved to an ignored location — treat as delete
            if _is_valid_media(src):
                self._handle_file_deleted(src)
            return
        if not _is_valid_media(dest):
            return
        self._cancel_timer(src)
        self._debounce(dest, lambda: self._handle_file_moved(src, dest))

    def on_modified(self, event):
        if event.is_directory:
            return
        path = event.src_path
        if _should_ignore(path) or not _is_valid_media(path):
            return
        # Debounce — reuses the created handler since the upsert handles both
        self._debounce(path, lambda p=path: self._handle_file_created(p))

    def _handle_file_created(self, filepath):
        """Process a new/modified file and publish event."""
        file_id = _process_and_upsert(filepath)
        if file_id:
            publish_event("files_detected", {
                "folder_key": folder_key_from_filepath(filepath),
                "file_id": file_id,
                "filename": os.path.basename(filepath),
            }, source="watcher")
            logger.info("Watcher: detected %s", os.path.basename(filepath))

    def _handle_file_deleted(self, filepath):
        """Remove file from DB and publish event."""
        file_id = hashlib.md5(filepath.encode()).hexdigest()
        try:
            with get_db_connection() as conn:
                # Check if it actually exists in DB before deleting
                row = conn.execute(FILES_EXISTS_BY_ID, (file_id,)).fetchone()
                if row:
                    conn.execute(FILES_DELETE_BY_ID, (file_id,))
                    conn.commit()
                    publish_event("files_removed", {
                        "folder_key": folder_key_from_filepath(filepath),
                        "file_ids": [file_id],
                    }, source="watcher")
                    logger.info("Watcher: removed %s", os.path.basename(filepath))
        except Exception as e:
            logger.warning("Watcher: failed to handle deletion of %s: %s", os.path.basename(filepath), e)

    def _handle_file_moved(self, src_path, dest_path):
        """Handle file move: delete old record, process at new location."""
        old_id = hashlib.md5(src_path.encode()).hexdigest()
        try:
            with get_db_connection() as conn:
                conn.execute(FILES_DELETE_BY_ID, (old_id,))
                conn.commit()
        except Exception as e:
            logger.warning("Watcher: failed to remove old record for move: %s", e)

        # Process at new location (creates new DB record)
        new_id = _process_and_upsert(dest_path)
        if new_id:
            publish_event("file_moved_external", {
                "old_file_id": old_id,
                "new_file_id": new_id,
                "folder_key": folder_key_from_filepath(dest_path),
                "filename": os.path.basename(dest_path),
            }, source="watcher")
            logger.info("Watcher: moved %s → %s", os.path.basename(src_path), os.path.basename(dest_path))

    def _handle_folder_created(self, folder_path):
        """New folder detected — refresh folder config and notify clients."""
        from smartgallery.folders import get_dynamic_folder_config
        get_dynamic_folder_config(force_refresh=True)
        publish_event("folder_created", {
            "folder_name": os.path.basename(folder_path),
        }, source="watcher")
        logger.info("Watcher: new folder %s", os.path.basename(folder_path))

    def _handle_folder_changed(self):
        """Folder deleted, moved, or renamed externally — refresh tree and notify."""
        from smartgallery.folders import get_dynamic_folder_config
        get_dynamic_folder_config(force_refresh=True)
        publish_event("folder_deleted", {
            "folder_key": "_unknown_",
            "parent_key": "_root_",
        }, source="watcher")
        logger.info("Watcher: folder tree changed")


def start_watcher():
    """Start the filesystem watcher on BASE_OUTPUT_PATH. Returns the Observer."""
    if not BASE_OUTPUT_PATH or not os.path.isdir(BASE_OUTPUT_PATH):
        logger.warning("Watcher: BASE_OUTPUT_PATH not set or not found, skipping")
        return None

    observer = Observer()
    handler = SmartGalleryHandler()
    observer.schedule(handler, BASE_OUTPUT_PATH, recursive=True)
    observer.daemon = True
    observer.start()
    logger.info("File watcher started on %s", BASE_OUTPUT_PATH)
    return observer


def stop_watcher(observer):
    """Stop the filesystem watcher."""
    if observer:
        observer.stop()
        observer.join(timeout=5)
