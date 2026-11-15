"""Speech-to-text for NOOBRA using faster-whisper (free, local).

``faster-whisper``, ``sounddevice`` and ``numpy`` are optional, guarded
imports: on a machine without them (e.g. this Linux build env) the module
still imports, ``is_available()`` returns ``False`` and every method
returns a clear ``{"success": False, "error": ...}`` dict instead of
crashing. The Whisper model is loaded lazily on first use.
"""

from __future__ import annotations

import logging
import os
import tempfile
import wave
from pathlib import Path
from typing import Any

logger = logging.getLogger("noobra.voice")

try:  # Optional heavy dependency.
    from faster_whisper import WhisperModel
except ImportError:  # pragma: no cover - missing in build env
    WhisperModel = None  # type: ignore[assignment]

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover
    sd = None

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


class SpeechToText:
    """Local Whisper transcription.

    Args:
        model_size: faster-whisper model, e.g. ``"tiny"``, ``"base"``,
            ``"small"``. ``"base"`` is a good CPU default.
        device: ``"cpu"`` (default) or ``"cuda"``.
        compute_type: passed to WhisperModel, ``"int8"`` on CPU.
    """

    def __init__(self, model_size: str = "base", device: str = "cpu",
                 compute_type: str = "int8"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model: Any = None

    # -- availability -------------------------------------------------------
    def is_available(self) -> bool:
        """True only if faster-whisper is importable in this environment."""
        return WhisperModel is not None

    def _load_model(self):
        if self._model is not None:
            return self._model
        if WhisperModel is None:
            raise RuntimeError(
                "faster-whisper not installed. Install it with:"
                " pip install faster-whisper")
        logger.info("Loading Whisper model %r on %s", self.model_size,
                    self.device)
        self._model = WhisperModel(
            self.model_size, device=self.device,
            compute_type=self.compute_type)
        return self._model

    # -- transcription ------------------------------------------------------
    def transcribe_file(self, path: str | Path) -> dict:
        """Transcribe an audio file.

        Returns ``{"success": bool, "text": str, "language": str|None,
        "error": str|None}``.
        """
        path = Path(path)
        if not path.is_file():
            return {"success": False, "text": "",
                    "language": None, "error": f"Audio file not found: {path}"}
        if WhisperModel is None:
            return {"success": False, "text": "", "language": None,
                    "error": "faster-whisper not installed"}
        try:
            model = self._load_model()
            segments, info = model.transcribe(str(path))
            text = " ".join(seg.text.strip() for seg in segments).strip()
            language = getattr(info, "language", None)
            return {"success": True, "text": text,
                    "language": language, "error": None}
        except Exception as exc:  # noqa: BLE001 - surface as error dict
            logger.exception("Transcription failed for %s", path)
            return {"success": False, "text": "", "language": None,
                    "error": str(exc)}

    def transcribe_audio_bytes(self, audio_bytes: bytes,
                               sample_rate: int = 16000) -> dict:
        """Transcribe raw 16-bit PCM mono audio bytes via a temp WAV file."""
        if WhisperModel is None:
            return {"success": False, "text": "", "language": None,
                    "error": "faster-whisper not installed"}
        if not audio_bytes:
            return {"success": False, "text": "", "language": None,
                    "error": "Empty audio data"}
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav",
                                           delete=False) as fh:
                tmp = fh.name
            with wave.open(tmp, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                wav.writeframes(audio_bytes)
            return self.transcribe_file(tmp)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Transcription of audio bytes failed")
            return {"success": False, "text": "", "language": None,
                    "error": str(exc)}
        finally:
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    # -- live capture ---------------------------------------------------------
    def listen_once(self, duration: float = 5,
                    sample_rate: int = 16000) -> dict:
        """Record ``duration`` seconds from the microphone and transcribe.

        Returns the same dict as :meth:`transcribe_file`. If no recorder
        is available, returns a clear error dict.
        """
        if sd is None or np is None:
            return {"success": False, "text": "", "language": None,
                    "error": "sounddevice/numpy not installed;"
                             " microphone recording unavailable"}
        if WhisperModel is None:
            return {"success": False, "text": "", "language": None,
                    "error": "faster-whisper not installed"}
        try:
            logger.info("Recording %.1fs of audio", duration)
            audio = sd.rec(int(duration * sample_rate),
                           samplerate=sample_rate, channels=1, dtype="int16")
            sd.wait()
            return self.transcribe_audio_bytes(
                audio.tobytes(), sample_rate=sample_rate)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Microphone recording failed")
            return {"success": False, "text": "", "language": None,
                    "error": str(exc)}
