"""Wake-word listener for NOOBRA.

Listens in a background thread, transcribing short microphone chunks
with :class:`noobra.voice.speech_to_text.SpeechToText` and calling
``on_wake(transcript)`` when the wake word appears (case-insensitive
substring match). No paid service is involved.

If speech-to-text / microphone capture is unavailable, :meth:`start`
logs a clear warning and does not start listening -- it never crashes.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger("noobra.voice")

try:
    from .speech_to_text import SpeechToText
except ImportError:  # pragma: no cover - defensive; same package
    SpeechToText = None  # type: ignore[assignment]


class WakeWordListener:
    """Background wake-word detection.

    Args:
        wake_word: word/phrase to listen for (default ``"noobra"``).
        on_wake: callable invoked as ``on_wake(transcript)`` on detection.
        stt: optional :class:`SpeechToText` instance to reuse; one is
            created lazily if omitted.
        chunk_seconds: length of each recorded chunk.
        poll_interval: pause between chunks (seconds).
    """

    def __init__(self, wake_word: str = "noobra", on_wake=None,
                 stt: SpeechToText | None = None,
                 chunk_seconds: float = 3.0, poll_interval: float = 0.2):
        self.wake_word = (wake_word or "noobra").lower()
        self.on_wake = on_wake
        self.stt = stt
        self.chunk_seconds = chunk_seconds
        self.poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def is_listening(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _ensure_stt(self):
        if self.stt is not None:
            return self.stt
        if SpeechToText is None:
            return None
        self.stt = SpeechToText()
        return self.stt

    def _loop(self) -> None:
        stt = self._ensure_stt()
        if stt is None or not stt.is_available():
            logger.warning(
                "Wake-word listening unavailable: faster-whisper not"
                " installed (or no microphone support)")
            return
        logger.info("Wake-word listening started for %r", self.wake_word)
        while not self._stop_event.is_set():
            try:
                result = stt.listen_once(duration=self.chunk_seconds)
            except Exception:
                logger.exception("Wake-word chunk failed")
                result = {"success": False, "text": ""}
            if result.get("success") and result.get("text"):
                transcript = result["text"]
                if self.wake_word in transcript.lower():
                    logger.info("Wake word detected in: %r", transcript)
                    if self.on_wake is not None:
                        try:
                            self.on_wake(transcript)
                        except Exception:
                            logger.exception("on_wake callback failed")
            if self._stop_event.wait(self.poll_interval):
                break
        logger.info("Wake-word listening stopped")

    def start(self) -> bool:
        """Start the background listener. Returns False if unavailable."""
        if self.is_listening:
            logger.warning("Wake-word listener already running")
            return True
        stt = self._ensure_stt()
        if stt is None or not stt.is_available():
            logger.warning(
                "Cannot start wake-word listener: speech-to-text"
                " unavailable (faster-whisper not installed)")
            return False
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="noobra-wakeword")
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop the background listener (no-op if not running)."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5)
        self._thread = None
        logger.info("Wake-word listener stopped")
