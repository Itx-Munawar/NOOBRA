"""Conversation memory manager for NOOBRA.

Wraps the SQLite store in :mod:`noobra.memory.database` with a small,
safe API used by the rest of the agent: conversation history, preferences,
task summaries and command shortcuts.

Security rule: keys that look like credentials (``API_KEY``, ``password``,
``token``, ``secret``) are never persisted. Such writes are refused with
a warning log and return ``False``. When ``enabled=False`` every method
is a safe no-op (reads return empty / default values).
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import get_connection, get_db_path, init_db

logger = logging.getLogger("noobra.memory")

# Substrings (case-insensitive) that mark a key as credential-like.
_SENSITIVE_KEY_MARKERS = ("API_KEY", "APIKEY", "PASSWORD", "PASSWD", "TOKEN",
                          "SECRET", "PRIVATE_KEY", "CREDENTIAL")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_sensitive_key(key: str) -> bool:
    upper = str(key).upper()
    return any(marker in upper for marker in _SENSITIVE_KEY_MARKERS)


class MemoryManager:
    """SQLite-backed memory. ``db_path=None`` uses the default location."""

    def __init__(self, db_path: str | Path | None = None, enabled: bool = True):
        self.db_path = Path(db_path) if db_path is not None else get_db_path()
        self._enabled = bool(enabled)
        if self._enabled:
            init_db(self.db_path)

    # -- enable / disable -------------------------------------------------
    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable memory. Disabling makes all methods no-ops."""
        self._enabled = bool(enabled)
        if self._enabled:
            init_db(self.db_path)
        logger.info("Memory %s", "enabled" if self._enabled else "disabled")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    # -- internal ---------------------------------------------------------
    def _connect(self) -> sqlite3.Connection | None:
        if not self._enabled:
            return None
        return get_connection(self.db_path)

    # -- conversation history ---------------------------------------------
    def add_message(self, role: str, content: str) -> bool:
        """Append one message (``role`` e.g. ``"user"``/``"assistant"``)."""
        if not self._enabled:
            return False
        if not content:
            return False
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO conversations (role, content, created_at)"
                " VALUES (?, ?, ?)",
                (str(role), str(content), _utcnow_iso()),
            )
            conn.commit()
            return True
        except sqlite3.Error:
            logger.exception("Failed to add message")
            return False
        finally:
            conn.close()

    def get_history(self, limit: int = 50) -> list[dict]:
        """Return the most recent ``limit`` messages, oldest first."""
        if not self._enabled:
            return []
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, role, content, created_at FROM conversations"
                " ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]
        except sqlite3.Error:
            logger.exception("Failed to read history")
            return []
        finally:
            conn.close()

    def search_history(self, query: str, limit: int = 10) -> list[dict]:
        """Case-insensitive substring search over message content/role."""
        if not self._enabled or not query:
            return []
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, role, content, created_at FROM conversations"
                " WHERE content LIKE ? OR role LIKE ?"
                " ORDER BY id DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", int(limit)),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]
        except sqlite3.Error:
            logger.exception("Failed to search history")
            return []
        finally:
            conn.close()

    def clear_history(self) -> bool:
        """Delete all conversation messages (preferences/tasks untouched)."""
        if not self._enabled:
            return False
        conn = self._connect()
        try:
            conn.execute("DELETE FROM conversations")
            conn.commit()
            return True
        except sqlite3.Error:
            logger.exception("Failed to clear history")
            return False
        finally:
            conn.close()

    # -- preferences --------------------------------------------------------
    def save_preference(self, key: str, value: Any) -> bool:
        """Store a preference. Credential-like keys are refused."""
        if not self._enabled:
            return False
        if _is_sensitive_key(key):
            logger.warning(
                "Refused to store preference with sensitive key %r", key)
            return False
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO preferences (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(key), str(value)),
            )
            conn.commit()
            return True
        except sqlite3.Error:
            logger.exception("Failed to save preference %r", key)
            return False
        finally:
            conn.close()

    def get_preference(self, key: str, default: Any = None) -> Any:
        if not self._enabled:
            return default
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT value FROM preferences WHERE key = ?", (str(key),)
            ).fetchone()
            return row["value"] if row else default
        except sqlite3.Error:
            logger.exception("Failed to read preference %r", key)
            return default
        finally:
            conn.close()

    def delete_preference(self, key: str) -> bool:
        if not self._enabled:
            return False
        conn = self._connect()
        try:
            cur = conn.execute(
                "DELETE FROM preferences WHERE key = ?", (str(key),))
            conn.commit()
            return cur.rowcount > 0
        except sqlite3.Error:
            logger.exception("Failed to delete preference %r", key)
            return False
        finally:
            conn.close()

    # -- task summaries -----------------------------------------------------
    def save_task_summary(self, summary: str, status: str = "done") -> bool:
        if not self._enabled:
            return False
        if not summary:
            return False
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO tasks (summary, status, created_at)"
                " VALUES (?, ?, ?)",
                (str(summary), str(status), _utcnow_iso()),
            )
            conn.commit()
            return True
        except sqlite3.Error:
            logger.exception("Failed to save task summary")
            return False
        finally:
            conn.close()

    def get_task_summaries(self, limit: int = 20) -> list[dict]:
        if not self._enabled:
            return []
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, summary, status, created_at FROM tasks"
                " ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            logger.exception("Failed to read task summaries")
            return []
        finally:
            conn.close()

    # -- shortcuts ----------------------------------------------------------
    def save_shortcut(self, name: str, command: str) -> bool:
        if not self._enabled:
            return False
        if not name or not command:
            return False
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO shortcuts (name, command) VALUES (?, ?)"
                " ON CONFLICT(name) DO UPDATE SET command = excluded.command",
                (str(name), str(command)),
            )
            conn.commit()
            return True
        except sqlite3.Error:
            logger.exception("Failed to save shortcut %r", name)
            return False
        finally:
            conn.close()

    def get_shortcut(self, name: str) -> str | None:
        if not self._enabled:
            return None
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT command FROM shortcuts WHERE name = ?", (str(name),)
            ).fetchone()
            return row["command"] if row else None
        except sqlite3.Error:
            logger.exception("Failed to read shortcut %r", name)
            return None
        finally:
            conn.close()

    def list_shortcuts(self) -> list[dict]:
        if not self._enabled:
            return []
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT name, command FROM shortcuts ORDER BY name"
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            logger.exception("Failed to list shortcuts")
            return []
        finally:
            conn.close()

    # -- wipe ----------------------------------------------------------------
    def clear_all(self) -> bool:
        """Delete history, preferences, tasks and shortcuts (not audit log)."""
        if not self._enabled:
            return False
        conn = self._connect()
        try:
            for table in ("conversations", "preferences", "tasks", "shortcuts"):
                conn.execute(f"DELETE FROM {table}")
            conn.commit()
            return True
        except sqlite3.Error:
            logger.exception("Failed to clear memory")
            return False
        finally:
            conn.close()
