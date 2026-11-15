"""Audit logging for NOOBRA.

Every audited action is written to two places:
1. the ``audit_log`` table in the NOOBRA SQLite database
   (``memory.database`` -- imported lazily inside functions so this
   module never creates an import cycle), and
2. a plain-text file ``<app_data_dir>/logs/audit.log`` (dirs created).

Levels are free-form strings; the conventional set is ``SAFE``,
``RISKY`` and ``BLOCKED``. All writes also go through the standard
``logging`` logger ``noobra.security``.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("noobra.security")

_VALID_LEVELS = ("SAFE", "RISKY", "BLOCKED", "INFO", "WARNING", "ERROR")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit_log_path(db_path: str | Path | None = None) -> Path:
    """<app_data_dir>/logs/audit.log (next to the DB's data dir)."""
    if db_path is not None:
        return Path(db_path).parent / "logs" / "audit.log"
    try:
        from ..memory.database import get_app_data_dir
        base = get_app_data_dir()
    except Exception:
        base = Path.home() / ".noobra"
    return base / "logs" / "audit.log"


def _ensure_table(db_path: str | Path | None) -> Path:
    try:
        from ..memory.database import init_db
        return init_db(db_path)
    except Exception:
        # Fallback: create just the audit_log table ourselves.
        from ..memory.database import get_db_path
        path = Path(db_path) if db_path is not None else get_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS audit_log ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " action TEXT NOT NULL, level TEXT NOT NULL DEFAULT 'SAFE',"
                " details TEXT NOT NULL DEFAULT '',"
                " created_at TEXT NOT NULL)")
            conn.commit()
        finally:
            conn.close()
        return path


def log_action(action: str, level: str = "SAFE", details: str = "",
               db_path: str | Path | None = None) -> bool:
    """Record an action in the DB and the audit log file. Returns success."""
    level = str(level or "SAFE").upper()
    if level not in _VALID_LEVELS:
        level = "SAFE"
    action = str(action or "")
    details = str(details or "")
    if level == "BLOCKED":
        logger.warning("AUDIT [%s] %s -- %s", level, action, details)
    elif level in ("RISKY", "WARNING", "ERROR"):
        logger.warning("AUDIT [%s] %s -- %s", level, action, details)
    else:
        logger.info("AUDIT [%s] %s -- %s", level, action, details)

    path = _ensure_table(db_path)
    ok_db = False
    try:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                "INSERT INTO audit_log (action, level, details, created_at)"
                " VALUES (?, ?, ?, ?)",
                (action, level, details, _utcnow_iso()))
            conn.commit()
            ok_db = True
        finally:
            conn.close()
    except sqlite3.Error:
        logger.exception("Failed to write audit entry to DB")

    ok_file = False
    try:
        log_file = _audit_log_path(db_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(f"{_utcnow_iso()} [{level}] {action} -- {details}\n")
        ok_file = True
    except OSError:
        logger.exception("Failed to write audit entry to log file")
    return ok_db or ok_file


def list_actions(limit: int = 50, level: str | None = None,
                 db_path: str | Path | None = None) -> list[dict]:
    """Return the most recent audit entries, newest first."""
    path = _ensure_table(db_path)
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            if level:
                rows = conn.execute(
                    "SELECT id, action, level, details, created_at"
                    " FROM audit_log WHERE level = ?"
                    " ORDER BY id DESC LIMIT ?",
                    (str(level).upper(), int(limit))).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, action, level, details, created_at"
                    " FROM audit_log ORDER BY id DESC LIMIT ?",
                    (int(limit),)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except sqlite3.Error:
        logger.exception("Failed to list audit entries")
        return []


def clear_audit_log(db_path: str | Path | None = None) -> bool:
    """Delete all audit entries from the DB (log file is left intact)."""
    path = _ensure_table(db_path)
    try:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("DELETE FROM audit_log")
            conn.commit()
            return True
        finally:
            conn.close()
    except sqlite3.Error:
        logger.exception("Failed to clear audit log")
        return False
