"""Publisher portal tables in the shared ArcVault SQLite database."""
from pathlib import Path
import os
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parent
_raw_database = os.environ.get("DATABASE_PATH")
if _raw_database:
    _candidate = Path(_raw_database).expanduser()
    DB_PATH = (_candidate if _candidate.is_absolute() else PROJECT_ROOT / _candidate).resolve()
else:
    DB_PATH = PROJECT_ROOT / "arcvault.db"

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn

def init_db():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS portal_publishers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            backend_publisher_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS portal_sessions (
            token_hash TEXT PRIMARY KEY,
            publisher_id INTEGER NOT NULL REFERENCES portal_publishers(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS portal_datasets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publisher_id INTEGER NOT NULL REFERENCES portal_publishers(id) ON DELETE CASCADE,
            name TEXT NOT NULL, language TEXT NOT NULL, category TEXT NOT NULL,
            format TEXT NOT NULL, size TEXT NOT NULL, price REAL NOT NULL DEFAULT 0,
            licence TEXT NOT NULL, description TEXT NOT NULL, expiry_date TEXT NOT NULL,
            allowed_uses_json TEXT NOT NULL, allowed_regions_json TEXT NOT NULL,
            restricted_regions_json TEXT NOT NULL, derivative_works_allowed INTEGER NOT NULL DEFAULT 0,
            redistribution_allowed INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'active',
            version INTEGER NOT NULL DEFAULT 1, rights_record_json TEXT, signature_json TEXT,
            backend_publication_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS portal_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publisher_id INTEGER NOT NULL REFERENCES portal_publishers(id) ON DELETE CASCADE,
            dataset_id INTEGER REFERENCES portal_datasets(id) ON DELETE SET NULL,
            event_type TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}',
            amount REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Safe migrations for projects extracted from an earlier version.
        publisher_columns = {r["name"] for r in db.execute("PRAGMA table_info(portal_publishers)")}
        if "backend_publisher_id" not in publisher_columns:
            db.execute("ALTER TABLE portal_publishers ADD COLUMN backend_publisher_id TEXT")
        dataset_columns = {r["name"] for r in db.execute("PRAGMA table_info(portal_datasets)")}
        if "backend_publication_id" not in dataset_columns:
            db.execute("ALTER TABLE portal_datasets ADD COLUMN backend_publication_id TEXT")
        _migrate_legacy_portal_database(db)

def _migrate_legacy_portal_database(target_db):
    """Copy records from the pre-integration publisher-only DB when it exists."""
    legacy_path = PROJECT_ROOT / "data" / "publisher_portal.sqlite3"
    if not legacy_path.exists() or legacy_path.resolve() == DB_PATH.resolve():
        return
    try:
        legacy = sqlite3.connect(str(legacy_path))
        legacy.row_factory = sqlite3.Row
        try:
            tables = {r["name"] for r in legacy.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "publishers" not in tables or "datasets" not in tables:
                return
            publisher_cols = {r["name"] for r in legacy.execute("PRAGMA table_info(publishers)")}
            for row in legacy.execute("SELECT * FROM publishers"):
                values = dict(row)
                target_db.execute(
                    "INSERT OR IGNORE INTO portal_publishers(id,name,email,password_hash,created_at) VALUES(?,?,?,?,?)",
                    (values.get("id"), values.get("name"), values.get("email"), values.get("password_hash"), values.get("created_at", ""))
                )
            dataset_cols = {r["name"] for r in legacy.execute("PRAGMA table_info(datasets)")}
            desired = ["id","publisher_id","name","language","category","format","size","price","licence","description","expiry_date",
                       "allowed_uses_json","allowed_regions_json","restricted_regions_json","derivative_works_allowed","redistribution_allowed",
                       "status","version","rights_record_json","signature_json","created_at","updated_at"]
            for row in legacy.execute("SELECT * FROM datasets"):
                values = dict(row)
                cols = [c for c in desired if c in dataset_cols]
                placeholders = ",".join("?" for _ in cols)
                target_db.execute(
                    f"INSERT OR IGNORE INTO portal_datasets({','.join(cols)}) VALUES({placeholders})",
                    tuple(values.get(c) for c in cols)
                )
            if "activity" in tables:
                activity_cols = {r["name"] for r in legacy.execute("PRAGMA table_info(activity)")}
                desired_activity = ["id","publisher_id","dataset_id","event_type","details_json","amount","created_at"]
                for row in legacy.execute("SELECT * FROM activity"):
                    values = dict(row)
                    cols = [c for c in desired_activity if c in activity_cols]
                    placeholders = ",".join("?" for _ in cols)
                    target_db.execute(
                        f"INSERT OR IGNORE INTO portal_activity({','.join(cols)}) VALUES({placeholders})",
                        tuple(values.get(c) for c in cols)
                    )
        finally:
            legacy.close()
    except (sqlite3.Error, OSError):
        # Startup should not fail merely because an optional legacy DB is unreadable.
        return
