"""Configuration for NOOBRA.

Settings come from (in increasing priority): built-in defaults,
``settings.json`` in the app-data directory, then environment variables
(and a ``.env`` file, loaded via python-dotenv when available).

API keys are **never** hardcoded and are **never** written to
``settings.json`` -- they live only in the environment / ``.env``.
"""

from __future__ import annotations

import json
import logging
import os
import platform
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger("noobra.core.config")

try:  # python-dotenv is optional; missing it must not break import.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv absent
    load_dotenv = None  # type: ignore[assignment]

# Fields that are secrets and must never be persisted to settings.json.
_SECRET_FIELDS = {"gemini_api_key", "groq_api_key", "openrouter_api_key"}

_SETTINGS: "Settings | None" = None


def app_data_dir() -> Path:
    """Return the per-user NOOBRA data directory.

    Windows: ``%APPDATA%/NOOBRA``; everywhere else: ``~/.noobra``.
    The directory is created on demand by :func:`settings_path`.
    """
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "NOOBRA"
    return Path.home() / ".noobra"


def settings_path() -> Path:
    """Return the path of ``settings.json`` (creating the dir if needed)."""
    directory = app_data_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # e.g. read-only home; callers handle missing file
        logger.warning("Could not create app data dir %s: %s", directory, exc)
    return directory / "settings.json"


@dataclass
class Settings:
    """All user-configurable NOOBRA settings."""

    provider: str = "gemini"
    gemini_model: str = "gemini-2.0-flash"
    groq_model: str = "llama-3.3-70b-versatile"
    openrouter_model: str = "openai/gpt-oss-20b:free"
    gemini_api_key: str = ""
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    fallback_providers: list = field(default_factory=lambda: ["groq", "openrouter"])
    voice_enabled: bool = True
    memory_enabled: bool = True

    def api_key_for(self, provider_name: str) -> str:
        """Return the configured API key for ``provider_name`` (or ``""``)."""
        mapping = {
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
            "openrouter": self.openrouter_api_key,
        }
        return mapping.get(str(provider_name).strip().lower(), "") or ""

    def model_for(self, provider_name: str) -> str:
        """Return the configured model name for ``provider_name``."""
        mapping = {
            "gemini": self.gemini_model,
            "groq": self.groq_model,
            "openrouter": self.openrouter_model,
        }
        return mapping.get(str(provider_name).strip().lower(), "") or ""


def _load_dotenv() -> None:
    """Load ``.env`` from the current directory / app-data dir, if possible."""
    if load_dotenv is None:
        return
    try:
        load_dotenv()  # searches upward from cwd
        env_file = app_data_dir() / ".env"
        if env_file.is_file():
            load_dotenv(dotenv_path=env_file, override=False)
    except Exception as exc:  # never let .env loading break startup
        logger.debug("Could not load .env: %s", exc)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    """Load settings fresh (defaults <- settings.json <- environment)."""
    _load_dotenv()
    settings = Settings()

    # 1. settings.json (non-secret fields only)
    path = settings_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, value in data.items():
                    if key in _SECRET_FIELDS:
                        continue  # keys never come from the JSON file
                    if hasattr(settings, key):
                        setattr(settings, key, value)
        except (OSError, ValueError) as exc:
            logger.warning("Could not read settings file %s: %s", path, exc)

    # 2. Environment variables override everything else.
    if os.environ.get("NOOBRA_PROVIDER"):
        settings.provider = os.environ["NOOBRA_PROVIDER"].strip().lower()
    if os.environ.get("GEMINI_MODEL"):
        settings.gemini_model = os.environ["GEMINI_MODEL"].strip()
    if os.environ.get("GROQ_MODEL"):
        settings.groq_model = os.environ["GROQ_MODEL"].strip()
    if os.environ.get("OPENROUTER_MODEL"):
        settings.openrouter_model = os.environ["OPENROUTER_MODEL"].strip()
    settings.gemini_api_key = os.environ.get("GEMINI_API_KEY", "") or settings.gemini_api_key
    settings.groq_api_key = os.environ.get("GROQ_API_KEY", "") or settings.groq_api_key
    settings.openrouter_api_key = (
        os.environ.get("OPENROUTER_API_KEY", "") or settings.openrouter_api_key
    )
    if os.environ.get("NOOBRA_FALLBACK_PROVIDERS"):
        settings.fallback_providers = [
            item.strip().lower()
            for item in os.environ["NOOBRA_FALLBACK_PROVIDERS"].split(",")
            if item.strip()
        ]
    settings.voice_enabled = _env_bool("NOOBRA_VOICE_ENABLED", settings.voice_enabled)
    settings.memory_enabled = _env_bool("NOOBRA_MEMORY_ENABLED", settings.memory_enabled)

    if settings.provider not in {"gemini", "groq", "openrouter"}:
        logger.warning("Unknown provider %r in settings; falling back to gemini", settings.provider)
        settings.provider = "gemini"
    return settings


def get_settings() -> Settings:
    """Return the cached settings, loading them on first use."""
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = load_settings()
    return _SETTINGS


def save_settings(settings: Settings) -> None:
    """Persist non-secret settings to ``settings.json``.

    API keys are deliberately excluded. Also refreshes the cached settings.
    """
    global _SETTINGS
    data = {k: v for k, v in asdict(settings).items() if k not in _SECRET_FIELDS}
    path = settings_path()
    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.error("Could not save settings to %s: %s", path, exc)
        raise
    _SETTINGS = settings
    logger.info("Settings saved to %s", path)
