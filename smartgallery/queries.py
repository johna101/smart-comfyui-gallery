# Smart Gallery for ComfyUI - SQL Query Registry
# Centralised SQL definitions. All queries live here; consuming modules import constants.
# Views are created in init_views() and used by SELECT queries where appropriate.

# ---------------------------------------------------------------------------
# VIEWS — created once at DB init, provide column-safe read interfaces
# ---------------------------------------------------------------------------

CREATE_VIEW_FILES = """
    CREATE VIEW IF NOT EXISTS v_files AS
    SELECT id, path, mtime, name, type, duration, dimensions,
           has_workflow, is_favorite, size, last_scanned,
           workflow_files, workflow_prompt,
           ai_last_scanned, ai_caption, ai_error
    FROM files
"""

CREATE_VIEW_FILES_WITH_AI = """
    CREATE VIEW IF NOT EXISTS v_files_ai AS
    SELECT id, path, mtime, name, type, duration, dimensions,
           has_workflow, is_favorite, size, last_scanned,
           workflow_files, workflow_prompt,
           ai_last_scanned, ai_caption, ai_embedding, ai_error
    FROM files
"""


def init_views(conn):
    """Create all SQL views. Called from init_db() after table creation."""
    conn.execute(CREATE_VIEW_FILES)
    conn.execute(CREATE_VIEW_FILES_WITH_AI)


# ---------------------------------------------------------------------------
# FILES — upsert (the big one: 4 copies consolidated into 1)
# ---------------------------------------------------------------------------

# Standard upsert for scan results — 12 positional params from process_single_file()
# Conditional logic: if mtime changed significantly (>0.1s), reset favourites and AI data
FILES_UPSERT = """
    INSERT INTO files (id, path, mtime, name, type, duration, dimensions,
                       has_workflow, size, last_scanned, workflow_files, workflow_prompt)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        path = excluded.path,
        name = excluded.name,
        type = excluded.type,
        duration = excluded.duration,
        dimensions = excluded.dimensions,
        has_workflow = excluded.has_workflow,
        size = excluded.size,
        last_scanned = excluded.last_scanned,
        workflow_files = excluded.workflow_files,
        workflow_prompt = excluded.workflow_prompt,
        is_favorite = CASE
            WHEN ABS(files.mtime - excluded.mtime) > 0.1 THEN 0
            ELSE files.is_favorite
        END,
        ai_caption = CASE
            WHEN ABS(files.mtime - excluded.mtime) > 0.1 THEN NULL
            ELSE files.ai_caption
        END,
        ai_embedding = CASE
            WHEN ABS(files.mtime - excluded.mtime) > 0.1 THEN NULL
            ELSE files.ai_embedding
        END,
        ai_last_scanned = CASE
            WHEN ABS(files.mtime - excluded.mtime) > 0.1 THEN 0
            ELSE files.ai_last_scanned
        END,
        mtime = excluded.mtime
"""

# Full insert for copy operations — 17 positional params (includes AI + favourite columns)
FILES_INSERT_FULL = """
    INSERT INTO files (
        id, path, mtime, name, type, duration, dimensions, has_workflow,
        size, is_favorite, last_scanned, workflow_files, workflow_prompt,
        ai_last_scanned, ai_caption, ai_embedding, ai_error
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

# Merge update — overwrites an existing record with full metadata (move/rename collision)
# 16 params: path, name, mtime, size, has_workflow, is_favorite, type, duration, dimensions,
#            ai_last_scanned, ai_caption, ai_embedding, ai_error, workflow_files, workflow_prompt, id
FILES_MERGE_UPDATE = """
    UPDATE files
    SET path = ?, name = ?, mtime = ?,
        size = ?, has_workflow = ?, is_favorite = ?,
        type = ?, duration = ?, dimensions = ?,
        ai_last_scanned = ?, ai_caption = ?, ai_embedding = ?, ai_error = ?,
        workflow_files = ?, workflow_prompt = ?
    WHERE id = ?
"""

# Simple path/name/id update (standard move/rename, no collision)
FILES_UPDATE_PATH = "UPDATE files SET id = ?, path = ?, name = ? WHERE id = ?"

# ---------------------------------------------------------------------------
# FILES — reads
# ---------------------------------------------------------------------------

# Gallery view — uses v_files (excludes ai_embedding blob)
FILES_SELECT_GALLERY = "SELECT * FROM v_files {where_clause} ORDER BY {sort_by} {sort_order}"

# Batch fetch with AI data (for move/copy that preserves AI metadata)
FILES_SELECT_BATCH_WITH_AI = """
    SELECT * FROM v_files_ai WHERE id IN ({placeholders})
