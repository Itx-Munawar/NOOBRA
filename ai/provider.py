"""Provider-independent LLM interface for NOOBRA.

Every provider (Gemini / Groq / OpenRouter) implements :class:`BaseProvider`
over plain HTTPS via :mod:`requests` (``timeout=30``). No provider SDK is
required, and no API key is ever hardcoded -- keys come from
:class:`~core.config.Settings` (environment variables).
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger("noobra.ai.provider")

REQUEST_TIMEOUT = 30


class ProviderError(Exception):
    """Base error for any LLM provider failure."""


class RateLimitError(ProviderError):
    """The provider rate-limited the request (HTTP 429). Retry / fall back."""


class AuthError(ProviderError):
    """Authentication failed (HTTP 401/403) -- the API key is bad/missing."""


@dataclass
class ChatMessage:
    """One message in a chat conversation."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str


@dataclass
class ToolDefinition:
    """A tool an LLM may ask the planner/agent to call (JSON Schema)."""

    name: str
    description: str
    parameters: dict = field(default_factory=dict)


class BaseProvider(ABC):
    """Abstract base class for all LLM providers."""

    name: str = "base"
    model: str = ""

    def __init__(self, settings=None, api_key: str = "", model: str = ""):
        self.settings = settings
        self.api_key = api_key or (settings.api_key_for(self.name) if settings else "")
        self.model = model or (settings.model_for(self.name) if settings else "") or self.model

    def has_key(self) -> bool:
        """Return True when an API key is configured for this provider."""
        return bool(self.api_key and self.api_key.strip())

    @abstractmethod
    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.3,
    ) -> str:
        """Send ``messages`` to the model and return the reply text."""
        raise NotImplementedError

    # -- shared helpers -------------------------------------------------

    def chat_json(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.3,
    ) -> dict:
        """Call :meth:`chat` and parse the reply as a JSON object.

        Strips Markdown code fences (`````json ... `````) and extracts the
        first ``{...}`` object when the model adds surrounding prose.
        Raises :class:`ProviderError` when no JSON object can be parsed.
        """
        raw = self.chat(messages, tools=tools, temperature=temperature)
        return parse_json_response(raw)

    @staticmethod
    def _require_key() -> None:
        raise NotImplementedError


def parse_json_response(raw: str) -> dict:
    """Parse a JSON object out of raw LLM text (fences / prose tolerated)."""
    if not raw or not raw.strip():
        raise ProviderError("Empty response from provider; expected JSON")
    text = raw.strip()
    # Strip a surrounding Markdown code fence, optionally ```json.
    fence = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        parsed = json.loads(text)
    except ValueError:
        # Fall back to the first {...} block in the text.
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ProviderError(f"Could not parse JSON from provider reply: {raw[:300]!r}")
        try:
            parsed = json.loads(text[start : end + 1])
        except ValueError as exc:
            raise ProviderError(f"Could not parse JSON from provider reply: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ProviderError(f"Provider reply was JSON but not an object: {parsed!r}")
    return parsed


def raise_for_status_code(status: int, body: str, provider_name: str) -> None:
    """Map an HTTP error status to the right provider exception."""
    if status == 429:
        raise RateLimitError(f"{provider_name} rate limit (HTTP 429): {body[:300]}")
    if status in (401, 403):
        raise AuthError(f"{provider_name} authentication failed (HTTP {status}): {body[:300]}")
    raise ProviderError(f"{provider_name} request failed (HTTP {status}): {body[:300]}")
