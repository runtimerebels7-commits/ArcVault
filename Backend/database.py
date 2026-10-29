import os
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "arcvault.db"
_raw_database = os.environ.get("DATABASE_PATH")
if _raw_database:
    _candidate = Path(_raw_database).expanduser()
    DATABASE = str((_candidate if _candidate.is_absolute() else PROJECT_ROOT / _candidate).resolve())
else:
    DATABASE = str(DEFAULT_DATABASE)



def connect():
    Path(DATABASE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS publishers (
            publisher_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS publications (
            publication_id TEXT PRIMARY KEY,
            publisher_id TEXT NOT NULL,
            title TEXT NOT NULL,
            language TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            licence_type TEXT NOT NULL,
            licence_terms TEXT NOT NULL,
            licensing_cost REAL NOT NULL CHECK (licensing_cost >= 0),
            value_score REAL NOT NULL CHECK (value_score >= 0),
            allowed_uses_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            rights_verified INTEGER NOT NULL DEFAULT 0,
            signature_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
            rights_record_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (publisher_id) REFERENCES publishers(publisher_id)
        );

        CREATE TABLE IF NOT EXISTS activity_events (
            event_id TEXT PRIMARY KEY,
            publication_id TEXT NOT NULL,
            publisher_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (publication_id) REFERENCES publications(publication_id),
            FOREIGN KEY (publisher_id) REFERENCES publishers(publisher_id)
        );

        CREATE TABLE IF NOT EXISTS access_requests (
            request_id TEXT PRIMARY KEY,
            publication_id TEXT NOT NULL,
            publisher_id TEXT NOT NULL,
            intended_use TEXT NOT NULL,
            decision TEXT NOT NULL,
            reason TEXT NOT NULL,
            buyer_reference TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (publication_id) REFERENCES publications(publication_id),
            FOREIGN KEY (publisher_id) REFERENCES publishers(publisher_id)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            publication_id TEXT NOT NULL,
            publisher_id TEXT NOT NULL,
            amount REAL NOT NULL CHECK (amount >= 0),
            status TEXT NOT NULL,
            is_demo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (publication_id) REFERENCES publications(publication_id),
            FOREIGN KEY (publisher_id) REFERENCES publishers(publisher_id)
        );

        CREATE TABLE IF NOT EXISTS permission_checks (
            check_id TEXT PRIMARY KEY,
            publication_id TEXT NOT NULL,
            intended_use TEXT NOT NULL,
            decision TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            log_id TEXT PRIMARY KEY,
            publisher_id TEXT,
            publication_id TEXT,
            action TEXT NOT NULL,
            result TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS optimisation_runs (
            run_id TEXT PRIMARY KEY,
            budget REAL NOT NULL,
            selected_dataset_ids_json TEXT NOT NULL,
            total_cost REAL NOT NULL,
            total_value REAL NOT NULL,
            status TEXT NOT NULL,
            engine TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS corpus_manifests (
            manifest_id TEXT PRIMARY KEY,
            intended_use TEXT NOT NULL,
            accepted_json TEXT NOT NULL,
            rejected_json TEXT NOT NULL,
            optimisation_run_id TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_publications_publisher ON publications(publisher_id);
        CREATE INDEX IF NOT EXISTS idx_activity_publisher_time ON activity_events(publisher_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_transactions_publisher_time ON transactions(publisher_id, created_at);
        """)
        # Safe migration for databases created by an earlier ArcVault version.
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(publications)").fetchall()}
        if "rights_record_json" not in columns:
            conn.execute("ALTER TABLE publications ADD COLUMN rights_record_json TEXT")