"""

# Batch fetch paths only (for delete, zip)
FILES_SELECT_PATHS_BATCH = "SELECT id, path FROM files WHERE id IN ({placeholders})"
FILES_SELECT_PATH_NAME_BATCH = "SELECT path, name FROM files WHERE id IN ({placeholders})"

# Single file lookups
FILES_SELECT_BY_ID = "SELECT {columns} FROM files WHERE id = ?"
FILES_SELECT_PATH_BY_ID = "SELECT path FROM files WHERE id = ?"
FILES_EXISTS_BY_ID = "SELECT id FROM files WHERE id = ?"

# Metadata for rename (all columns except id, via v_files_ai to include embedding)
FILES_SELECT_METADATA_FOR_RENAME = """
    SELECT path, name, size, has_workflow, is_favorite, type, duration, dimensions,
           ai_last_scanned, ai_caption, ai_embedding, ai_error, workflow_files, workflow_prompt
    FROM files WHERE id = ?
"""

# Favourite operations
FILES_SELECT_FAVORITE = "SELECT is_favorite FROM files WHERE id = ?"
FILES_UPDATE_FAVORITE = "UPDATE files SET is_favorite = ? WHERE id = ?"
FILES_UPDATE_FAVORITE_BATCH = "UPDATE files SET is_favorite = ? WHERE id IN ({placeholders})"

# Thumbnail/media lookups
FILES_SELECT_FOR_THUMBNAIL = "SELECT path, mtime, type FROM files WHERE id = ?"
FILES_SELECT_FOR_METADATA = "SELECT path, has_workflow, ai_caption, ai_last_scanned FROM files WHERE id = ?"

# Count
FILES_COUNT = "SELECT COUNT(*) FROM files"

# Sync queries
FILES_SELECT_PATH_MTIME_ALL = "SELECT path, mtime FROM files"
FILES_SELECT_PATH_MTIME_FOLDER = "SELECT path, mtime FROM files WHERE path LIKE ?"
FILES_SELECT_PATH_LASTSCAN_FOLDER = "SELECT path, last_scanned FROM files WHERE path LIKE ?"

# Delete
FILES_DELETE_BY_ID = "DELETE FROM files WHERE id = ?"
FILES_DELETE_BY_ID_BATCH = "DELETE FROM files WHERE id IN ({placeholders})"
FILES_DELETE_BY_PATH = "DELETE FROM files WHERE path = ?"
FILES_DELETE_BY_PATH_LIKE = "DELETE FROM files WHERE path LIKE ?"

# Folder rename/move — full table scan (needed for path prefix rewrite)
FILES_SELECT_ID_PATH_ALL = "SELECT id, path FROM files"

# AI search
FILES_SELECT_AI_SEARCH = """
    SELECT f.*, r.score FROM ai_search_results r
    JOIN files f ON r.file_id = f.id
    WHERE r.session_id = ? ORDER BY r.score DESC
"""

# AI reset/wipe
FILES_WIPE_AI_BATCH = """
    UPDATE files SET ai_caption=NULL, ai_embedding=NULL, ai_last_scanned=0, ai_error=NULL
    WHERE id IN ({placeholders})
"""

# AI lookup (background watcher)
FILES_SELECT_AI_STATUS = "SELECT id, mtime, ai_last_scanned FROM files WHERE path = ?"
FILES_SELECT_AI_STATUS_NORMALIZED = """
    SELECT id, mtime, ai_last_scanned FROM files WHERE REPLACE(path, '\\', '/') = ?
"""
FILES_SELECT_AI_INDEXED = """
    SELECT id, path FROM files WHERE ai_caption IS NOT NULL OR ai_embedding IS NOT NULL
"""

# ---------------------------------------------------------------------------
# AI SEARCH QUEUE
# ---------------------------------------------------------------------------
AI_SEARCH_QUEUE_INSERT = """
    INSERT INTO ai_search_queue (session_id, query, limit_results, status)
    VALUES (?, ?, ?, 'pending')
"""
AI_SEARCH_QUEUE_SELECT_STATUS = "SELECT status FROM ai_search_queue WHERE session_id = ?"
AI_SEARCH_QUEUE_SELECT_INFO = "SELECT query, status FROM ai_search_queue WHERE session_id = ?"
AI_SEARCH_QUEUE_CLEANUP = "DELETE FROM ai_search_queue WHERE created_at < datetime('now', '-1 hour')"
AI_SEARCH_RESULTS_CLEANUP = """
    DELETE FROM ai_search_results WHERE session_id NOT IN (SELECT session_id FROM ai_search_queue)
