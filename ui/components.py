"""Reusable UI components for NOOBRA.

Includes :class:`AnimatedOrb` — a genuinely animated QWidget (real
``QTimer`` + ``paintEvent`` gradient pulse, no static image), a status
badge, a progress-bar helper and an activity label.

PySide6 is imported normally at the top of this module, per the
project contract. Code that must run without PySide6 (tests, CLI)
should import this module only via ``pytest.importorskip`` or a
guarded ``try/except ImportError``.
"""

import logging
import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QLabel, QProgressBar, QWidget

logger = logging.getLogger("noobra.ui.components")

# ---------------------------------------------------------------------------
# Status states
# ---------------------------------------------------------------------------
# Canonical state names shared with main_window.py. Colours / speeds are
# defined per state so the orb, badge and activity label stay consistent.
STATE_STYLES = {
    "Waiting":   {"color": QColor("#8b5cf6"), "speed_ms": 120, "label": "Waiting"},
    "Thinking":  {"color": QColor("#00aaff"), "speed_ms": 60,  "label": "Thinking…"},
    "Listening": {"color": QColor("#22c55e"), "speed_ms": 80,  "label": "Listening…"},
    "Speaking":  {"color": QColor("#f59e0b"), "speed_ms": 50,  "label": "Speaking…"},
    "Executing": {"color": QColor("#00aaff"), "speed_ms": 40,  "label": "Working…"},
    "Completed": {"color": QColor("#22c55e"), "speed_ms": 120, "label": "Done"},
    "Failed":    {"color": QColor("#ef4444"), "speed_ms": 200, "label": "Failed"},
}

VALID_STATES = tuple(STATE_STYLES.keys())


class AnimatedOrb(QWidget):
    """Pulsing gradient orb drawn with QPainter, animated by a QTimer.

    The orb breathes (radius oscillates with a sine wave) and its
    colour / pulse speed change with :meth:`set_state`. This is real
    animation, not a static image.
    """

    def __init__(self, parent=None, diameter: int = 120):
        super().__init__(parent)
        self.setFixedSize(diameter, diameter)
        self._state = "Waiting"
        self._phase = 0.0
        self._color = STATE_STYLES["Waiting"]["color"]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(STATE_STYLES["Waiting"]["speed_ms"])
        logger.debug("AnimatedOrb created, state=Waiting")

    # -- state ---------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        """Change orb colour / speed. Unknown states fall back to Waiting."""
        if state not in STATE_STYLES:
            logger.warning("AnimatedOrb: unknown state %r, using Waiting", state)
            state = "Waiting"
        self._state = state
        style = STATE_STYLES[state]
        self._color = style["color"]
        self._timer.setInterval(style["speed_ms"])
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    # -- animation -----------------------------------------------------
    def _on_tick(self) -> None:
        self._phase += 0.15
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width(), self.height())
        centre = self.rect().center()
        # Breathing pulse: radius oscillates between ~32% and ~46% of size.
        pulse = 0.5 + 0.5 * math.sin(self._phase)
        radius = size * (0.32 + 0.14 * pulse)
        gradient = QRadialGradient(centre, radius)
        base = self._color
        gradient.setColorAt(0.0, QColor(base.red(), base.green(), base.blue(), 255))
        gradient.setColorAt(0.6, QColor(base.red(), base.green(), base.blue(), 160))
        gradient.setColorAt(1.0, QColor(base.red(), base.green(), base.blue(), 0))
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(centre, int(radius), int(radius))
        # Inner bright core.
        core_radius = max(4, int(radius * 0.45))
        core = QRadialGradient(centre, core_radius)
        core.setColorAt(0.0, QColor(255, 255, 255, 220))
        core.setColorAt(1.0, QColor(base.red(), base.green(), base.blue(), 0))
        painter.setBrush(core)
        painter.drawEllipse(centre, core_radius, core_radius)


class StatusBadge(QLabel):
    """Small coloured pill showing the current agent status."""

    def __init__(self, parent=None):
        super().__init__("● Waiting", parent)
        self._state = "Waiting"
        self.set_state("Waiting")

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        if state not in STATE_STYLES:
            state = "Waiting"
        self._state = state
        color = STATE_STYLES[state]["color"].name()
        label = STATE_STYLES[state]["label"]
        self.setText(f"● {label}")
        self.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 13px; "
            "background: transparent;"
        )


class ProgressBar(QProgressBar):
    """Thin styled progress bar; indeterminate while busy, 0/100 at rest."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimum(0)
        self.setMaximum(100)
        self.setValue(0)
        self.setTextVisible(False)
        self.setFixedHeight(6)
        self.setStyleSheet(
            "QProgressBar { background: #2a2a2a; border: none; border-radius: 3px; }"
            "QProgressBar::chunk { background: #00aaff; border-radius: 3px; }"
        )

    def set_busy(self, busy: bool) -> None:
        """Switch between indeterminate (busy) and idle (0%)."""
        if busy:
            self.setMinimum(0)
            self.setMaximum(0)  # Qt indeterminate mode
        else:
            self.setMinimum(0)
            self.setMaximum(100)
            self.setValue(0)

    def set_progress(self, percent: int) -> None:
        self.setMinimum(0)
        self.setMaximum(100)
        self.setValue(max(0, min(100, int(percent))))


class ActivityLabel(QLabel):
    """One-line label describing what the agent is currently doing."""

    def __init__(self, parent=None):
        super().__init__("Ready. Type a command or press the mic.", parent)
        self.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        self.setWordWrap(True)

    def set_activity(self, text: str) -> None:
        self.setText(text or "")

    def set_state(self, state: str) -> None:
        """Convenience: show the human label for a state."""
        if state in STATE_STYLES:
            self.setText(STATE_STYLES[state]["label"])
