"""NOOBRA main window (QMainWindow).

Dark theme (charcoal #121212 / #1e1e1e, electric blue #00aaff, purple
#8b5cf6), NOOBRA branding, animated orb, chat, text input + Send,
voice button, Stop button, progress bar, activity display, execution
history panel, provider selector and a settings button.

The agent runs in a QThread worker so the UI never blocks: an
instruction is sent to the worker, and replies / status updates come
back via Qt signals.
"""

import logging
from collections import deque

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QMainWindow, QPushButton, QTextEdit,
    QVBoxLayout, QWidget, QComboBox,
)

from ui.chat import ChatWidget
from ui.components import (
    ActivityLabel, AnimatedOrb, ProgressBar, StatusBadge, VALID_STATES,
)
from ui.settings import SettingsDialog

logger = logging.getLogger("noobra.ui.main_window")

DARK_STYLESHEET = """
QMainWindow, QWidget { background: #121212; color: #e8e8e8; font-family: Segoe UI, sans-serif; }
QTextEdit, QListWidget {
    background: #1e1e1e; color: #e8e8e8; border: 1px solid #333333;
    border-radius: 8px; padding: 6px;
}
QPushButton {
    background: #00aaff; color: #ffffff; border: none; border-radius: 8px;
    padding: 8px 16px; font-weight: bold;
}
QPushButton:hover { background: #0090dd; }
QPushButton:disabled { background: #333333; color: #888888; }
QPushButton#stopButton { background: #ef4444; }
QPushButton#voiceButton { background: #8b5cf6; }
QPushButton#settingsButton { background: #2a2a2a; }
QComboBox {
    background: #1e1e1e; color: #e8e8e8; border: 1px solid #333333;
    border-radius: 6px; padding: 4px 8px;
}
"""


