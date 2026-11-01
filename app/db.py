"""SQLite access + versioned migrations (PRAGMA user_version).

Migrations only ever add/convert; existing rows are preserved. Before upgrading
an existing database a timestamped copy is written next to it.
Every query in the app uses ? placeholders (never string-built SQL values).
"""
import os
import shutil
import sqlite3
from datetime import datetime

from flask import current_app, g


def connect(path):
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


# --------------------------------------------------------------------------
# Migrations
# --------------------------------------------------------------------------

def _m1_base_schema(conn):
    """Original single-user schema (idempotent; matches pre-accounts StudyOS)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            color TEXT DEFAULT '#9B7BFF',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            subject_id INTEGER,
            due_date TEXT,
            priority TEXT DEFAULT 'Medium',
            completed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT DEFAULT '',
            subject_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS study_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER,
            duration INTEGER NOT NULL,
            studied_on TEXT NOT NULL,
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS flashcards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        );
        """
    )


def _m2_accounts(conn):
    """Users, per-user settings, rate limiting, and user_id ownership columns."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_login_at TEXT
        );
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            focus_min INTEGER NOT NULL DEFAULT 25,
            short_min INTEGER NOT NULL DEFAULT 5,
            long_min INTEGER NOT NULL DEFAULT 15,
            sessions_before_long INTEGER NOT NULL DEFAULT 4,
            auto_start_breaks INTEGER NOT NULL DEFAULT 0,
            auto_start_focus INTEGER NOT NULL DEFAULT 0,
            sound_enabled INTEGER NOT NULL DEFAULT 1,
            ambient TEXT NOT NULL DEFAULT 'off',
            ambient_volume INTEGER NOT NULL DEFAULT 35,
            bg_preset TEXT NOT NULL DEFAULT 'cosmic-night',
            bg_animated INTEGER NOT NULL DEFAULT 1,
            bg_intensity INTEGER NOT NULL DEFAULT 70,
            reduce_motion INTEGER NOT NULL DEFAULT 0,
            accent TEXT NOT NULL DEFAULT 'violet'
        );
        CREATE TABLE IF NOT EXISTS rate_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bucket TEXT NOT NULL,
            key TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_rate_limits
            ON rate_limits(bucket, key, created_at);
        """
    )
    for table in ("subjects", "tasks", "notes", "study_sessions"):
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN user_id INTEGER "
            "REFERENCES users(id) ON DELETE CASCADE"
        )


def _m3_features(conn):
    """Subject descriptions, task details, session idempotency, flashcard SRS."""
    conn.execute("ALTER TABLE subjects ADD COLUMN description TEXT NOT NULL DEFAULT ''")
    conn.execute("ALTER TABLE tasks ADD COLUMN description TEXT NOT NULL DEFAULT ''")
    conn.execute("ALTER TABLE tasks ADD COLUMN completed_at TEXT")
    conn.execute("ALTER TABLE tasks ADD COLUMN updated_at TEXT")
    conn.execute("ALTER TABLE study_sessions ADD COLUMN session_key TEXT")
    conn.execute("ALTER TABLE study_sessions ADD COLUMN started_at TEXT")
    conn.execute("ALTER TABLE study_sessions ADD COLUMN created_at TEXT")
    conn.execute(
        "ALTER TABLE study_sessions ADD COLUMN kind TEXT NOT NULL DEFAULT 'focus'"
    )
    # Rebuild flashcards: add ownership + spaced-repetition fields, and make
    # deleting a subject keep its cards (subject_id -> NULL) instead of cascading.
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript(
        """
        BEGIN;
        CREATE TABLE flashcards_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            box INTEGER NOT NULL DEFAULT 0,
            due_on TEXT,
            reviews INTEGER NOT NULL DEFAULT 0,
            lapses INTEGER NOT NULL DEFAULT 0,
            last_reviewed TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        INSERT INTO flashcards_new (id, subject_id, question, answer, created_at)
            SELECT id, subject_id, question, answer, CURRENT_TIMESTAMP FROM flashcards;
        DROP TABLE flashcards;
        ALTER TABLE flashcards_new RENAME TO flashcards;
        COMMIT;
        """
    )
    conn.execute("PRAGMA foreign_keys = ON")


def _m4_indexes(conn):
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_subjects_user ON subjects(user_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_user_due ON tasks(user_id, completed, due_date);
        CREATE INDEX IF NOT EXISTS idx_notes_user_upd ON notes(user_id, updated_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_user_day ON study_sessions(user_id, studied_on);
        CREATE INDEX IF NOT EXISTS idx_cards_user_due ON flashcards(user_id, due_on);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_key
            ON study_sessions(user_id, session_key) WHERE session_key IS NOT NULL;
        """
    )


MIGRATIONS = [_m1_base_schema, _m2_accounts, _m3_features, _m4_indexes]
SCHEMA_VERSION = len(MIGRATIONS)


def _has_user_tables(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='subjects'"
    ).fetchone()[0] > 0


def migrate(path):
    """Bring the database at `path` up to SCHEMA_VERSION. Safe to call repeatedly."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = connect(path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= SCHEMA_VERSION:
            return
        if os.path.isfile(path) and _has_user_tables(conn):
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(path, f"{path}.backup-{stamp}")
        for number, migration in enumerate(MIGRATIONS, start=1):
            if version < number:
                migration(conn)
                conn.execute(f"PRAGMA user_version = {number}")
                conn.commit()
    finally:
        conn.close()


def adopt_legacy_rows(conn, user_id):
    """Give pre-accounts (user_id IS NULL) data to the first account created."""
    for table in ("subjects", "tasks", "notes", "study_sessions", "flashcards"):
        conn.execute(f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL", (user_id,))
