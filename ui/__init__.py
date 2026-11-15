"""NOOBRA UI package (Workstream 4).

PySide6 widgets for the Windows 11 desktop app. Imports are guarded
here so that ``import NOOBRA.ui`` (or plain ``import ui``) does not crash
on a headless / PySide6-less machine — the individual modules import
PySide6 normally at their top level, as required, and this package
re-exports them only when available.
"""

__all__ = ["AnimatedOrb", "StatusBadge", "ProgressBar", "ActivityLabel",
           "ChatWidget", "SettingsDialog", "SettingsPanel", "MainWindow"]

try:
    from ui.components import (  # type: ignore
        ActivityLabel, AnimatedOrb, ProgressBar, StatusBadge,
    )
    from ui.chat import ChatWidget  # type: ignore
    from ui.settings import SettingsDialog, SettingsPanel  # type: ignore
    from ui.main_window import MainWindow  # type: ignore
except Exception:  # ImportError (no PySide6) or missing display, etc.
    AnimatedOrb = None  # type: ignore
    StatusBadge = None  # type: ignore
    ProgressBar = None  # type: ignore
    ActivityLabel = None  # type: ignore
    ChatWidget = None  # type: ignore
    SettingsDialog = None  # type: ignore
    SettingsPanel = None  # type: ignore
    MainWindow = None  # type: ignore
