# Smart Gallery for ComfyUI - Database Operations
# SQLite connection, schema creation, and migrations.

import sqlite3
import threading
from smartgallery.config import DATABASE_FILE, DB_SCHEMA_VERSION
from smartgallery.queries import init_views

# Thread-local connection cache — avoids opening a new connection per request
_local = threading.local()


def get_db_connection():
    """Get a SQLite connection, reusing per-thread for performance."""
    conn = getattr(_local, 'conn', None)
    if conn is not None:
        try:
            conn.execute('SELECT 1')  # Test if still alive
            return conn
        except Exception:
            conn = None

    conn = sqlite3.connect(DATABASE_FILE, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA synchronous=NORMAL;')
    _local.conn = conn
    return conn


def init_db(conn=None):
    """Create tables and run migrations to the current schema version."""
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True

    try:
        # 1. CORE TABLE CREATION
        conn.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                mtime REAL NOT NULL,
                name TEXT NOT NULL,
                type TEXT,
                duration TEXT,
                dimensions TEXT,
                has_workflow INTEGER,
                is_favorite INTEGER DEFAULT 0,
                size INTEGER DEFAULT 0,
                last_scanned REAL DEFAULT 0,
                workflow_files TEXT DEFAULT '',
                workflow_prompt TEXT DEFAULT ''
            )
        ''')

        # File indexes for fast folder queries and sorting
        conn.execute('CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_files_mtime ON files(mtime);')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_files_name ON files(name);')
        # Note: workflow_files and workflow_prompt are NOT indexed because keyword search uses
        # LIKE '%keyword%' (leading wildcard), which forces a full table scan regardless of
        # B-tree indexes. FTS5 virtual table is the correct future solution for this.

        # MOUNT POINTS TABLE
        conn.execute('''
            CREATE TABLE IF NOT EXISTS mounted_folders (
                path TEXT PRIMARY KEY,
                target_source TEXT,
                created_at REAL
            );
        ''')

        # EVENT LOG TABLE — persistent audit trail for all mutations
        conn.execute('''
            CREATE TABLE IF NOT EXISTS event_log (
                id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                data TEXT NOT NULL,
                source TEXT NOT NULL
            );
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_event_log_ts ON event_log(timestamp);')

        # VIEWS — column-safe read interfaces (see queries.py)
        init_views(conn)

        # 3. COLUMN MIGRATION
        required_columns = {
            'size': 'INTEGER DEFAULT 0',
            'last_scanned': 'REAL DEFAULT 0',
            'workflow_files': "TEXT DEFAULT ''",
            'workflow_prompt': "TEXT DEFAULT ''",
            'civitai_resources': "TEXT DEFAULT ''"
        }

        cursor = conn.execute("PRAGMA table_info(files)")
        existing_columns = {row['name'] for row in cursor.fetchall()}

        for col_name, col_type in required_columns.items():
            if col_name not in existing_columns:
                print(f"INFO: Updating Database Schema... Adding missing column '{col_name}'")
                try:
                    conn.execute(f"ALTER TABLE files ADD COLUMN {col_name} {col_type}")
                except Exception as e:
                    print(f"WARNING: Could not add column {col_name}: {e}")

        # 4. SCHEMA VERSION CONTROL
        try:
            cur = conn.execute("PRAGMA user_version")
            current_ver = cur.fetchone()[0]

            if current_ver != DB_SCHEMA_VERSION:
                print(f"INFO: Updating Database Schema Version: {current_ver} -> {DB_SCHEMA_VERSION}")
                # Recreate views to pick up new columns
                conn.execute("DROP VIEW IF EXISTS v_files")
                init_views(conn)
                conn.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION}")
        except Exception as e:
            print(f"WARNING: Could not update DB schema version: {e}")

        conn.commit()

    except Exception as e:
        print(f"CRITICAL DATABASE ERROR: {e}")

    finally:
        if close_conn: conn.close()
