"""Settings dialog / panel for NOOBRA.

Lets the user pick a provider (gemini / groq / openrouter), edit model
names, and enter API keys. Keys are shown with password echo and the
placeholder "from .env — leave blank to use env"; they are **never**
printed or logged. Saving goes through ``core.config.save_settings``
when available and writes a ``.env`` note (keys only when the user
typed a new one). The dialog must not crash if ``core.config`` is
missing or incomplete — it falls back to plain defaults.
"""

import logging
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QLineEdit, QMessageBox, QVBoxLayout, QWidget,
)

logger = logging.getLogger("noobra.ui.settings")

PROVIDERS = ["gemini", "groq", "openrouter"]
KEY_PLACEHOLDER = "from .env — leave blank to use env"

_DEFAULTS = {
    "provider": "gemini",
    "gemini_model": "gemini-2.0-flash",
    "groq_model": "llama-3.3-70b-versatile",
    "openrouter_model": "openai/gpt-oss-20b:free",
    "voice_enabled": True,
    "memory_enabled": True,
}


def _load_current() -> dict:
    """Best-effort load of current settings; never raises."""
    data = dict(_DEFAULTS)
    try:
        from core.config import get_settings  # type: ignore

        settings = get_settings()
        for key in _DEFAULTS:
            value = getattr(settings, key, None)
            if value is not None:
                data[key] = value
        # Provider attribute may be named differently; keep it simple.
        provider = getattr(settings, "provider", None)
        if provider:
            data["provider"] = str(provider)
    except Exception as exc:  # config missing / incomplete — use defaults
        logger.debug("Settings: could not load core.config (%s); using defaults", exc)
    return data


def _save_settings(data: dict, keys: dict) -> None:
    """Persist settings via core.config when available; else write .env.

    ``keys`` maps env-var name -> value; blank values are *not* written,
    so existing .env keys are preserved. Keys are never logged.
    """
    saved_via_config = False
    try:
        # core.config.save_settings expects a Settings object, not a dict.
        from core.config import Settings, get_settings, save_settings  # type: ignore

        current = get_settings()
        merged = {
            "provider": data.get("provider", current.provider),
            "gemini_model": data.get("gemini_model", current.gemini_model),
            "groq_model": data.get("groq_model", current.groq_model),
            "openrouter_model": data.get("openrouter_model", current.openrouter_model),
            "voice_enabled": data.get("voice_enabled", current.voice_enabled),
            "memory_enabled": data.get("memory_enabled", current.memory_enabled),
        }
        settings_obj = Settings(
            gemini_api_key=current.gemini_api_key,
            groq_api_key=current.groq_api_key,
            openrouter_api_key=current.openrouter_api_key,
            fallback_providers=current.fallback_providers,
            **merged,
        )
        save_settings(settings_obj)
        saved_via_config = True
    except Exception as exc:
        logger.debug("Settings: core.config.save_settings unavailable (%s)", exc)

    # Write any newly entered keys to .env (preserving existing lines).
    new_keys = {k: v for k, v in keys.items() if v}
    if new_keys:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        existing: dict[str, str] = {}
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, _, v = line.partition("=")
                    existing[k.strip()] = v.strip()
        existing.update(new_keys)
        # Also mirror the non-secret settings into .env for the CLI.
        existing.setdefault("NOOBRA_PROVIDER", str(data.get("provider", "gemini")))
        env_path.write_text(
            "".join(f"{k}={v}\n" for k, v in existing.items()), encoding="utf-8"
        )
        logger.info("Settings: wrote %d new key(s) to .env", len(new_keys))
    if not saved_via_config and not new_keys:
        logger.info("Settings: nothing persisted (no config module, no new keys)")


