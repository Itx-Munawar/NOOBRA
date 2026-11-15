"""Groq provider (secondary, free tier).

OpenAI-compatible chat-completions endpoint. Model defaults to
``openai/gpt-oss-20b``, configurable via ``Settings.groq_model`` /
``GROQ_MODEL``.
"""

from __future__ import annotations

import logging

import requests

from .provider import (
    AuthError,
    BaseProvider,
    ChatMessage,
    ProviderError,
    ToolDefinition,
    raise_for_status_code,
)
from .provider import REQUEST_TIMEOUT

logger = logging.getLogger("noobra.ai.groq")

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider(BaseProvider):
    """Groq provider via its OpenAI-compatible endpoint."""

    name = "groq"
    model = "openai/gpt-oss-20b"

    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.3,
    ) -> str:
        if not self.has_key():
            raise AuthError("Groq API key is not configured (set GROQ_API_KEY)")
        body = {
            "model": self.model,
            "messages": [self._to_openai_message(m) for m in messages],
            "temperature": float(temperature),
        }
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters or {"type": "object", "properties": {}},
                    },
                }
                for t in tools
            ]
        try:
            response = requests.post(
                _GROQ_URL,
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise ProviderError(f"Groq request failed: {exc}") from exc
        if response.status_code != 200:
            raise_for_status_code(response.status_code, response.text, "Groq")
        try:
            data = response.json()
            return data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"Groq reply was not usable: {response.text[:300]!r}") from exc

    @staticmethod
    def _to_openai_message(msg: ChatMessage) -> dict:
        role = (msg.role or "user").lower()
        if role not in ("system", "user", "assistant", "tool"):
            role = "user"
        return {"role": role, "content": msg.content}
