"""NOOBRA voice package: speech-to-text, text-to-speech and wake-word.

All heavy / Windows-only dependencies (``faster-whisper``, ``edge-tts``,
``sounddevice``, ``pygame``) are imported lazily and guarded, so this
package imports cleanly on Linux even when none of them are installed.
Unavailable features return a clear error dict / ``False`` instead of
crashing on import.
"""

from .speech_to_text import SpeechToText
from .text_to_speech import TextToSpeech
from .wakeword import WakeWordListener

__all__ = ["SpeechToText", "TextToSpeech", "WakeWordListener"]
