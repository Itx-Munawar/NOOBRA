"""NOOBRA memory package: SQLite-backed conversation, preference,
task-summary and shortcut storage.

Public API (see ``database`` / ``manager``):
``get_db_path``, ``init_db``, ``get_connection``, ``MemoryManager``.
"""

from .database import get_app_data_dir, get_db_path, get_connection, init_db
from .manager import MemoryManager

__all__ = [
    "MemoryManager",
    "get_app_data_dir",
    "get_db_path",
    "get_connection",
    "init_db",
]
