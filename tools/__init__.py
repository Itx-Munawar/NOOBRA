"""NOOBRA tool registry — the single entry point other workstreams use.

Exposes:

* ``TOOL_SCHEMAS`` — JSON-schema descriptions of every tool, for the planner.
* :func:`get_tool_registry` — ``{name: callable}`` for every schema name.
  Every callable returns ``{"success", "result", "error", "verified"}``.
* :func:`describe_tools_for_llm` — a prompt-ready text listing of the tools.

All imports here are guarded inside the submodules, so importing
``noobra.tools`` never crashes on Linux even though the target is Windows 11.
"""

from __future__ import annotations

import logging

from . import applications, browser, desktop, files, terminal, windows

logger = logging.getLogger("noobra.tools")

__all__ = ["TOOL_SCHEMAS", "get_tool_registry", "describe_tools_for_llm"]


def _schema(name, description, properties, required=None):
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(required or []),
            "additionalProperties": False,
        },
    }


def _s_str(desc):
    return {"type": "string", "description": desc}


def _s_int(desc):
    return {"type": "integer", "description": desc}


def _s_bool(desc):
    return {"type": "boolean", "description": desc}


def _s_num(desc):
    return {"type": "number", "description": desc}


TOOL_SCHEMAS = [
    # -- applications ------------------------------------------------------
    _schema("open_app", "Launch an application by name (chrome, vscode, notepad, explorer, settings, calculator, paint).",
            {"name": _s_str("Application name, e.g. 'chrome' or 'notepad'"),
             "args": {"type": "array", "items": {"type": "string"}, "description": "Extra command-line arguments"}}, ["name"]),
    _schema("launch_app", "Launch an application by name (same as open_app).",
            {"name": _s_str("Application name"), "args": {"type": "array", "items": {"type": "string"}}}, ["name"]),
    _schema("close_app", "Close/terminate an application by name.",
            {"name": _s_str("Application name, e.g. 'chrome'")}, ["name"]),
    _schema("is_app_running", "Check whether an application is currently running.",
            {"name": _s_str("Application name")}, ["name"]),
    # -- windows -----------------------------------------------------------
    _schema("list_windows", "List open windows with title, pid and active flag.",
            {}),
    _schema("get_active_window", "Get the currently focused/foreground window.",
            {}),
    _schema("switch_window", "Bring a window to the foreground by title or pid.",
            {"title_or_pid": _s_str("Window title (substring) or pid")}, ["title_or_pid"]),
    _schema("focus_window", "Bring a window to the foreground by title or pid (same as switch_window).",
            {"title_or_pid": _s_str("Window title (substring) or pid")}, ["title_or_pid"]),
    _schema("minimize_window", "Minimise a window by title.",
            {"title": _s_str("Window title (substring)")}, ["title"]),
    _schema("maximize_window", "Maximise a window by title.",
            {"title": _s_str("Window title (substring)")}, ["title"]),
    _schema("close_window", "Close a window by title.",
            {"title": _s_str("Window title (substring)")}, ["title"]),
    # -- desktop -----------------------------------------------------------
    _schema("mouse_move", "Move the mouse to absolute screen coordinates.",
            {"x": _s_int("X coordinate"), "y": _s_int("Y coordinate")}, ["x", "y"]),
    _schema("mouse_click", "Click the mouse at (x, y) or at the current position.",
            {"x": _s_int("X coordinate (optional)"), "y": _s_int("Y coordinate (optional)"),
             "button": _s_str("left, right or middle (default left)"),
             "clicks": _s_int("Number of clicks (default 1)")}),
    _schema("mouse_scroll", "Scroll the mouse wheel; positive scrolls up, negative down.",
            {"amount": _s_int("Scroll amount, e.g. 3 or -3")}, ["amount"]),
    _schema("type_text", "Type text as if on the keyboard.",
            {"text": _s_str("Text to type"), "interval": _s_num("Seconds between keystrokes (default 0.01)")}, ["text"]),
    _schema("press_keys", "Press keys in combination, e.g. ['ctrl', 'c'].",
            {"keys": {"type": "array", "items": {"type": "string"}, "description": "Keys to press together, e.g. ['ctrl', 'c']"}}, ["keys"]),
    _schema("take_screenshot", "Take a screenshot and save it; returns the file path.",
            {"path": _s_str("Optional destination path")}),
    # -- files -------------------------------------------------------------
    _schema("create_folder", "Create a folder (including parents).",
            {"path": _s_str("Folder path, e.g. 'Desktop/New Folder'")}, ["path"]),
    _schema("delete_file", "Move a file to the trash (never permanently deletes). Requires confirm=true.",
            {"path": _s_str("File path"), "confirm": _s_bool("Must be true to delete")}, ["path"]),
    _schema("delete_folder", "Move a folder to the trash (never permanently deletes). Requires confirm=true.",
            {"path": _s_str("Folder path"), "confirm": _s_bool("Must be true to delete")}, ["path"]),
    _schema("delete_path", "Move a file or folder to the trash (never permanently deletes). Requires confirm=true.",
            {"path": _s_str("Path"), "confirm": _s_bool("Must be true to delete")}, ["path"]),
    _schema("rename_path", "Rename or move a file/folder.",
            {"src": _s_str("Source path"), "dst": _s_str("Destination path")}, ["src", "dst"]),
    _schema("copy_file", "Copy a file.",
            {"src": _s_str("Source file"), "dst": _s_str("Destination file")}, ["src", "dst"]),
    _schema("move_file", "Move a file.",
            {"src": _s_str("Source file"), "dst": _s_str("Destination file")}, ["src", "dst"]),
    _schema("search_files", "Search for files matching a glob pattern (e.g. '*.pdf') or name substring.",
            {"directory": _s_str("Directory to search"), "pattern": _s_str("Glob pattern or substring"),
             "recursive": _s_bool("Search subfolders (default true)")}, ["directory", "pattern"]),
    _schema("read_file", "Read a text file (up to max_chars characters).",
            {"path": _s_str("File path"), "max_chars": _s_int("Maximum characters (default 20000)")}, ["path"]),
    _schema("create_file", "Create (or overwrite) a text file with content.",
            {"path": _s_str("File path"), "content": _s_str("File content")}, ["path"]),
    _schema("list_directory", "List entries of a directory with name, type and size.",
            {"path": _s_str("Directory path")}, ["path"]),
    _schema("organize_downloads", "Move files from Downloads into organised subfolders by type (PDFs to Documents/Study Material, images to Pictures/Organized, ...).",
            {}),
    _schema("find_duplicates", "Find duplicate files under a directory by SHA-256 hash.",
            {"directory": _s_str("Directory to scan")}, ["directory"]),
    # -- terminal ----------------------------------------------------------
    _schema("run_command", "Run a safe shell command and capture its output. Dangerous commands are blocked.",
            {"command": _s_str("Command, e.g. 'python --version' or 'git status'"),
             "cwd": _s_str("Working directory (optional)"),
             "timeout": _s_int("Timeout in seconds (default 30)")}, ["command"]),
    # -- browser -----------------------------------------------------------
    _schema("browser_navigate", "Navigate the browser's current tab to a URL.",
            {"url": _s_str("URL to open")}, ["url"]),
    _schema("browser_search", "Search Google for a query in the browser.",
            {"query": _s_str("Search query")}, ["query"]),
    _schema("search_google", "Search Google for a query in the browser (alias of browser_search).",
            {"query": _s_str("Search query")}, ["query"]),
    _schema("search_youtube", "Search YouTube for a query in the browser.",
            {"query": _s_str("Search query")}, ["query"]),
    _schema("navigate", "Navigate the browser's current tab to a URL (alias of browser_navigate).",
            {"url": _s_str("URL to open")}, ["url"]),
    _schema("browser_read", "Read the current page: title, url and visible text.",
            {}),
    _schema("browser_click", "Click an element on the current page by CSS selector.",
            {"selector": _s_str("CSS selector, e.g. 'a[href=\"/about\"]'"),
             "timeout": _s_int("Timeout in ms (default 5000)")}, ["selector"]),
    _schema("browser_fill", "Fill a form field on the current page by CSS selector.",
            {"selector": _s_str("CSS selector"), "value": _s_str("Value to fill")}, ["selector", "value"]),
    _schema("browser_new_tab", "Open a new browser tab, optionally navigating to a URL.",
            {"url": _s_str("Optional URL to open in the new tab")}),
    _schema("browser_close_tab", "Close a browser tab by index (default: current tab).",
            {"index": _s_int("Tab index, -1 = current (default -1)")}),
    _schema("browser_back", "Go back in the browser's history.", {}),
    _schema("browser_forward", "Go forward in the browser's history.", {}),
]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _list_windows_tool(**kwargs):
    """Wrap windows.list_windows() (plain list) into the standard dict."""
    try:
        result = windows.list_windows()
        return {"success": True, "result": result, "error": None, "verified": True}
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("list_windows failed")
        return {"success": False, "result": [], "error": str(exc), "verified": False}


def _press_keys_tool(keys=None, **kwargs):
    """Adapter: the schema passes ``keys`` as a list; desktop.press_keys takes *keys."""
    if keys is None:
        # Also accept a single "key" kwarg or positional-style kwargs.
        keys = kwargs.get("key") or kwargs.get("key_list") or []
    if isinstance(keys, str):
        keys = [keys]
    return desktop.press_keys(*list(keys))


def get_tool_registry():
    """Return ``{tool_name: callable}`` for every tool in ``TOOL_SCHEMAS``.

    All callables accept keyword arguments matching their schema and return
    ``{"success", "result", "error", "verified"}``.
    """
    return {
        # applications
        "open_app": applications.open_app,
        "launch_app": applications.launch_app,
        "close_app": applications.close_app,
        "is_app_running": applications.is_app_running,
        # windows
        "list_windows": _list_windows_tool,
        "get_active_window": windows.get_active_window,
        "switch_window": windows.switch_window,
        "focus_window": windows.focus_window,
        "minimize_window": windows.minimize_window,
        "maximize_window": windows.maximize_window,
        "close_window": windows.close_window,
        # desktop
        "mouse_move": desktop.mouse_move,
        "mouse_click": desktop.mouse_click,
        "mouse_scroll": desktop.mouse_scroll,
        "type_text": desktop.type_text,
        "press_keys": _press_keys_tool,
        "take_screenshot": desktop.take_screenshot,
        # files
        "create_folder": files.create_folder,
        "delete_file": files.delete_file,
        "delete_folder": files.delete_folder,
        "delete_path": files.delete_path,
        "rename_path": files.rename_path,
        "copy_file": files.copy_file,
        "move_file": files.move_file,
        "search_files": files.search_files,
        "read_file": files.read_file,
        "create_file": files.create_file,
        "list_directory": files.list_directory,
        "organize_downloads": files.organize_downloads,
        "find_duplicates": files.find_duplicates,
        # terminal
        "run_command": terminal.run_command,
        # browser
        "browser_navigate": browser.browser_navigate,
        "navigate": browser.browser_navigate,
        "browser_search": browser.browser_search,
        "search_google": browser.search_google,
        "search_youtube": browser.search_youtube,
        "browser_read": browser.browser_read,
        "browser_click": browser.browser_click,
        "browser_fill": browser.browser_fill,
        "browser_new_tab": browser.browser_new_tab,
        "browser_close_tab": browser.browser_close_tab,
        "browser_back": browser.browser_back,
        "browser_forward": browser.browser_forward,
    }


def describe_tools_for_llm() -> str:
    """Return a prompt-ready listing: name + description + parameters."""
    lines = ["Available tools:"]
    for schema in TOOL_SCHEMAS:
        params = schema["parameters"]["properties"]
        if params:
            param_str = ", ".join(
                f"{name}: {spec.get('type', '?')}"
                + (" (required)" if name in schema["parameters"]["required"] else "")
                for name, spec in params.items()
            )
        else:
            param_str = "no parameters"
        lines.append(f"- {schema['name']}({param_str}): {schema['description']}")
    return "\n".join(lines)
