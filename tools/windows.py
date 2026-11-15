"""Window management tools for NOOBRA.

Windows 11 is the target: ``pywin32`` (``win32gui``) is tried first, then
``ctypes.windll.user32`` EnumWindows. Both are guarded imports — on Linux
the module still imports and ``list_windows()`` falls back to ``wmctrl`` /
``ps``, while focus/minimise/maximise/close return a clear
``{"success": False, "error": "Windows-only: ..."}`` dict.
"""

from __future__ import annotations

import ctypes
import logging
import subprocess
import sys
from ctypes import wintypes

logger = logging.getLogger("noobra.tools")

try:
    import win32gui  # type: ignore
    import win32con  # type: ignore
    import win32process  # type: ignore
except Exception:  # pragma: no cover - Windows-only
    win32gui = None
    win32con = None
    win32process = None

__all__ = [
    "list_windows",
    "get_active_window",
    "focus_window",
    "switch_window",
    "minimize_window",
    "maximize_window",
    "close_window",
]


def _ok(result=None, verified=False):
    return {"success": True, "result": result, "error": None, "verified": verified}


def _fail(error, result=None):
    return {"success": False, "result": result, "error": str(error), "verified": False}


def _windows_only(feature: str):
    return _fail(f"Windows-only: {feature} is not available on Linux")


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def _list_windows_win32gui():
    windows = []

    def _cb(hwnd, _extra):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            windows.append({
                "title": title,
                "pid": int(pid),
                "hwnd": int(hwnd),
                "active": hwnd == win32gui.GetForegroundWindow(),
            })
        except Exception:
            return

    win32gui.EnumWindows(_cb, None)
    return windows


def _list_windows_ctypes():
    windows = []
    user32 = ctypes.windll.user32
    EnumWindows = user32.EnumWindows
    GetWindowTextW = user32.GetWindowTextW
    GetWindowTextLengthW = user32.GetWindowTextLengthW
    IsWindowVisible = user32.IsWindowVisible
    GetWindowThreadProcessId = user32.GetWindowThreadProcessId
    GetForegroundWindow = user32.GetForegroundWindow
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _lparam):
        try:
            if not IsWindowVisible(hwnd):
                return True
            length = GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            GetWindowTextW(hwnd, buf, length + 1)
            pid = wintypes.DWORD()
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            windows.append({
                "title": buf.value,
                "pid": int(pid.value),
                "hwnd": int(hwnd),
                "active": hwnd == GetForegroundWindow(),
            })
        except Exception:
            pass
        return True

    EnumWindows(WNDENUMPROC(_cb), 0)
    return windows


def _list_windows_linux():
    """Best-effort fallback: wmctrl -l, else a `ps` process list."""
    try:
        out = subprocess.run(["wmctrl", "-l", "-p"], capture_output=True,
                             text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            windows = []
            for line in out.stdout.splitlines():
                parts = line.split(None, 3)
                if len(parts) >= 4:
                    try:
                        pid = int(parts[2])
                    except ValueError:
                        pid = 0
                    windows.append({"title": parts[3], "pid": pid, "active": False})
            return windows
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.debug("wmctrl fallback failed: %s", exc)
    try:
        out = subprocess.run(["ps", "-eo", "pid,comm"], capture_output=True,
                             text=True, timeout=10)
        windows = []
        for line in out.stdout.splitlines()[1:]:
            parts = line.split(None, 1)
            if len(parts) == 2:
                windows.append({"title": parts[1].strip(), "pid": int(parts[0]),
                                "active": False})
        return windows
    except Exception as exc:
        logger.exception("list_windows Linux fallback failed")
        return []


def list_windows():
    """Return a list of ``{"title": str, "pid": int, "active": bool}``.

    Note: unlike most tools this returns a plain list (per the shared
    contract); the tool registry in ``tools/__init__.py`` wraps it into the
    standard ``{success, result, error, verified}`` dict.
    """
    try:
        if sys.platform == "win32" and win32gui is not None:
            return _list_windows_win32gui()
        if sys.platform == "win32":
            try:
                return _list_windows_ctypes()
            except Exception as exc:
                logger.exception("ctypes EnumWindows failed")
                return []
        return _list_windows_linux()
    except Exception as exc:
        logger.exception("list_windows failed")
        return []


# ---------------------------------------------------------------------------
# Helpers for Windows-only actions
# ---------------------------------------------------------------------------

def _find_hwnd(title_or_pid):
    """Find an HWND by window title (substring, case-insensitive) or PID."""
    if win32gui is None:
        return None
    target = str(title_or_pid)
    found = []
    try:
        pid_target = int(target)
    except (TypeError, ValueError):
        pid_target = None

    def _cb(hwnd, _extra):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd) or ""
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid_target is not None and int(pid) == pid_target:
                found.append(hwnd)
            elif pid_target is None and target.lower() in title.lower():
                found.append(hwnd)
        except Exception:
            return

    win32gui.EnumWindows(_cb, None)
    return found[0] if found else None


