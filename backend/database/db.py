import os
import sqlite3

from flask import current_app, g

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


def _connect(path):
    # timeout: wait up to 10s if another request is writing (many students scan at once)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")      # readers don't block the writer
    return conn


def get_db():
    """One connection per request, closed automatically at the end."""
    if "db" not in g:
        g.db = _connect(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# Columns added after the first release. Existing databases get them automatically (data is kept).
_NEW_COLUMNS = [
    ("teachers", "require_face", "INTEGER NOT NULL DEFAULT 0"),
    ("students", "face_descriptor", "TEXT"),
    ("students", "face_enrolled_at", "TEXT"),
    ("students", "avatar", "BLOB"),
    ("students", "avatar_updated_at", "TEXT"),
    ("attendance_records", "marked_via", "TEXT NOT NULL DEFAULT 'qr'"),
    ("users", "must_change_password", "INTEGER NOT NULL DEFAULT 0"),
    ("sections", "join_code", "TEXT"),
    ("sections", "join_mode", "TEXT NOT NULL DEFAULT 'off'"),
    ("teachers", "auto_alerts", "INTEGER NOT NULL DEFAULT 0"),
    ("teachers", "weekly_summary", "INTEGER NOT NULL DEFAULT 0"),
    ("teachers", "last_summary_at", "TEXT"),
]


def _students_is_old(conn):
    """Old databases: roll_no was unique across the whole college and a login could be only ONE student."""
    for idx in conn.execute("PRAGMA index_list(students)").fetchall():
        if not idx["unique"]:
            continue
        cols = [r["name"] for r in conn.execute(f"PRAGMA index_info({idx['name']})").fetchall()]
        if cols in (["roll_no"], ["user_id"]):
            return True
    return False


_STUDENTS_NEW_DDL = """
CREATE TABLE students_new (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    roll_no    TEXT NOT NULL,
    name       TEXT NOT NULL,
    phone      TEXT,
    section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE RESTRICT,
    face_descriptor  TEXT,
    face_enrolled_at TEXT,
    avatar           BLOB,
    avatar_updated_at TEXT,
    UNIQUE (section_id, roll_no),
    UNIQUE (section_id, user_id)
)"""


def _rebuild_students(conn):
    """SQLite cannot drop a UNIQUE rule, so copy the table (ids stay the same, so all attendance data stays linked).
    This is SQLite's own recommended order: new table -> copy -> drop old -> rename new."""
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("DROP TABLE IF EXISTS students_new")
        conn.execute(_STUDENTS_NEW_DDL)
        conn.execute("""INSERT INTO students_new (id, user_id, roll_no, name, phone, section_id, face_descriptor, face_enrolled_at, avatar, avatar_updated_at)
                        SELECT id, user_id, roll_no, name, phone, section_id, face_descriptor, face_enrolled_at, avatar, avatar_updated_at
                        FROM students""")
        conn.execute("DROP TABLE students")
        conn.execute("ALTER TABLE students_new RENAME TO students")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_students_user ON students(user_id)")
        conn.commit()
        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise RuntimeError("Database upgrade failed: broken links after rebuilding the students table.")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate(conn):
    for table, column, ddl in _NEW_COLUMNS:
        have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    if _students_is_old(conn):
        _rebuild_students(conn)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_sections_join_code ON sections(join_code) WHERE join_code IS NOT NULL")
    conn.commit()


def init_db(path):
    """Create all tables and upgrade older databases (safe to run repeatedly)."""
    conn = _connect(path)
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    _migrate(conn)
    conn.commit()
    conn.close()
