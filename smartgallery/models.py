# Smart Gallery for ComfyUI - Database Operations
# SQLite connection, schema creation, and migrations.

import sqlite3
import threading
from smartgallery.config import DATABASE_FILE, DB_SCHEMA_VERSION

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
                workflow_prompt TEXT DEFAULT '',
                ai_last_scanned REAL DEFAULT 0,
                ai_caption TEXT,
                ai_embedding BLOB,
                ai_error TEXT
            )
        ''')

        # 2. AI TABLE CREATION
        conn.execute('''
            CREATE TABLE IF NOT EXISTS ai_search_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL UNIQUE,
                query TEXT NOT NULL,
                limit_results INTEGER DEFAULT 100,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP NULL
            );
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS ai_search_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                score REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES ai_search_queue(session_id)
            );
        ''')

        conn.execute('CREATE INDEX IF NOT EXISTS idx_queue_status ON ai_search_queue(status);')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_results_session ON ai_search_results(session_id);')

        # File indexes for fast folder queries and sorting
        conn.execute('CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_files_mtime ON files(mtime);')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_files_name ON files(name);')
        # Note: workflow_files and workflow_prompt are NOT indexed because keyword search uses
        # LIKE '%keyword%' (leading wildcard), which forces a full table scan regardless of
        # B-tree indexes. FTS5 virtual table is the correct future solution for this.

        conn.execute('''
            CREATE TABLE IF NOT EXISTS ai_indexing_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                file_id TEXT,
                status TEXT DEFAULT 'pending',
                force_index INTEGER DEFAULT 0,
                params TEXT DEFAULT '{}',
                created_at REAL,
                updated_at REAL,
                error_msg TEXT,
                UNIQUE(file_path) ON CONFLICT REPLACE
            );
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_ai_idx_status ON ai_indexing_queue(status);')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS ai_watched_folders (
                path TEXT PRIMARY KEY,
                recursive INTEGER DEFAULT 0,
                added_at REAL
            );
        ''')

        conn.execute("CREATE TABLE IF NOT EXISTS ai_metadata (key TEXT PRIMARY KEY, value TEXT, updated_at REAL)")

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

        # 3. COLUMN MIGRATION
        required_columns = {
            'size': 'INTEGER DEFAULT 0',
            'last_scanned': 'REAL DEFAULT 0',
            'workflow_files': "TEXT DEFAULT ''",
            'workflow_prompt': "TEXT DEFAULT ''",
            'ai_last_scanned': 'REAL DEFAULT 0',
            'ai_caption': 'TEXT',
            'ai_embedding': 'BLOB',
            'ai_error': 'TEXT'
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
                conn.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION}")
        except Exception as e:
            print(f"WARNING: Could not update DB schema version: {e}")

        conn.commit()

    except Exception as e:
        print(f"CRITICAL DATABASE ERROR: {e}")

    finally:
        if close_conn: conn.close()
