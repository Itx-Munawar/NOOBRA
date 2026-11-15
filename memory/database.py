"""SQLite storage layer for NOOBRA.

The database lives at ``app_data_dir()/noobra.db`` where ``app_data_dir``
is ``%APPDATA%/NOOBRA`` on Windows and ``~/.noobra`` elsewhere.  This
module intentionally duplicates that tiny path logic instead of importing
``core.config`` at module level, to avoid import cycles.

Tables (created by :func:`init_db`):
``conversations``, ``preferences``, ``tasks``, ``settings``,
``shortcuts`` and ``audit_log``.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger("noobra.memory")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    summary TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'done',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shortcuts (
    name TEXT PRIMARY KEY,
    command TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'SAFE',
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""


def get_app_data_dir() -> Path:
    """Return NOOBRA's per-user data directory (created if missing)."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        path = Path(base) / "NOOBRA"
    else:
        path = Path.home() / ".noobra"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_db_path() -> Path:
    """Return the path of the NOOBRA SQLite database."""
    return get_app_data_dir() / "noobra.db"


def init_db(db_path: str | Path | None = None) -> Path:
    """Create the database file and all tables if they do not exist.

    Returns the resolved database path. Safe to call repeatedly.
    """
    path = Path(db_path) if db_path is not None else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
    logger.debug("Database initialised at %s", path)
    return path


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Return a SQLite connection with ``sqlite3.Row`` row factory.

    Ensures the schema exists first. Callers own closing the connection
    (use as a context manager or call ``.close()``).
    """
    path = Path(db_path) if db_path is not None else get_db_path()
    init_db(path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn
