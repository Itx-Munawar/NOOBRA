"""Permission classification for NOOBRA tools.

Every tool call is classified before it runs:

* ``SAFE`` -- read-only / reversible, runs without asking.
* ``CAUTION`` -- changes files or the system, or leaves the machine;
  needs the user's approval (once per step).
* ``DANGEROUS`` -- destructive or hard to undo (delete, admin, send,
  submit, install); always needs explicit confirmation.

Unknown tools default to ``CAUTION`` -- fail closed, never open.
"""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger("noobra.core.permissions")


class PermissionLevel(Enum):
    """How risky a tool call is."""

    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"


SAFE_TOOLS = {
    "open_app",
    "search_google",
    "search_youtube",
    "navigate",
    "read_file",
    "list_windows",
    "create_folder",
    "list_directory",
    "search_files",
    "read_content",
}

CAUTION_TOOLS = {
    "move_file",
    "copy_file",
    "rename_file",
    "organize_downloads",
    "run_command",
    "fill_form",
    "upload_file",
}

DANGEROUS_TOOLS = {
    "delete_file",
    "delete_folder",
    "run_admin_command",
    "send_email",
    "submit_form",
    "install_software",
}

# Extra aliases the tools registry / planner may use, mapped to the same
# levels so classification stays consistent even for renamed tools.
_ALIASES = {
    "close_app": PermissionLevel.SAFE,
    "browser_navigate": PermissionLevel.SAFE,
    "browser_search": PermissionLevel.SAFE,
    "browser_read": PermissionLevel.SAFE,
    "browser_new_tab": PermissionLevel.SAFE,
    "browser_back": PermissionLevel.SAFE,
    "browser_forward": PermissionLevel.SAFE,
    "launch_app": PermissionLevel.SAFE,
    "open_website": PermissionLevel.SAFE,
    "open_file": PermissionLevel.SAFE,
    "list_files": PermissionLevel.SAFE,
    "get_clipboard": PermissionLevel.SAFE,
    "take_screenshot": PermissionLevel.SAFE,
    "write_file": PermissionLevel.CAUTION,
    "create_file": PermissionLevel.CAUTION,
    "edit_file": PermissionLevel.CAUTION,
    "download_file": PermissionLevel.CAUTION,
    "empty_recycle_bin": PermissionLevel.DANGEROUS,
    "delete": PermissionLevel.DANGEROUS,
    "send_message": PermissionLevel.DANGEROUS,
    "purchase": PermissionLevel.DANGEROUS,
}


def classify_tool(tool_name: str, args: dict | None = None) -> PermissionLevel:
    """Classify a tool call by name (and, where relevant, its arguments).

    ``args`` is accepted for forward compatibility (e.g. a delete aimed
    at a system path could be escalated later); today classification is
    purely by name, with unknown tools defaulting to ``CAUTION``.
    """
    name = str(tool_name or "").strip().lower()
    if name in SAFE_TOOLS:
        return PermissionLevel.SAFE
    if name in CAUTION_TOOLS:
        return PermissionLevel.CAUTION
    if name in DANGEROUS_TOOLS:
        return PermissionLevel.DANGEROUS
    if name in _ALIASES:
        return _ALIASES[name]
    logger.warning("Unknown tool %r classified as CAUTION (fail closed)", tool_name)
    return PermissionLevel.CAUTION


def requires_approval(level: PermissionLevel) -> bool:
    """Return True when ``level`` needs user approval before running."""
    return level in (PermissionLevel.CAUTION, PermissionLevel.DANGEROUS)


def describe_level(level: PermissionLevel) -> str:
    """Return a short human-readable description of a permission level."""
    descriptions = {
        PermissionLevel.SAFE: "Safe: read-only or reversible, no approval needed.",
        PermissionLevel.CAUTION: (
            "Caution: changes files, runs a command, or leaves the machine -- "
            "needs your approval first."
        ),
        PermissionLevel.DANGEROUS: (
            "Dangerous: destructive or hard to undo (delete, admin, send, "
            "submit, install) -- needs your explicit confirmation."
        ),
    }
    return descriptions.get(level, f"Unknown permission level: {level!r}")