class SettingsPanel(QWidget):
    """The editable settings form; usable standalone or inside a dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = _load_current()

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(PROVIDERS)
        self.provider_combo.setCurrentText(str(self._current.get("provider", "gemini")))

        self.gemini_model_edit = QLineEdit(str(self._current.get("gemini_model", "")))
        self.groq_model_edit = QLineEdit(str(self._current.get("groq_model", "")))
        self.openrouter_model_edit = QLineEdit(str(self._current.get("openrouter_model", "")))

        self.gemini_key_edit = QLineEdit()
        self.gemini_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_key_edit.setPlaceholderText(KEY_PLACEHOLDER)
        self.groq_key_edit = QLineEdit()
        self.groq_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.groq_key_edit.setPlaceholderText(KEY_PLACEHOLDER)
        self.openrouter_key_edit = QLineEdit()
        self.openrouter_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.openrouter_key_edit.setPlaceholderText(KEY_PLACEHOLDER)

        self.voice_checkbox = QCheckBox("Enable voice (mic + speech)")
        self.voice_checkbox.setChecked(bool(self._current.get("voice_enabled", True)))
        self.memory_checkbox = QCheckBox("Enable memory (remember preferences)")
        self.memory_checkbox.setChecked(bool(self._current.get("memory_enabled", True)))

        # Permission level display (read-only; set in core.permissions).
        level_text = "unknown"
        try:
            from core.permissions import PermissionLevel  # type: ignore

            level_text = ", ".join(level.name for level in PermissionLevel)
        except Exception:
            level_text = "SAFE / CAUTION / DANGEROUS (see core.permissions)"
        self.permission_label = QLabel(f"Permission levels: {level_text}")
        self.permission_label.setWordWrap(True)
        self.permission_label.setStyleSheet("color: #aaaaaa; font-size: 12px;")

        form = QFormLayout()
        form.addRow("Provider:", self.provider_combo)
        form.addRow("Gemini model:", self.gemini_model_edit)
        form.addRow("Groq model:", self.groq_model_edit)
        form.addRow("OpenRouter model:", self.openrouter_model_edit)
        form.addRow("Gemini API key:", self.gemini_key_edit)
        form.addRow("Groq API key:", self.groq_key_edit)
        form.addRow("OpenRouter API key:", self.openrouter_key_edit)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.voice_checkbox)
        layout.addWidget(self.memory_checkbox)
        layout.addWidget(self.permission_label)
        layout.addWidget(QLabel(
            "Keys are stored in .env only if you type a new one here. "
            "Leave blank to keep using the environment / .env."))
        layout.addStretch(1)

    def collect(self) -> tuple[dict, dict]:
        """Return (settings dict, new-keys dict). Keys dict may be empty."""
        data = {
            "provider": self.provider_combo.currentText(),
            "gemini_model": self.gemini_model_edit.text().strip() or _DEFAULTS["gemini_model"],
            "groq_model": self.groq_model_edit.text().strip() or _DEFAULTS["groq_model"],
            "openrouter_model": self.openrouter_model_edit.text().strip()
            or _DEFAULTS["openrouter_model"],
            "voice_enabled": self.voice_checkbox.isChecked(),
            "memory_enabled": self.memory_checkbox.isChecked(),
        }
        keys = {
            "GEMINI_API_KEY": self.gemini_key_edit.text().strip(),
            "GROQ_API_KEY": self.groq_key_edit.text().strip(),
            "OPENROUTER_API_KEY": self.openrouter_key_edit.text().strip(),
        }
        return data, keys

    def save(self) -> bool:
        """Persist the current form values. Returns True on success."""
        try:
            data, keys = self.collect()
            _save_settings(data, keys)
            # Clear key fields after saving so keys don't linger on screen.
            for edit in (self.gemini_key_edit, self.groq_key_edit, self.openrouter_key_edit):
                edit.clear()
            return True
        except Exception as exc:
            logger.exception("Settings: save failed: %s", exc)
            return False


class SettingsDialog(QDialog):
    """Modal dialog wrapping :class:`SettingsPanel` with OK / Cancel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NOOBRA Settings")
        self.setMinimumWidth(420)
        self.panel = SettingsPanel(self)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.panel)
        layout.addWidget(buttons)

    def _on_save(self) -> None:
        if self.panel.save():
            self.accept()
        else:
            QMessageBox.warning(self, "NOOBRA", "Could not save settings. See logs.")
