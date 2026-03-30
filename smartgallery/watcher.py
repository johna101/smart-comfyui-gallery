# Smart Gallery for ComfyUI - Filesystem Watcher
# Detects external file changes (ComfyUI output, manual edits) and triggers
# a debounced database rescan to reconcile DB state with disk.
#
# Design: watchdog is a "something changed" signal, not a per-file processor.
# Any relevant event resets a 2-second debounce timer. When the timer fires,
# a full disk-vs-DB sync runs. This is simple, self-healing, and avoids all
# the race conditions of per-file event handling (inotify gaps, partial writes,
# coalesced FSEvents, etc.).

import os
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
from smartgallery import state

logger = logging.getLogger(__name__)

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

# Debounce delay: wait this long after the last event before rescanning.
RESCAN_DEBOUNCE_SECONDS = 2.0

# Root poller interval: how often to check for new top-level directories.
ROOT_POLL_SECONDS = 10


def _should_ignore(path):
    """Check if a path should be ignored (cache dirs, hidden dirs, non-media)."""
    basename = os.path.basename(path)
    if basename.startswith('._') or basename.startswith('.'):
        return True
    parts = path.replace('\\', '/').split('/')
    for part in parts:
        if part in EXCLUDED_DIRS or (part.startswith('.') and part != '.'):
            return True
    return False


def _is_valid_media(path):
    """Check if file has a valid media extension."""
    _, ext = os.path.splitext(path)
    return ext.lower() in VALID_EXTENSIONS


class SmartGalleryHandler(FileSystemEventHandler):
    """Simplified watchdog handler. Any relevant event triggers a debounced
    full rescan — no per-file or per-folder processing."""

    def __init__(self):
        super().__init__()
        self._rescan_timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def cancel_all_timers(self):
        """Cancel the pending rescan timer. Called when a folder operation starts."""
        with self._lock:
            if self._rescan_timer:
                self._rescan_timer.cancel()
                self._rescan_timer = None

    def _suppressed(self):
        """Check if events should be suppressed during folder operations."""
        return state.folder_operation_in_progress

    def _schedule_rescan(self):
        """Reset the debounce timer. When it fires, a DB sync runs."""
        with self._lock:
            if self._rescan_timer:
                self._rescan_timer.cancel()
            timer = threading.Timer(RESCAN_DEBOUNCE_SECONDS, self._run_rescan)
            timer.daemon = True
            self._rescan_timer = timer
            timer.start()

    def _run_rescan(self):
        """Execute the database sync. Called by the debounce timer."""
        with self._lock:
            self._rescan_timer = None
        if self._suppressed():
            return
        try:
            from smartgallery.folders import watcher_sync
            from smartgallery.models import get_db_connection
            with get_db_connection() as conn:
                changed = watcher_sync(conn)
            # If the sync found changes, reschedule the observer so inotify
            # picks up watches for any new directories on the tree.
            if changed:
                self._refresh_observer()
        except Exception as e:
            logger.warning("Watcher rescan failed: %s", e)

    def _refresh_observer(self):
        """Reschedule the observer to pick up inotify watches for new directories."""
        observer = state.watcher_observer
        if observer:
            try:
                observer.unschedule_all()
                observer.schedule(self, BASE_OUTPUT_PATH, recursive=True)
                logger.info("Watcher: refreshed observer watches")
            except Exception as e:
                logger.warning("Watcher: failed to refresh observer: %s", e)

    def on_any_event(self, event):
        if self._suppressed():
            return
        path = getattr(event, 'dest_path', None) or event.src_path
        if _should_ignore(path):
            return
        # For file events, filter by media extension
        if not event.is_directory and not _is_valid_media(path):
            return
        self._schedule_rescan()


def _start_root_poller(handler):
    """Poll BASE_OUTPUT_PATH for new root-level directories.

    Watchdog's inotify watch on the root directory can silently fail to
    deliver events for new top-level subdirectories on some Linux systems.
    This lightweight poller detects new dirs and triggers a rescan.
    """
    known_dirs = set()

    def snapshot():
        try:
            return {
                name for name in os.listdir(BASE_OUTPUT_PATH)
                if os.path.isdir(os.path.join(BASE_OUTPUT_PATH, name))
                and not name.startswith('.')
                and name not in EXCLUDED_DIRS
            }
        except OSError:
            return set()

    known_dirs = snapshot()

    def poll_loop():
        nonlocal known_dirs
        while True:
            time.sleep(ROOT_POLL_SECONDS)
            if state.folder_operation_in_progress:
                continue
            current = snapshot()
            if current != known_dirs:
                new_dirs = current - known_dirs
                removed_dirs = known_dirs - current
                if new_dirs:
                    print(f"[Watcher] New root folder(s): {', '.join(sorted(new_dirs))}")
                if removed_dirs:
                    print(f"[Watcher] Removed root folder(s): {', '.join(sorted(removed_dirs))}")
                known_dirs = current
                handler._schedule_rescan()

    t = threading.Thread(target=poll_loop, daemon=True)
    t.start()
    logger.info("Root directory poller started (%ds interval)", ROOT_POLL_SECONDS)


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

    # Fallback poller for new root-level directories (inotify blind spot)
    _start_root_poller(handler)

    return observer


def stop_watcher(observer):
    """Stop the filesystem watcher."""
    if observer:
        observer.stop()
        observer.join(timeout=5)
