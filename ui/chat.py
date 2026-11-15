"""Chat widget for NOOBRA — the scrollable message list.

A :class:`ChatWidget` shows user / assistant / system messages in a
scroll area, keeps an in-memory ``history`` list of ``(role, text)``
tuples, and auto-scrolls to the newest message.
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

logger = logging.getLogger("noobra.ui.chat")

_ROLE_STYLES = {
    "user": (
        "#1e3a5f", "#ffffff", "You",
        "margin-left: 60px; margin-right: 4px; text-align: left;",
    ),
    "assistant": (
        "#2a2a2a", "#e8e8e8", "NOOBRA",
        "margin-right: 60px; margin-left: 4px; text-align: left;",
    ),
    "system": (
        "#3a2a4a", "#c9b8e8", "System",
        "margin-left: 40px; margin-right: 40px; text-align: center;",
    ),
}


class ChatWidget(QWidget):
    """Scrollable chat transcript with typed add_* helpers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.history: list[tuple[str, str]] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: #121212; }")

        self._container = QWidget()
        self._messages_layout = QVBoxLayout(self._container)
        self._messages_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._messages_layout.setSpacing(8)
        self._scroll.setWidget(self._container)
        self._layout.addWidget(self._scroll)

    # -- public API ----------------------------------------------------
    def add_user_message(self, text: str) -> None:
        self._add_message("user", text)

    def add_assistant_message(self, text: str) -> None:
        self._add_message("assistant", text)

    def add_system_message(self, text: str) -> None:
        self._add_message("system", text)

    def clear(self) -> None:
        """Remove all messages from the view and from history."""
        self.history.clear()
        while self._messages_layout.count():
            item = self._messages_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        logger.debug("ChatWidget cleared")

    def message_count(self) -> int:
        return len(self.history)

    # -- internals -----------------------------------------------------
    def _add_message(self, role: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self.history.append((role, text))
        bg, fg, sender, margin = _ROLE_STYLES.get(role, _ROLE_STYLES["assistant"])
        bubble = QLabel(f"<b>{sender}</b><br>{_escape(text)}")
        bubble.setWordWrap(True)
        bubble.setTextFormat(Qt.TextFormat.RichText)
        bubble.setStyleSheet(
            f"background: {bg}; color: {fg}; border-radius: 10px; "
            f"padding: 8px 12px; {margin}"
        )
        self._messages_layout.addWidget(bubble)
        # Scroll to bottom after layout settles.
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        logger.debug("ChatWidget: added %s message (%d chars)", role, len(text))


def _escape(text: str) -> str:
    """Minimal HTML escaping so message text cannot inject markup."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )
