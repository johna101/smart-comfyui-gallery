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
           workflow_files, workflow_prompt
    FROM files
"""


def init_views(conn):
    """Create all SQL views. Called from init_db() after table creation."""
    conn.execute(CREATE_VIEW_FILES)


# ---------------------------------------------------------------------------
# FILES — upsert (the big one: 4 copies consolidated into 1)
# ---------------------------------------------------------------------------

# Standard upsert for scan results — 12 positional params from process_single_file()
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
        mtime = excluded.mtime
"""

# Full insert for copy operations — 13 positional params (includes favourite column)
FILES_INSERT_FULL = """
    INSERT INTO files (
        id, path, mtime, name, type, duration, dimensions, has_workflow,
        size, is_favorite, last_scanned, workflow_files, workflow_prompt
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

# Merge update — overwrites an existing record with full metadata (move/rename collision)
# 12 params: path, name, mtime, size, has_workflow, is_favorite, type, duration, dimensions,
#            workflow_files, workflow_prompt, id
FILES_MERGE_UPDATE = """
    UPDATE files
    SET path = ?, name = ?, mtime = ?,
        size = ?, has_workflow = ?, is_favorite = ?,
        type = ?, duration = ?, dimensions = ?,
        workflow_files = ?, workflow_prompt = ?
    WHERE id = ?
"""

# Simple path/name/id update (standard move/rename, no collision)
FILES_UPDATE_PATH = "UPDATE files SET id = ?, path = ?, name = ? WHERE id = ?"

# ---------------------------------------------------------------------------
# FILES — reads
# ---------------------------------------------------------------------------

# Gallery view — uses v_files (clean column set)
FILES_SELECT_GALLERY = "SELECT * FROM v_files {where_clause} ORDER BY {sort_by} {sort_order}"

# Batch fetch for move/copy (preserves all metadata)
FILES_SELECT_BATCH = """
    SELECT * FROM v_files WHERE id IN ({placeholders})
"""

# Batch fetch paths only (for delete, zip)
FILES_SELECT_PATHS_BATCH = "SELECT id, path FROM files WHERE id IN ({placeholders})"
FILES_SELECT_PATH_NAME_BATCH = "SELECT path, name FROM files WHERE id IN ({placeholders})"

# Single file lookups
FILES_SELECT_BY_ID = "SELECT {columns} FROM files WHERE id = ?"
FILES_SELECT_PATH_BY_ID = "SELECT path FROM files WHERE id = ?"
FILES_EXISTS_BY_ID = "SELECT id FROM files WHERE id = ?"

# Metadata for rename (all operational columns)
FILES_SELECT_METADATA_FOR_RENAME = """
    SELECT path, name, size, has_workflow, is_favorite, type, duration, dimensions,
           workflow_files, workflow_prompt
    FROM files WHERE id = ?
"""

# Favourite operations
FILES_SELECT_FAVORITE = "SELECT is_favorite FROM files WHERE id = ?"
FILES_UPDATE_FAVORITE = "UPDATE files SET is_favorite = ? WHERE id = ?"
FILES_UPDATE_FAVORITE_BATCH = "UPDATE files SET is_favorite = ? WHERE id IN ({placeholders})"

# Thumbnail/media lookups
FILES_SELECT_FOR_THUMBNAIL = "SELECT path, mtime, type FROM files WHERE id = ?"
FILES_SELECT_FOR_METADATA = "SELECT path, has_workflow FROM files WHERE id = ?"

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
