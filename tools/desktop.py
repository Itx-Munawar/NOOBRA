"""Desktop automation tools for NOOBRA (mouse, keyboard, screenshots).

Windows 11 is the target; ``pyautogui`` is an optional, guarded import.
On Linux without pyautogui or without a display, every function returns
``{"success": False, "error": "..."}`` instead of crashing — the module must
always import cleanly.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("noobra.tools")

try:
    import pyautogui  # type: ignore
except Exception:  # pragma: no cover - optional dependency / no display
    pyautogui = None

__all__ = [
    "mouse_move",
    "mouse_click",
    "mouse_scroll",
    "type_text",
    "press_keys",
    "hotkey",
    "take_screenshot",
    "get_mouse_position",
    "get_screen_size",
    "is_available",
]


def _ok(result=None, verified=False):
    return {"success": True, "result": result, "error": None, "verified": verified}


def _fail(error, result=None):
    return {"success": False, "result": result, "error": str(error), "verified": False}


def is_available() -> bool:
    """True when pyautogui is importable and a display is present."""
    if pyautogui is None:
        return False
    if sys.platform != "win32" and not os.environ.get("DISPLAY"):
        return False
    return True


def _require():
    """Return an error dict if desktop automation is unavailable, else None."""
    if pyautogui is None:
        return _fail(
            "pyautogui not installed: pip install pyautogui "
            "(Windows-only feature on this machine)"
        )
    if sys.platform != "win32" and not os.environ.get("DISPLAY"):
        return _fail("Windows-only: no display available for desktop automation on Linux")
    return None


def get_screen_size():
    """Return ``{"width": int, "height": int}`` or an error dict."""
    err = _require()
    if err:
        return err
    try:
        w, h = pyautogui.size()
    except Exception as exc:
        logger.exception("get_screen_size failed")
        return _fail(exc)
    return _ok({"width": int(w), "height": int(h)}, verified=True)


def get_mouse_position():
    """Return the current mouse position ``{"x": int, "y": int}``."""
    err = _require()
    if err:
        return err
    try:
        x, y = pyautogui.position()
    except Exception as exc:
        logger.exception("get_mouse_position failed")
        return _fail(exc)
    return _ok({"x": int(x), "y": int(y)}, verified=True)


def mouse_move(x, y):
    """Move the mouse to absolute screen coordinates (x, y)."""
    err = _require()
    if err:
        return err
    try:
        pyautogui.moveTo(int(x), int(y))
        cur = pyautogui.position()
    except Exception as exc:
        logger.exception("mouse_move failed")
        return _fail(exc)
    return _ok({"x": int(cur.x), "y": int(cur.y)}, verified=True)


def mouse_click(x=None, y=None, button="left", clicks=1):
    """Click at (x, y) if given, else at the current mouse position."""
    err = _require()
    if err:
        return err
    if button not in ("left", "right", "middle"):
        return _fail(f"invalid button: {button!r} (left/right/middle)")
    try:
        if x is not None and y is not None:
            pyautogui.click(int(x), int(y), button=button, clicks=int(clicks))
        else:
            pyautogui.click(button=button, clicks=int(clicks))
        cur = pyautogui.position()
    except Exception as exc:
        logger.exception("mouse_click failed")
        return _fail(exc)
    return _ok({"x": int(cur.x), "y": int(cur.y), "button": button, "clicks": int(clicks)},
               verified=True)


def mouse_scroll(amount):
    """Scroll the mouse wheel; positive ``amount`` scrolls up, negative down."""
    err = _require()
    if err:
        return err
    try:
        pyautogui.scroll(int(amount))
    except Exception as exc:
        logger.exception("mouse_scroll failed")
        return _fail(exc)
    return _ok({"amount": int(amount)}, verified=True)


def type_text(text, interval=0.01):
    """Type ``text`` with ``interval`` seconds between keystrokes."""
    err = _require()
    if err:
        return err
    if text is None:
        return _fail("text is required")
    try:
        pyautogui.typewrite(str(text), interval=float(interval))
    except Exception as exc:
        logger.exception("type_text failed")
        return _fail(exc)
    return _ok({"typed_chars": len(str(text))}, verified=True)


#: pyautogui key-name aliases for common planner spellings.
_KEY_ALIASES = {
    "control": "ctrl", "command": "win", "windows": "win", "win": "win",
    "return": "enter", "esc": "escape", "del": "delete",
    "up_arrow": "up", "down_arrow": "down", "left_arrow": "left", "right_arrow": "right",
}


def press_keys(*keys):
    """Press keys in combination, e.g. ``press_keys("ctrl", "c")``.

    Accepts either ``press_keys("ctrl", "c")`` or ``press_keys(["ctrl", "c"])``.
    """
    err = _require()
    if err:
        return err
    if len(keys) == 1 and isinstance(keys[0], (list, tuple)):
        keys = tuple(keys[0])
    if not keys:
        return _fail("no keys given")
    normalised = [_KEY_ALIASES.get(str(k).lower(), str(k).lower()) for k in keys]
    try:
        if len(normalised) == 1:
            pyautogui.press(normalised[0])
        else:
            pyautogui.hotkey(*normalised)
    except Exception as exc:
        logger.exception("press_keys failed for %s", normalised)
        return _fail(exc)
    return _ok({"keys": normalised}, verified=True)


# Alias used by planners that say "hotkey".
hotkey = press_keys


def take_screenshot(path=None):
    """Take a screenshot and save it; returns ``{"path": ...}``.

    Default location: ``~/Pictures/noobra_screenshots/screenshot-<timestamp>.png``.
    """
    err = _require()
    if err:
        return err
    if path is None:
        out = (Path.home() / "Pictures" / "noobra_screenshots"
               / f"screenshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
    else:
        out = Path(os.path.expanduser(str(path)))
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        pyautogui.screenshot(str(out))
    except Exception as exc:
        logger.exception("take_screenshot failed")
        return _fail(exc)
    return _ok({"path": str(out)}, verified=out.is_file())