def get_active_window():
    """Return ``{"title": str, "pid": int}`` for the foreground window."""
    if sys.platform != "win32":
        return _windows_only("get_active_window")
    if win32gui is None:
        return _windows_only("get_active_window (pywin32 not installed)")
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return _ok({"title": title, "pid": int(pid), "hwnd": int(hwnd)}, verified=True)
    except Exception as exc:
        logger.exception("get_active_window failed")
        return _fail(exc)


def focus_window(title_or_pid):
    """Bring a window to the foreground by title substring or PID."""
    if sys.platform != "win32":
        return _windows_only("focus_window")
    if win32gui is None:
        return _windows_only("focus_window (pywin32 not installed)")
    try:
        hwnd = _find_hwnd(title_or_pid)
        if hwnd is None:
            return _fail(f"window not found: {title_or_pid!r}")
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
    except Exception as exc:
        logger.exception("focus_window failed for %s", title_or_pid)
        return _fail(exc)
    active = get_active_window()
    verified = bool(active.get("success")
                    and str(title_or_pid).lower() in active["result"]["title"].lower()) \
        if isinstance(title_or_pid, str) else True
    return _ok({"title_or_pid": str(title_or_pid), "focused": True}, verified=verified)


def switch_window(title_or_pid):
    """Alias for :func:`focus_window` used by the planner / tool registry."""
    return focus_window(title_or_pid)


def _show_window(title, cmd, verb):
    if sys.platform != "win32":
        return _windows_only(verb)
    if win32gui is None:
        return _windows_only(f"{verb} (pywin32 not installed)")
    try:
        hwnd = _find_hwnd(title)
        if hwnd is None:
            return _fail(f"window not found: {title!r}")
        win32gui.ShowWindow(hwnd, cmd)
    except Exception as exc:
        logger.exception("%s failed for %s", verb, title)
        return _fail(exc)
    return _ok({"title": str(title), verb: True}, verified=True)


def minimize_window(title):
    """Minimise a window by title substring."""
    return _show_window(title, win32con.SW_MINIMIZE if win32con else 6, "minimized")


def maximize_window(title):
    """Maximise a window by title substring."""
    return _show_window(title, win32con.SW_MAXIMIZE if win32con else 3, "maximized")


def close_window(title):
    """Close a window by title substring (WM_CLOSE)."""
    if sys.platform != "win32":
        return _windows_only("close_window")
    if win32gui is None:
        return _windows_only("close_window (pywin32 not installed)")
    try:
        hwnd = _find_hwnd(title)
        if hwnd is None:
            return _fail(f"window not found: {title!r}")
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    except Exception as exc:
        logger.exception("close_window failed for %s", title)
        return _fail(exc)
    return _ok({"title": str(title), "closed": True}, verified=True)
