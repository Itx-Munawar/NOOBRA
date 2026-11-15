"""Google Gemini provider (primary, free tier).

Uses the Gemini REST API directly via :mod:`requests` -- no Google SDK
needed. Model defaults to ``gemini-3.8-flash`` (free), configurable via
``Settings.gemini_model`` / ``GEMINI_MODEL``.
"""

from __future__ import annotations

import logging

import requests

from .provider import (
    AuthError,
    BaseProvider,
    ChatMessage,
    ProviderError,
    RateLimitError,
    ToolDefinition,
    raise_for_status_code,
)
from .provider import REQUEST_TIMEOUT

logger = logging.getLogger("noobra.ai.gemini")


class GeminiProvider(BaseProvider):
    """Gemini provider via ``generativelanguage.googleapis.com``."""

    name = "gemini"
    model = "gemini-3.8-flash"

    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.3,
    ) -> str:
        if not self.has_key():
            raise AuthError("Gemini API key is not configured (set GEMINI_API_KEY)")
        system_text, contents = self._to_gemini_messages(messages, tools)
        body: dict = {
            "systemInstruction": {"parts": [{"text": system_text}]},
            "contents": contents,
            "generationConfig": {"temperature": float(temperature)},
        }
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        try:
            response = requests.post(url, json=body, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            raise ProviderError(f"Gemini request failed: {exc}") from exc
        if response.status_code != 200:
            raise_for_status_code(response.status_code, response.text, "Gemini")
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(f"Gemini returned invalid JSON: {exc}") from exc
        try:
            candidates = data.get("candidates") or []
            parts = candidates[0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        except (IndexError, KeyError, TypeError) as exc:
            raise ProviderError(f"Gemini reply had no text content: {data!r}") from exc
        if not text:
            # A blocked / empty reply still counts as a provider failure.
            raise ProviderError(f"Gemini returned an empty reply: {data!r}")
        return text

    @staticmethod
    def _to_gemini_messages(messages, tools):
        """Split system messages out; map roles to Gemini's user/model roles."""
        system_parts = []
        contents = []
        for msg in messages:
            role = (msg.role or "user").lower()
            if role == "system":
                system_parts.append(msg.content)
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": msg.content}]})
            else:  # "user" and "tool" both arrive as user turns
                contents.append({"role": "user", "parts": [{"text": msg.content}]})
        if tools:
            tool_text = "\n".join(
                f"- {t.name}: {t.description} Parameters (JSON schema): {t.parameters}"
                for t in tools
            )
            system_parts.append(
                "You may use these tools by naming them in your plan/reply:\n" + tool_text
            )
        system_text = "\n".join(system_parts) or (
            "You are NOOBRA, a helpful personal AI desktop assistant. "
            "Reply in the same language mix (English / Roman Urdu) as the user."
        )
        if not contents:  # Gemini requires at least one content turn
            contents.append({"role": "user", "parts": [{"text": "Hello"}]})
        return system_text, contents
