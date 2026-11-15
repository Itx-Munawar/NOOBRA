"""Tests for tools.files — all on tmp_path, no real user files.

Interface note (verified against the shipped workstream): the tools
return ``{"success": bool, "result": ..., "error": ...}`` dicts, not
bare paths/strings. ``search_files(directory, pattern)`` matches
*filenames* (glob or substring), not file contents.
``organize_downloads()`` takes no arguments and works on the real
``~/Downloads``, so it is tested with ``tools.files._home`` patched
to tmp_path.
"""

import pytest

pytest.importorskip("tools.files", reason="tools.files not implemented yet")

import tools.files as files_mod  # noqa: E402
from tools.files import (  # noqa: E402
    copy_file, create_folder, delete_path, find_duplicates,
    is_path_allowed, organize_downloads, read_file, search_files,
)


def test_create_folder(tmp_path):
    result = create_folder(tmp_path / "Test" / "Sub")
    assert result["success"] is True
    assert (tmp_path / "Test" / "Sub").is_dir()


def test_copy_file_and_read(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("hello", encoding="utf-8")
    result = copy_file(src, tmp_path / "b.txt")
    assert result["success"] is True
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "hello"
    read = read_file(tmp_path / "b.txt")
    assert read["success"] is True
    assert read["result"]["content"] == "hello"


def test_search_files(tmp_path):
    (tmp_path / "notes.txt").write_text("python is great", encoding="utf-8")
    (tmp_path / "other.txt").write_text("nothing here", encoding="utf-8")
    result = search_files(tmp_path, "*.txt")
    assert result["success"] is True
    assert result["result"]["count"] == 2
    by_name = search_files(tmp_path, "notes")
    assert by_name["success"] is True
    assert any("notes.txt" in p for p in by_name["result"]["matches"])


def test_organize_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(files_mod, "_home", lambda: tmp_path)
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "photo.jpg").write_text("x", encoding="utf-8")
    (downloads / "doc.pdf").write_text("x", encoding="utf-8")
    result = organize_downloads()
    assert result["success"] is True
    assert result["result"]["moved_count"] == 2
    assert not (downloads / "photo.jpg").exists()
    assert (tmp_path / "Pictures" / "Organized" / "photo.jpg").exists()
    assert (tmp_path / "Documents" / "Study Material" / "doc.pdf").exists()


def test_find_duplicates(tmp_path):
    (tmp_path / "a.txt").write_text("same content", encoding="utf-8")
    (tmp_path / "b.txt").write_text("same content", encoding="utf-8")
    (tmp_path / "c.txt").write_text("different", encoding="utf-8")
    result = find_duplicates(tmp_path)
    assert result["success"] is True
    assert result["result"]["count"] == 1
    group = result["result"]["groups"][0]
    assert any("a.txt" in p for p in group) and any("b.txt" in p for p in group)


def test_is_path_allowed_blocks_system_paths(tmp_path):
    assert not is_path_allowed("/etc/passwd")
    assert not is_path_allowed("/usr/bin/python3")
    assert not is_path_allowed("/tmp/../etc/passwd")
    # Windows paths must be judged as Windows paths on any OS (fixed
    # by the coordinator: previously C:\Windows\... was treated as a
    # relative path under home on Linux and wrongly allowed).
    assert not is_path_allowed(r"C:\Windows\System32\cmd.exe")
    assert not is_path_allowed(r"C:\Program Files\App\app.exe")
    assert not is_path_allowed(r"C:\Temp\file.txt")
    assert not is_path_allowed(r"\\server\share\file.txt")
    assert is_path_allowed(r"C:\Users\Alice\Desktop\file.txt")
    # A plain path inside the allowed area should be allowed.
    assert is_path_allowed(tmp_path / "ok.txt")


def test_delete_path_requires_confirm(tmp_path):
    target = tmp_path / "to_delete.txt"
    target.write_text("x", encoding="utf-8")
    result = delete_path(target, confirm=False)
    assert result["success"] is False
    assert target.exists(), "delete_path without confirm must not delete"


def test_delete_path_uses_trash_not_permanent_delete(tmp_path):
    target = tmp_path / "trash_me.txt"
    target.write_text("x", encoding="utf-8")
    result = delete_path(target, confirm=True)
    assert result["success"] is True
    assert not target.exists(), "confirmed delete must remove the original path"
    assert "trash" in str(result["result"]).lower() or "recycle" in str(result["result"]).lower()