class AgentWorker(QObject):
    """Runs ``NoobraAgent.handle_instruction`` off the UI thread."""

    finished = Signal(str)          # reply text
    failed = Signal(str)            # error text
    status = Signal(str, str)       # (state, activity text)

    def __init__(self, agent, instruction: str):
        super().__init__()
        self._agent = agent
        self._instruction = instruction
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True
        try:
            stop = getattr(self._agent, "stop", None)
            if callable(stop):
                stop()
        except Exception as exc:
            logger.debug("AgentWorker.stop: agent.stop() failed: %s", exc)

    def run(self) -> None:
        if self._stopped:
            self.finished.emit("")
            return
        self.status.emit("Thinking", "Thinking…")
        try:
            reply = self._agent.handle_instruction(self._instruction)
            if self._stopped:
                self.finished.emit("")
                return
            self.finished.emit(str(reply) if reply is not None else "")
        except Exception as exc:
            logger.exception("AgentWorker failed")
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    """The NOOBRA desktop window."""

    def __init__(self, agent=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NOOBRA — Personal AI Agent")
        self.setMinimumSize(900, 650)
        self.setStyleSheet(DARK_STYLESHEET)

        self._agent = agent
        self._thread: QThread | None = None
        self._worker: AgentWorker | None = None
        self._listening = False
        self._history: deque[str] = deque(maxlen=50)

        # -- widgets -------------------------------------------------
        self.orb = AnimatedOrb(self, diameter=110)
        self.status_badge = StatusBadge(self)
        self.activity_label = ActivityLabel(self)
        self.progress_bar = ProgressBar(self)
        self.chat = ChatWidget(self)
        self.chat.add_system_message(
            "Assalam-o-Alaikum! I'm NOOBRA. Ask me anything — Roman Urdu ya English, dono chalte hain."
        )

        self.input_box = QTextEdit(self)
        self.input_box.setPlaceholderText("Type a command… e.g. 'Desktop par Test folder banao'")
        self.input_box.setFixedHeight(64)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._on_send)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.clicked.connect(self._on_stop)
        self.stop_button.setEnabled(False)
        self.voice_button = QPushButton("🎤 Voice")
        self.voice_button.setObjectName("voiceButton")
        self.voice_button.clicked.connect(self._on_voice_toggle)
        self.settings_button = QPushButton("⚙ Settings")
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.clicked.connect(self._on_open_settings)

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["gemini", "groq", "openrouter"])
        self.provider_combo.setToolTip("AI provider (change in Settings to save)")
        try:
            from core.config import get_settings  # type: ignore

            self.provider_combo.setCurrentText(str(get_settings().provider))
        except Exception:
            self.provider_combo.setCurrentText("gemini")

        self.history_list = QListWidget(self)
        self.history_list.setFixedHeight(110)
        self.history_list.itemClicked.connect(self._on_history_clicked)

        # -- layout --------------------------------------------------
        top = QHBoxLayout()
        top.addWidget(self.orb)
        title_box = QVBoxLayout()
        title = QLabel("NOOBRA")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #00aaff;")
        subtitle = QLabel("Your personal AI agent — Roman Urdu + English")
        subtitle.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        title_box.addWidget(self.status_badge)
        title_box.addWidget(self.activity_label)
        top.addLayout(title_box)
        top.addStretch(1)
        provider_box = QVBoxLayout()
        provider_box.addWidget(QLabel("Provider:"))
        provider_box.addWidget(self.provider_combo)
        provider_box.addWidget(self.settings_button)
        top.addLayout(provider_box)

        input_row = QHBoxLayout()
        input_row.addWidget(self.input_box, stretch=1)
        input_row.addWidget(self.send_button)
        input_row.addWidget(self.stop_button)
        input_row.addWidget(self.voice_button)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(top)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.chat, stretch=1)
        layout.addLayout(input_row)
        layout.addWidget(QLabel("Execution history:"))
        layout.addWidget(self.history_list)
        self.setCentralWidget(central)

    # -- status ------------------------------------------------------
    def set_status(self, state: str, activity: str = "") -> None:
        if state not in VALID_STATES:
            state = "Waiting"
        self.orb.set_state(state)
        self.status_badge.set_state(state)
        self.activity_label.set_activity(activity or state)
        self.progress_bar.set_busy(state in ("Thinking", "Listening", "Speaking", "Executing"))

    # -- sending -----------------------------------------------------
    def _on_send(self) -> None:
        text = self.input_box.toPlainText().strip()
        if not text:
            return
        self.input_box.clear()
        self.send_instruction(text)

    def send_instruction(self, text: str) -> None:
        """Show the message and run it in a worker thread."""
        self.chat.add_user_message(text)
        self._history.append(text)
        self.history_list.addItem(text)
        if self._agent is None:
            self.chat.add_system_message(
                "Agent is not available in this session. Run the full app (python main.py) "
                "with the core modules installed."
            )
            return
        if self._thread is not None and self._thread.isRunning():
            self.chat.add_system_message("Please wait — I'm still working on the last request.")
            return
        self.set_status("Thinking", "Thinking…")
        self.send_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self._thread = QThread(self)
        self._worker = AgentWorker(self._agent, text)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_agent_finished)
        self._worker.failed.connect(self._on_agent_failed)
        self._worker.status.connect(self.set_status)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _on_agent_finished(self, reply: str) -> None:
        if reply:
            self.chat.add_assistant_message(reply)
            self._speak(reply)
        self.set_status("Completed", "Done.")
        self.send_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _on_agent_failed(self, error: str) -> None:
        self.chat.add_system_message(f"Something went wrong: {error}")
        self.set_status("Failed", f"Failed: {error}")
        self.send_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _cleanup_thread(self) -> None:
        self._worker = None
        self._thread = None

    def _on_stop(self) -> None:
        if self._worker is not None:
            self._worker.stop()
        try:
            if self._agent is not None and hasattr(self._agent, "stop"):
                self._agent.stop()
        except Exception as exc:
            logger.debug("Stop: agent.stop() failed: %s", exc)
        self.set_status("Waiting", "Stopped.")
        self.send_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _on_history_clicked(self, item) -> None:
        self.input_box.setPlainText(item.text())

    # -- voice -------------------------------------------------------
    def _on_voice_toggle(self) -> None:
        """Toggle listening via the voice module, guarded for Linux/no-mic."""
        self._listening = not self._listening
        if not self._listening:
            self.set_status("Waiting", "Stopped listening.")
            self.voice_button.setText("🎤 Voice")
            return
        self.set_status("Listening", "Listening… speak now.")
        self.voice_button.setText("⏹ Stop listening")
        try:
            from voice.speech_to_text import SpeechToText  # type: ignore
        except Exception as exc:
            self._listening = False
            self.voice_button.setText("🎤 Voice")
            self.chat.add_system_message(
                f"Voice input is not available here ({exc}). Type your command instead."
            )
            logger.debug("Voice unavailable: %s", exc)
            return
        try:
            result = SpeechToText().listen_once()
        except Exception as exc:
            self.chat.add_system_message(f"Voice listening failed: {exc}")
            self.set_status("Waiting", "Ready.")
            self._listening = False
            self.voice_button.setText("🎤 Voice")
            return
        self._listening = False
        self.voice_button.setText("🎤 Voice")
        # listen_once returns {"success": bool, "text": str, "error": ...}.
        text = result.get("text", "") if isinstance(result, dict) else str(result or "")
        if result.get("success") and text:
            self.input_box.setPlainText(text)
            self.send_instruction(text)
        elif not result.get("success"):
            self.chat.add_system_message(
                f"Voice input unavailable: {result.get('error', 'unknown error')}. "
                "Type your command instead."
            )
            self.set_status("Waiting", "Ready.")
        else:
            self.set_status("Waiting", "Didn't catch that — try typing.")

    def _speak(self, text: str) -> None:
        """Best-effort speech output; silently skipped if voice is absent."""
        try:
            from voice.text_to_speech import TextToSpeech  # type: ignore

            TextToSpeech().speak(text)
        except Exception as exc:
            logger.debug("Speech output unavailable: %s", exc)

    # -- settings ----------------------------------------------------
    def _on_open_settings(self) -> None:
        dialog = SettingsDialog(self)
        if dialog.exec():
            try:
                from core.config import get_settings  # type: ignore

                self.provider_combo.setCurrentText(str(get_settings().provider))
            except Exception:
                pass
            self.chat.add_system_message("Settings saved.")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._on_stop()
        super().closeEvent(event)
