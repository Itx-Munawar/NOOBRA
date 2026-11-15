"""NOOBRA core package: config, context, permissions, planner, executor, agent.

All modules are platform-independent: no Windows-only imports at module
level, so the package imports cleanly on Linux (build/test env) as well as
on Windows 11 (target).
"""

from .config import Settings, app_data_dir, get_settings, load_settings, save_settings, settings_path
from .context import ConversationContext
from .permissions import PermissionLevel, classify_tool, describe_level, requires_approval

__all__ = [
    "Settings",
    "app_data_dir",
    "get_settings",
    "load_settings",
    "save_settings",
    "settings_path",
    "ConversationContext",
    "PermissionLevel",
    "classify_tool",
    "describe_level",
    "requires_approval",
]
