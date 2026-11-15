"""Tests for memory.manager — tmp SQLite DB, no real user data.

Interface note (verified against the shipped workstream): history uses
``add_message(role, content)`` / ``get_history()`` / ``clear_history()``,
preferences use ``save_preference`` / ``get_preference``, shortcuts use
``save_shortcut`` / ``get_shortcut`` / ``list_shortcuts``, and a full
wipe is ``clear_all()``. Sensitive keys are *refused* (``save_preference``
returns False) rather than raising.
"""

import pytest

pytest.importorskip("memory.manager", reason="memory.manager not implemented yet")

from memory.manager import MemoryManager  # noqa: E402


def _manager(tmp_path, enabled=True):
    return MemoryManager(db_path=str(tmp_path / "mem.db"), enabled=enabled)


def test_add_and_get_history(tmp_path):
    mem = _manager(tmp_path)
    assert mem.add_message("user", "hello") is True
    assert mem.add_message("assistant", "hi there") is True
    history = mem.get_history()
    assert len(history) >= 2
    assert "hello" in str(history)


def test_preferences(tmp_path):
    mem = _manager(tmp_path)
    assert mem.save_preference("language", "roman urdu") is True
    assert mem.get_preference("language") == "roman urdu"


def test_shortcuts(tmp_path):
    mem = _manager(tmp_path)
    assert mem.save_shortcut("open chrome", "open_app chrome") is True
    assert mem.get_shortcut("open chrome") == "open_app chrome"
    assert any(s["name"] == "open chrome" for s in mem.list_shortcuts())


def test_clear(tmp_path):
    mem = _manager(tmp_path)
    mem.add_message("user", "hello")
    assert mem.clear_all() is True
    assert mem.get_history() == []


def test_disabled_mode_noops(tmp_path):
    mem = _manager(tmp_path, enabled=False)
    assert mem.add_message("user", "hello") is False
    assert mem.save_preference("language", "roman urdu") is False
    assert mem.get_history() == []
    assert mem.get_preference("language") is None


def test_refuses_api_key_preference(tmp_path):
    mem = _manager(tmp_path)
    assert mem.save_preference("GEMINI_API_KEY", "secret-key") is False
    assert mem.get_preference("GEMINI_API_KEY") is None
