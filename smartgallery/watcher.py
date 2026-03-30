# Smart Gallery for ComfyUI - Filesystem Watcher
# Detects external file changes (ComfyUI output, manual edits) and pushes events
# through the EventBus for real-time client updates.

import os
import hashlib
import logging
import time
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from smartgallery.config import (
    BASE_OUTPUT_PATH,
    THUMBNAIL_CACHE_FOLDER_NAME, SQLITE_CACHE_FOLDER_NAME,
    ZIP_CACHE_FOLDER_NAME,
)
from smartgallery.models import get_db_connection
from smartgallery.processing import process_single_file
from smartgallery.events import publish_event
from smartgallery import state
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
    ZIP_CACHE_FOLDER_NAME, '.AImodels',
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

    def cancel_all_timers(self):
        """Cancel all pending debounced callbacks. Called when a folder operation starts."""
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()

    def _debounce(self, path, callback, delay=1.0):
        """Schedule a callback after `delay` seconds, resetting on repeated events.
        Re-checks suppression flag at fire time to handle events queued before a folder op started."""
        self._cancel_timer(path)
        def guarded():
            if not self._suppressed():
                callback()
        timer = threading.Timer(delay, guarded)
        timer.daemon = True
        with self._lock:
            self._timers[path] = timer
        timer.start()

    def _suppressed(self):
        """Check if events should be suppressed during folder operations."""
        return state.folder_operation_in_progress

    def on_created(self, event):
        if self._suppressed():
            return
        if event.is_directory:
            # New folder — refresh folder tree
            if not _should_ignore(event.src_path):
                print(f"[Watcher] Dir created: {event.src_path}")
                self._debounce(event.src_path, lambda: self._handle_folder_created(event.src_path))
            return
        path = event.src_path
        if _should_ignore(path) or not _is_valid_media(path):
            return
        print(f"[Watcher] File created: {os.path.basename(path)}")
        self._debounce(path, lambda p=path: self._handle_file_created(p))

    def on_deleted(self, event):
        if self._suppressed():
            return
        if event.is_directory:
            if not _should_ignore(event.src_path):
                self._debounce(event.src_path + ':dir_del', lambda: self._handle_folder_changed())
            return
        path = event.src_path
        if _should_ignore(path) or not _is_valid_media(path):
            return
        self._cancel_timer(path)  # No point processing a deleted file
        if not self._suppressed():
            self._handle_file_deleted(path)

    def on_moved(self, event):
        if self._suppressed():
            return
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
        if self._suppressed():
            return
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

    def _scan_new_folder(self, folder_path):
        """Scan a newly created folder for media files not yet in the DB.

        Called immediately on folder detection and again at intervals to catch files
        written after the initial scan (e.g. ComfyUI generation takes 10-60+ seconds).
        Returns the number of new files inserted.
        """
        if not os.path.isdir(folder_path):
            return 0

        inserted = 0
        try:
            for name in os.listdir(folder_path):
                filepath = os.path.join(folder_path, name)
                if not os.path.isfile(filepath):
                    continue
                if _should_ignore(filepath) or not _is_valid_media(filepath):
                    continue
                # Skip if already in DB
                file_id = hashlib.md5(filepath.encode()).hexdigest()
                try:
                    with get_db_connection() as conn:
                        if conn.execute(FILES_EXISTS_BY_ID, (file_id,)).fetchone():
                            continue
                except Exception:
                    pass
                new_id = _process_and_upsert(filepath)
                if new_id:
                    publish_event("files_detected", {
                        "folder_key": folder_key_from_filepath(filepath),
                        "file_id": new_id,
                        "filename": name,
                    }, source="watcher")
                    logger.info("Watcher: new file in new folder: %s", name)
                    inserted += 1
        except OSError as e:
            logger.warning("Watcher: could not scan folder %s: %s", folder_path, e)

        return inserted

    def _handle_folder_created(self, folder_path):
        """New folder detected — refresh folder config, notify clients, poll for files.

        Watchdog events for files inside a newly-created directory are unreliable:
        on Linux/inotify the recursive watch races with the file being written; on
        macOS FSEvents can coalesce or drop events in rapid sequences. Rather than
        relying solely on on_created for those files, we scan the new folder at
        increasing intervals until no new files appear. This covers the full range
        of ComfyUI generation times (seconds to minutes).
        """
        from smartgallery.folders import get_dynamic_folder_config
        get_dynamic_folder_config(force_refresh=True)

        # Publish folder event immediately so the sidebar updates
        publish_event("folder_created", {
            "folder_name": os.path.basename(folder_path),
        }, source="watcher")
        logger.info("Watcher: new folder detected: %s", os.path.basename(folder_path))

        # Initial scan — catches files already present (fast generations)
        self._scan_new_folder(folder_path)

        # Follow-up scans at increasing intervals — covers slower generations.
        # Stops early if folder disappears. Scans are cheap (DB check before processing).
        def poll(attempt, delays):
            if not os.path.isdir(folder_path):
                return
            self._scan_new_folder(folder_path)
            if delays:
                t = threading.Timer(delays[0], poll, args=[attempt + 1, delays[1:]])
                t.daemon = True
                t.start()

        delays = [5.0, 15.0, 45.0, 120.0]
        t = threading.Timer(delays[0], poll, args=[1, delays[1:]])
        t.daemon = True
        t.start()

    def _handle_folder_changed(self):
        """Folder deleted, moved, or renamed externally — refresh tree and notify."""
        from smartgallery.folders import get_dynamic_folder_config
        get_dynamic_folder_config(force_refresh=True)
        publish_event("folder_deleted", {
            "folder_key": "_unknown_",
            "parent_key": "_root_",
        }, source="watcher")
        logger.info("Watcher: folder tree changed")


