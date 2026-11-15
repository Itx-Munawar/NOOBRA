"""File tools for NOOBRA — safe path handling and file operations.

Works fully on Linux (build environment) and Windows 11 (target).
All public functions return ``{"success": bool, "result": ..., "error": str|None,
"verified": bool}`` and never raise for expected failures.

Safety rules
------------
* Paths are resolved through :func:`resolve_user_path` and checked with
  :func:`is_path_allowed` before any read/write/delete.
* ``..`` escapes and system directories are blocked.
* Deletes are NEVER permanent: files go to the recycle bin via ``send2trash``
  (if installed) or to ``~/.noobra/trash/<timestamp>_<name>``.
* Deletes require ``confirm=True``.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("noobra.tools")

try:  # Optional: recycle-bin support.
    from send2trash import send2trash
except Exception:  # pragma: no cover - optional dependency
    send2trash = None

__all__ = [
    "resolve_user_path",
    "is_path_allowed",
    "create_folder",
    "delete_path",
    "delete_file",
    "delete_folder",
    "rename_path",
    "copy_file",
    "move_file",
    "search_files",
    "read_file",
    "create_file",
    "list_directory",
    "organize_downloads",
    "find_duplicates",
    "ALLOWED_DIRS",
    "BLOCKED_DIRS",
    "TRASH_DIR",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: User folders that are always allowed (relative to the home directory).
KNOWN_FOLDERS = ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos")

#: Directories that are never writable/deletable through these tools.
#: Windows entries are matched case-insensitively; Linux entries are absolute.
BLOCKED_DIRS = (
    r"C:\Windows",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    r"C:\Windows\System32",
    r"C:\ProgramData",
    "/etc",
    "/usr",
    "/bin",
    "/sbin",
    "/proc",
    "/sys",
    "/boot",
    "/dev",
    "/var",
    "/lib",
    "/lib64",
    "/opt",
    "/root",
)

TRASH_DIR = Path.home() / ".noobra" / "trash"

#: Extra directories the user explicitly allows, from ``NOOBRA_ALLOWED_DIRS``
#: (os.pathsep-separated). ``/tmp`` is allowed on Linux so tests / scratch
#: work can use it; it is not a system directory.
ALLOWED_DIRS: list[Path] = []


def _load_allowed_dirs() -> list[Path]:
    dirs: list[Path] = []
    raw = os.environ.get("NOOBRA_ALLOWED_DIRS", "")
    for part in raw.split(os.pathsep):
        part = part.strip()
        if part:
            try:
                dirs.append(Path(part).expanduser().resolve())
            except Exception:
                continue
    return dirs


def _home() -> Path:
    return Path.home()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Path resolution / allow-list
# ---------------------------------------------------------------------------

def resolve_user_path(path, base=None) -> Path:
    """Resolve a user-supplied path to an absolute :class:`pathlib.Path`.

    * Expands ``~`` and environment variables (``%USERPROFILE%`` / ``$HOME``).
    * Bare known-folder names (``"Desktop"``, ``"Documents"``, ``"Downloads"``,
      ``"Pictures"``, ``"Music"``, ``"Videos"``) and paths starting with one
      (``"Desktop/report.txt"``, ``"Downloads/file.pdf"``) resolve under the
      user's home directory, on both Windows and Linux.
    * Other relative paths resolve against ``base`` (default: current dir).
    * Absolute paths are returned as-is (normalised).
    """
    if path is None:
        raise ValueError("path is required")
    text = os.path.expandvars(os.path.expanduser(str(path).strip()))
    if not text:
        raise ValueError("path is empty")

    # Normalise Windows separators on any platform for matching purposes.
    parts = Path(text).parts
    # Handle "Desktop", "Desktop/..." etc. (also "Desktop\\..." on Windows).
    first = text.replace("\\", "/").split("/", 1)[0]
    if first in KNOWN_FOLDERS:
        rest = text.replace("\\", "/").split("/", 1)
        resolved = _home() / first
        if len(rest) > 1 and rest[1]:
            resolved = resolved / rest[1]
        return resolved.resolve() if not _has_glob_chars(text) else resolved

    p = Path(text)
    if p.is_absolute():
        return p.resolve() if not _has_glob_chars(text) else p
    if base is not None:
        return (Path(base) / p).resolve() if not _has_glob_chars(text) else (Path(base) / p)
    return (Path.cwd() / p).resolve() if not _has_glob_chars(text) else (Path.cwd() / p)


def _has_glob_chars(text: str) -> bool:
    return any(ch in text for ch in "*?[")


def is_path_allowed(path) -> bool:
    """Return True if ``path`` may be touched by NOOBRA tools.

    Blocks ``..`` escapes (via resolution), system directories, and anything
    outside the home directory / ``/tmp`` / user-configured allowed dirs,
    unless the path is inside an explicitly allowed directory.
    """
    try:
        if path is None:
            return False
        raw = str(path)
        # --- Windows-style paths must be judged as Windows paths, on
        # any OS. On Linux, Path("C:\\Windows\\...") is just a relative
        # filename under the cwd/home, so without this check it slipped
        # past the blocked-dir list (fixed 2026-11-15, coordinator).
        raw_norm = raw.strip().replace("/", "\\").lower()
        if raw_norm.startswith("\\\\"):
            return False  # UNC paths are never allowed.
        drive = re.match(r"^([a-z]):\\", raw_norm)
        if drive:
            for blocked in BLOCKED_DIRS:
                b = blocked.lower().replace("/", "\\")
                if raw_norm == b or raw_norm.startswith(b.rstrip("\\") + "\\"):
                    return False
            # Only a user-profile path on a drive is allowed, e.g.
            # C:\Users\<name>\Desktop\... — everything else on a drive
            # (C:\Temp, D:\Data, ...) fails closed.
            if re.match(r"^[a-z]:\\users\\[^\\]+(\\.*)?$", raw_norm):
                return True
            return False
        # A literal ".." component in the raw input is suspicious; resolved
        # paths are also checked below, so "a/../b" that stays inside home
        # is fine, but reject attempts that escape via "..".
        p = resolve_user_path(raw)
    except Exception:
        return False

    # Blocked system directories (case-insensitive for Windows paths).
    lowered = str(p).lower().replace("/", "\\")
    for blocked in BLOCKED_DIRS:
        b = blocked.lower().replace("/", "\\")
        if lowered == b or lowered.startswith(b.rstrip("\\") + "\\"):
            return False
    # Also block the Windows drive root / system folders by name on any OS.
    if lowered.startswith("c:\\windows") or lowered.startswith("c:\\program files"):
        return False

    allowed_roots = [_home(), Path("/tmp")] + _load_allowed_dirs() + ALLOWED_DIRS
    # On Windows also allow the user profile / other drive user folders via home.
    for root in allowed_roots:
        try:
            if _is_within(p, root.resolve()):
                return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(result=None, verified=False):
    return {"success": True, "result": result, "error": None, "verified": verified}


def _fail(error, result=None):
    return {"success": False, "result": result, "error": str(error), "verified": False}


def _check(path):
    """Resolve + allow-check a path; returns (Path, error_dict|None)."""
    try:
        p = resolve_user_path(path)
    except Exception as exc:
        return None, _fail(f"invalid path {path!r}: {exc}")
    if not is_path_allowed(p):
        return None, _fail(f"path not allowed: {p}")
    return p, None


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def create_folder(path):
    """Create a folder (including parents). Verified by existence afterwards."""
    p, err = _check(path)
    if err:
        return err
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.exception("create_folder failed for %s", p)
        return _fail(exc)
    return _ok(str(p), verified=p.is_dir())


def create_file(path, content=""):
    """Create (or overwrite) a text file with ``content``. Parent dirs created."""
    p, err = _check(path)
    if err:
        return err
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except Exception as exc:
        logger.exception("create_file failed for %s", p)
        return _fail(exc)
    return _ok(str(p), verified=p.is_file() and p.read_text(encoding="utf-8") == content)


def read_file(path, max_chars=20000):
    """Read a text file (up to ``max_chars`` chars). Binary files are rejected."""
    p, err = _check(path)
    if err:
        return err
    if not p.exists():
        return _fail(f"file not found: {p}")
    if not p.is_file():
        return _fail(f"not a file: {p}")
    try:
        data = p.read_bytes()
        # Reject obvious binary content.
        if b"\x00" in data[:8192]:
            return _fail(f"binary file, cannot read as text: {p}")
        text = data.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.exception("read_file failed for %s", p)
        return _fail(exc)
    truncated = len(text) > max_chars
    return _ok(
        {"path": str(p), "content": text[:max_chars], "truncated": truncated,
         "size_bytes": len(data)},
        verified=True,
    )


def list_directory(path):
    """List entries of a directory: [{name, path, type, size_bytes}]."""
    p, err = _check(path)
    if err:
        return err
    if not p.exists():
        return _fail(f"directory not found: {p}")
    if not p.is_dir():
        return _fail(f"not a directory: {p}")
    try:
        entries = []
        for entry in sorted(p.iterdir(), key=lambda e: e.name.lower()):
            try:
                entries.append({
                    "name": entry.name,
                    "path": str(entry),
                    "type": "directory" if entry.is_dir() else "file",
                    "size_bytes": entry.stat().st_size if entry.is_file() else None,
                })
            except OSError:
                continue
    except Exception as exc:
        logger.exception("list_directory failed for %s", p)
        return _fail(exc)
    return _ok(entries, verified=True)


def rename_path(src, dst):
    """Rename / move a file or folder within allowed locations."""
    s, err = _check(src)
    if err:
        return err
    d, err = _check(dst)
    if err:
        return err
    if not s.exists():
        return _fail(f"source not found: {s}")
    try:
        d.parent.mkdir(parents=True, exist_ok=True)
        s.rename(d)
    except Exception as exc:
        logger.exception("rename_path failed %s -> %s", s, d)
        return _fail(exc)
    return _ok({"from": str(s), "to": str(d)}, verified=d.exists() and not s.exists())


def copy_file(src, dst):
    """Copy a file, preserving metadata. Verified by size + existence."""
    s, err = _check(src)
    if err:
        return err
    d, err = _check(dst)
    if err:
        return err
    if not s.exists():
        return _fail(f"source not found: {s}")
    if not s.is_file():
        return _fail(f"not a file: {s}")
    try:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
    except Exception as exc:
        logger.exception("copy_file failed %s -> %s", s, d)
        return _fail(exc)
    verified = d.is_file() and d.stat().st_size == s.stat().st_size
    return _ok({"from": str(s), "to": str(d), "size_bytes": d.stat().st_size},
               verified=verified)


def move_file(src, dst):
    """Move a file. Verified by existence at destination and absence at source."""
    s, err = _check(src)
    if err:
        return err
    d, err = _check(dst)
    if err:
        return err
    if not s.exists():
        return _fail(f"source not found: {s}")
    try:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s), str(d))
    except Exception as exc:
        logger.exception("move_file failed %s -> %s", s, d)
        return _fail(exc)
    return _ok({"from": str(s), "to": str(d)}, verified=d.exists() and not s.exists())


def delete_path(path, confirm=False):
    """Move a file/folder to trash — never permanently delete.

    Requires ``confirm=True``; otherwise returns success=False with
    ``"confirmation required"``. Uses ``send2trash`` when available, else
    moves to ``~/.noobra/trash/<timestamp>_<name>``. Verified by the path
    no longer existing at its original location.
    """
    if not confirm:
        return _fail("confirmation required: pass confirm=True to delete")
    p, err = _check(path)
    if err:
        return err
    if not p.exists() and not p.is_symlink():
        return _fail(f"path not found: {p}")
    try:
        if send2trash is not None:
            send2trash(str(p))
            trashed_to = "recycle bin (send2trash)"
        else:
            TRASH_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            dest = TRASH_DIR / f"{stamp}_{p.name}"
            # Avoid collisions.
            n = 1
            while dest.exists():
                dest = TRASH_DIR / f"{stamp}_{n}_{p.name}"
                n += 1
            shutil.move(str(p), str(dest))
            trashed_to = str(dest)
    except Exception as exc:
        logger.exception("delete_path failed for %s", p)
        return _fail(exc)
    return _ok({"path": str(p), "trashed_to": trashed_to},
               verified=not p.exists())


def delete_file(path, confirm=False):
    """Delete a single file (to trash). Wrapper over :func:`delete_path`."""
    p, err = _check(path)
    if err:
        return err
    if p.exists() and not p.is_file():
        return _fail(f"not a file: {p}")
    return delete_path(path, confirm=confirm)


def delete_folder(path, confirm=False):
    """Delete a folder (to trash). Wrapper over :func:`delete_path`."""
    p, err = _check(path)
    if err:
        return err
    if p.exists() and not p.is_dir():
        return _fail(f"not a directory: {p}")
    return delete_path(path, confirm=confirm)


def search_files(directory, pattern, recursive=True):
    """Search for files matching a glob ``pattern`` (e.g. ``"*.pdf"``).

    Returns ``{"matches": [paths], "count": int}``. ``pattern`` may also be a
    plain substring matched against file names when it contains no glob chars.
    """
    d, err = _check(directory)
    if err:
        return err
    if not d.exists():
        return _fail(f"directory not found: {d}")
    if not d.is_dir():
        return _fail(f"not a directory: {d}")
    try:
        if any(ch in pattern for ch in "*?["):
            iterator = d.rglob(pattern) if recursive else d.glob(pattern)
            matches = [str(p) for p in iterator if p.is_file()]
        else:
            needle = pattern.lower()
            if recursive:
                matches = [str(p) for p in d.rglob("*")
                           if p.is_file() and needle in p.name.lower()]
            else:
                matches = [str(p) for p in d.iterdir()
                           if p.is_file() and needle in p.name.lower()]
        matches.sort()
    except Exception as exc:
        logger.exception("search_files failed in %s", d)
        return _fail(exc)
    return _ok({"matches": matches, "count": len(matches)}, verified=True)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_duplicates(directory):
    """Find duplicate files under ``directory`` by SHA-256 hash.

    Returns ``{"groups": [[path, ...], ...], "count": int}`` — only groups
    with 2+ identical files are returned.
    """
    d, err = _check(directory)
    if err:
        return err
    if not d.exists():
        return _fail(f"directory not found: {d}")
    try:
        by_hash: dict[str, list[str]] = {}
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            try:
                by_hash.setdefault(_sha256(p), []).append(str(p))
            except OSError:
                continue
        groups = [sorted(v) for v in by_hash.values() if len(v) > 1]
        groups.sort(key=lambda g: g[0])
    except Exception as exc:
        logger.exception("find_duplicates failed in %s", d)
        return _fail(exc)
    return _ok({"groups": groups, "count": len(groups)}, verified=True)


# ---------------------------------------------------------------------------
# Organize Downloads
# ---------------------------------------------------------------------------

#: extension -> (destination folder relative to home, subfolder name)
ORGANIZE_MAP = {
    ".pdf": ("Documents", "Study Material"),
    ".epub": ("Documents", "Study Material"),
    ".mobi": ("Documents", "Study Material"),
    ".doc": ("Documents", "Documents"),
    ".docx": ("Documents", "Documents"),
    ".txt": ("Documents", "Documents"),
    ".md": ("Documents", "Documents"),
    ".rtf": ("Documents", "Documents"),
    ".xls": ("Documents", "Spreadsheets"),
    ".xlsx": ("Documents", "Spreadsheets"),
    ".csv": ("Documents", "Spreadsheets"),
    ".ppt": ("Documents", "Presentations"),
    ".pptx": ("Documents", "Presentations"),
    ".jpg": ("Pictures", "Organized"),
    ".jpeg": ("Pictures", "Organized"),
    ".png": ("Pictures", "Organized"),
    ".gif": ("Pictures", "Organized"),
    ".webp": ("Pictures", "Organized"),
    ".bmp": ("Pictures", "Organized"),
    ".mp3": ("Music", "Organized"),
    ".wav": ("Music", "Organized"),
    ".flac": ("Music", "Organized"),
    ".mp4": ("Videos", "Organized"),
    ".mkv": ("Videos", "Organized"),
    ".mov": ("Videos", "Organized"),
    ".zip": ("Downloads", "Archives"),
    ".rar": ("Downloads", "Archives"),
    ".7z": ("Downloads", "Archives"),
    ".exe": ("Downloads", "Installers"),
    ".msi": ("Downloads", "Installers"),
}


def organize_downloads():
    """Move files out of Downloads into organised subfolders by extension.

    PDFs go to ``Documents/Study Material``, images to ``Pictures/Organized``,
    documents to ``Documents/Documents``, etc. (see ``ORGANIZE_MAP``).
    Files with unknown extensions go to ``Downloads/Other``. Directories and
    hidden files are left alone. Returns a summary ``{moved, skipped, by_category}``.
    """
    downloads = _home() / "Downloads"
    if not downloads.exists():
        return _fail(f"Downloads folder not found: {downloads}")
    moved: list[dict] = []
    skipped: list[str] = []
    by_category: dict[str, int] = {}
    try:
        for entry in sorted(downloads.iterdir(), key=lambda e: e.name.lower()):
            if entry.is_dir() or entry.name.startswith("."):
                skipped.append(str(entry))
                continue
            folder, sub = ORGANIZE_MAP.get(entry.suffix.lower(),
                                           ("Downloads", "Other"))
            dest_dir = _home() / folder / sub
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / entry.name
            if dest.exists() and dest.resolve() != entry.resolve():
                stem, suffix = entry.stem, entry.suffix
                n = 1
                while dest.exists():
                    dest = dest_dir / f"{stem} ({n}){suffix}"
                    n += 1
            try:
                shutil.move(str(entry), str(dest))
                moved.append({"from": str(entry), "to": str(dest)})
                by_category[sub] = by_category.get(sub, 0) + 1
            except OSError as exc:
                logger.warning("organize_downloads: could not move %s: %s", entry, exc)
                skipped.append(str(entry))
    except Exception as exc:
        logger.exception("organize_downloads failed")
        return _fail(exc)
    return _ok({"moved": moved, "moved_count": len(moved),
                "skipped": skipped, "by_category": by_category}, verified=True)