"""

# ---------------------------------------------------------------------------
# AI INDEXING QUEUE
# ---------------------------------------------------------------------------
AI_INDEX_QUEUE_UPSERT = """
    INSERT INTO ai_indexing_queue (file_path, file_id, status, created_at, force_index, params)
    VALUES (?, ?, 'pending', ?, 0, '{}')
    ON CONFLICT(file_path) DO UPDATE SET
        status = 'pending',
        file_id = excluded.file_id,
        created_at = excluded.created_at
"""
AI_INDEX_QUEUE_UPSERT_FORCE = """
    INSERT INTO ai_indexing_queue (file_path, file_id, status, force_index, created_at, updated_at, params)
    VALUES (?, ?, 'pending', ?, ?, ?, '{}')
    ON CONFLICT(file_path) DO UPDATE SET
        status = 'pending',
        force_index = excluded.force_index,
        file_id = excluded.file_id,
        created_at = excluded.created_at,
        updated_at = excluded.updated_at
"""
AI_INDEX_QUEUE_CHECK_ACTIVE = """
    SELECT 1 FROM ai_indexing_queue
    WHERE file_path = ? AND status IN ('pending', 'processing', 'waiting_gpu')
"""
AI_INDEX_QUEUE_DELETE_BY_PATH = "DELETE FROM ai_indexing_queue WHERE file_path = ? OR file_path LIKE ?"
AI_INDEX_QUEUE_DELETE_BY_FILE_BATCH = "DELETE FROM ai_indexing_queue WHERE file_id IN ({placeholders})"
AI_INDEX_QUEUE_DELETE_COMPLETED_OLD = "DELETE FROM ai_indexing_queue WHERE status='completed' AND created_at < ?"
AI_INDEX_QUEUE_DELETE_NON_PROCESSING = "DELETE FROM ai_indexing_queue WHERE status != 'processing'"
AI_INDEX_QUEUE_RESUME_GPU = "UPDATE ai_indexing_queue SET status='pending' WHERE status='waiting_gpu'"
AI_INDEX_QUEUE_COUNT_PENDING = "SELECT COUNT(*) FROM ai_indexing_queue WHERE status='pending'"
AI_INDEX_QUEUE_CURRENT = "SELECT file_path FROM ai_indexing_queue WHERE status='processing'"
AI_INDEX_QUEUE_PEEK = """
    SELECT file_path, force_index FROM ai_indexing_queue
    WHERE status='pending' ORDER BY force_index DESC, created_at ASC LIMIT 10
"""
AI_INDEX_QUEUE_COUNT_GPU = "SELECT COUNT(*) FROM ai_indexing_queue WHERE status='waiting_gpu'"

# ---------------------------------------------------------------------------
# AI WATCHED FOLDERS
# ---------------------------------------------------------------------------
AI_WATCHED_SELECT = "SELECT path, recursive FROM ai_watched_folders"
AI_WATCHED_SELECT_PATHS = "SELECT path FROM ai_watched_folders"
AI_WATCHED_INSERT = "INSERT OR REPLACE INTO ai_watched_folders (path, recursive, added_at) VALUES (?, ?, ?)"
AI_WATCHED_UPDATE_RECURSIVE = "UPDATE ai_watched_folders SET recursive=1 WHERE path=?"
AI_WATCHED_DELETE = "DELETE FROM ai_watched_folders WHERE path=?"
AI_WATCHED_DELETE_LIKE = "DELETE FROM ai_watched_folders WHERE path LIKE ?"
AI_WATCHED_UPDATE_PATH = "UPDATE ai_watched_folders SET path = ? WHERE path = ?"

# ---------------------------------------------------------------------------
# AI METADATA
# ---------------------------------------------------------------------------
AI_METADATA_SELECT = "SELECT value FROM ai_metadata WHERE key=?"
AI_METADATA_UPSERT = "INSERT OR REPLACE INTO ai_metadata (key, value) VALUES (?, ?)"

# ---------------------------------------------------------------------------
# MOUNTED FOLDERS
# ---------------------------------------------------------------------------
MOUNTED_INSERT = "INSERT OR REPLACE INTO mounted_folders (path, target_source, created_at) VALUES (?, ?, ?)"
MOUNTED_SELECT_ALL = "SELECT path FROM mounted_folders"
MOUNTED_SELECT_BY_PATH = "SELECT path FROM mounted_folders WHERE path = ?"
MOUNTED_DELETE = "DELETE FROM mounted_folders WHERE path = ?"

# ---------------------------------------------------------------------------
# EVENT LOG
# ---------------------------------------------------------------------------
EVENT_LOG_INSERT = """
    INSERT INTO event_log (id, timestamp, event_type, data, source) VALUES (?, ?, ?, ?, ?)
"""
EVENT_LOG_PRUNE = "DELETE FROM event_log WHERE timestamp < ?"
