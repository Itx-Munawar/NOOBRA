"""Text-to-speech for NOOBRA using edge-tts (free Microsoft Edge voices).

``edge-tts`` is an optional, guarded import and is only loaded lazily when
speech is actually requested, so this module imports cleanly without it.
Synthesis writes an MP3 to a temp file, which is then played back with
``ffplay`` (preferred, if installed), ``pygame`` if available, or -- as a
last resort -- just left as a saved file (``speak`` still returns ``True``
and logs where the audio was saved). Roman Urdu text is passed through
as-is; edge-tts renders it as text.

Default voice ``en-IN-NeerjaNeural`` is a natural Indian-English voice
that handles Roman Urdu reasonably; callers may pass any edge-tts voice.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

logger = logging.getLogger("noobra.voice")

try:  # Optional dependency, loaded lazily in practice.
    import edge_tts
except ImportError:  # pragma: no cover
    edge_tts = None

try:
    import pygame
except ImportError:  # pragma: no cover
    pygame = None

_DEFAULT_VOICES = [
    "en-IN-NeerjaNeural",
    "en-IN-PrabhatNeural",
    "en-US-AriaNeural",
    "en-GB-SoniaNeural",
    "ur-PK-AsadNeural",
    "ur-PK-UzmaNeural",
]


class TextToSpeech:
    """Edge-TTS synthesis with threaded playback and stop support."""

    def __init__(self, voice: str = "en-IN-NeerjaNeural"):
        self.voice = voice
        self._muted = False
        self._speaking = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._player: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._last_audio_path: Path | None = None

    # -- state ----------------------------------------------------------------
    @property
    def is_muted(self) -> bool:
        return self._muted

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def set_muted(self, muted: bool) -> None:
        """Mute/unmute. Muting also stops any speech in progress."""
        self._muted = bool(muted)
        if self._muted:
            self.stop()
        logger.info("TTS %s", "muted" if self._muted else "unmuted")

    # -- synthesis --------------------------------------------------------------
    def _synthesize(self, text: str) -> Path | None:
        """Synthesise ``text`` to a temp MP3; returns its path or None."""
        if edge_tts is None:
            logger.error("edge-tts not installed; cannot synthesise speech")
            return None
        tmp = Path(tempfile.mktemp(suffix=".mp3"))
        try:
            async def _run():
                communicate = edge_tts.Communicate(text, self.voice)
                await communicate.save(str(tmp))

            asyncio.run(_run())
        except RuntimeError:
            # Already inside a running event loop (e.g. called from async
            # code): run the coroutine on a fresh loop in a helper thread.
            loop_holder: dict = {}

            def _target():
                loop = asyncio.new_event_loop()
                loop_holder["loop"] = loop
                try:
                    loop.run_until_complete(
                        edge_tts.Communicate(text, self.voice).save(str(tmp)))
                finally:
                    loop.close()

            worker = threading.Thread(target=_target, daemon=True)
            worker.start()
            worker.join()
        except Exception:
            logger.exception("edge-tts synthesis failed")
            return None
        if not tmp.is_file() or tmp.stat().st_size == 0:
            logger.error("edge-tts produced no audio for text %r", text[:50])
            return None
        self._last_audio_path = tmp
        return tmp

    def _play_file(self, audio_path: Path) -> bool:
        """Play an MP3: ffplay first, pygame second, saved-file fallback."""
        ffplay = shutil.which("ffplay")
        if ffplay:
            try:
                self._player = subprocess.Popen(
                    [ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet",
                     str(audio_path)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._player.wait()
                return self._player.returncode in (0, None) \
                    or self._stop_event.is_set()
            except Exception:
                logger.exception("ffplay playback failed")
            finally:
                self._player = None
        if pygame is not None:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(str(audio_path))
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    if self._stop_event.is_set():
                        pygame.mixer.music.stop()
                        break
                    pygame.time.wait(100)
                return True
            except Exception:
                logger.exception("pygame playback failed")
        # No player available: the MP3 is saved; report success with a note.
        logger.warning(
            "No audio player (ffplay/pygame) found; audio saved to %s",
            audio_path)
        return True

    def _speak_sync(self, text: str) -> bool:
        if self._muted:
            logger.info("TTS muted; not speaking")
            return False
        if not text or not text.strip():
            logger.warning("TTS called with empty text")
            return False
        self._stop_event.clear()
        self._speaking = True
        try:
            audio_path = self._synthesize(text.strip())
            if audio_path is None:
                return False
            if self._stop_event.is_set():
                return False
            return self._play_file(audio_path)
        finally:
            self._speaking = False
            self._player = None

    # -- public API ---------------------------------------------------------------
    def speak(self, text: str) -> bool:
        """Synthesise and play ``text`` synchronously. Returns success."""
        with self._lock:
            return self._speak_sync(text)

    def speak_async(self, text: str) -> threading.Thread:
        """Speak in a background daemon thread; returns the thread."""
        thread = threading.Thread(target=self._speak_sync, args=(text,),
                                  daemon=True)
        self._thread = thread
        thread.start()
        return thread

    def stop(self) -> None:
        """Interrupt any speech in progress."""
        self._stop_event.set()
        player = self._player
        if player is not None and player.poll() is None:
            try:
                player.terminate()
            except Exception:
                logger.debug("Could not terminate ffplay", exc_info=True)
        if pygame is not None:
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.music.stop()
            except Exception:
                pass
        self._speaking = False

    def get_available_voices(self) -> list:
        """Return known voices (edge-tts list when available, else defaults).

        Querying the live edge-tts voice list needs network; the curated
        default list is returned if that lookup fails or edge-tts is
        missing, so callers always get usable voice names.
        """
        if edge_tts is None:
            return list(_DEFAULT_VOICES)
        try:
            async def _run():
                return await edge_tts.list_voices()

            voices = asyncio.run(_run())
            names = [v.get("ShortName") for v in voices if v.get("ShortName")]
            return names or list(_DEFAULT_VOICES)
        except Exception:
            logger.debug("Could not list edge-tts voices; using defaults",
                         exc_info=True)
            return list(_DEFAULT_VOICES)