def _start_root_poller(handler):
    """Poll BASE_OUTPUT_PATH for new root-level directories.

    Watchdog's inotify watch on the root directory can silently fail to
    deliver events for new top-level subdirectories on some Linux systems
    (while child-directory events work fine via their parent's watch).
    This lightweight poller checks every 10 seconds, comparing os.listdir
    against a known set, and triggers _handle_folder_created for any new dirs.
    """
    known_dirs = set()

    def snapshot():
        """Return current set of direct child directories."""
        try:
            return {
                name for name in os.listdir(BASE_OUTPUT_PATH)
                if os.path.isdir(os.path.join(BASE_OUTPUT_PATH, name))
                and not name.startswith('.')
                and name not in {THUMBNAIL_CACHE_FOLDER_NAME, SQLITE_CACHE_FOLDER_NAME,
                                 ZIP_CACHE_FOLDER_NAME, '.AImodels'}
            }
        except OSError:
            return set()

    known_dirs = snapshot()

    def poll_loop():
        nonlocal known_dirs
        while True:
            time.sleep(10)
            if state.folder_operation_in_progress:
                continue
            current = snapshot()
            new_dirs = current - known_dirs
            for name in new_dirs:
                folder_path = os.path.join(BASE_OUTPUT_PATH, name)
                print(f"[Watcher:Poller] New root folder detected: {name}")
                handler._handle_folder_created(folder_path)
            known_dirs = current

    t = threading.Thread(target=poll_loop, daemon=True)
    t.start()
    logger.info("Root directory poller started (10s interval)")


def start_watcher():
    """Start the filesystem watcher on BASE_OUTPUT_PATH. Returns the Observer."""
    if not BASE_OUTPUT_PATH or not os.path.isdir(BASE_OUTPUT_PATH):
        logger.warning("Watcher: BASE_OUTPUT_PATH not set or not found, skipping")
        return None

    observer = Observer()
    handler = SmartGalleryHandler()
    state.watcher_handler = handler
    state.watcher_observer = observer
    observer.schedule(handler, BASE_OUTPUT_PATH, recursive=True)
    observer.daemon = True
    observer.start()
    logger.info("File watcher started on %s", BASE_OUTPUT_PATH)

    # Fallback poller for new root-level directories (works around inotify blind spot)
    _start_root_poller(handler)

    return observer


def stop_watcher(observer):
    """Stop the filesystem watcher."""
    if observer:
        observer.stop()
        observer.join(timeout=5)
