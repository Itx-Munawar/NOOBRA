"""NOOBRA AI package: provider-independent LLM access.

Providers (all free-tier friendly, keyed by environment variables only):
Gemini (primary), Groq (secondary), OpenRouter (optional). The chain
falls back to the next provider on error / rate limit.
"""

import logging

from .provider import AuthError, BaseProvider, ChatMessage, ProviderError, RateLimitError, ToolDefinition

logger = logging.getLogger("noobra.ai")

__all__ = [
    "AuthError",
    "BaseProvider",
    "ChatMessage",
    "ProviderError",
    "RateLimitError",
    "ToolDefinition",
    "get_provider",
    "get_provider_chain",
    "list_available_providers",
]


def get_provider(name=None, settings=None):
    """Return a provider instance by name (``gemini``/``groq``/``openrouter``).

    ``name`` defaults to ``settings.provider`` (or ``"gemini"``). Raises
    :class:`ProviderError` for an unknown name and :class:`AuthError`
    when the provider has no API key configured.
    """
    if settings is None:
        try:
            from core.config import get_settings  # NOOBRA/ on sys.path
        except ImportError:  # pragma: no cover - imported as NOOBRA.ai
            from ..core.config import get_settings

        settings = get_settings()
    wanted = (name or getattr(settings, "provider", None) or "gemini").strip().lower()
    if wanted == "gemini":
        from .gemini import GeminiProvider

        return GeminiProvider(settings=settings)
    if wanted == "groq":
        from .groq import GroqProvider

        return GroqProvider(settings=settings)
    if wanted == "openrouter":
        from .openrouter import OpenRouterProvider

        return OpenRouterProvider(settings=settings)
    raise ProviderError(f"Unknown provider: {wanted!r} (expected gemini, groq or openrouter)")


def get_provider_chain(settings=None):
    """Return providers in fallback order: primary, then Groq, then OpenRouter.

    Only providers that actually have an API key are included. The order
    follows ``settings.fallback_providers`` when set, with the primary
    provider first; duplicates are removed. Returns an empty list when no
    provider has a key (callers must then use the offline rule-based path).
    """
    if settings is None:
        try:
            from core.config import get_settings
        except ImportError:  # pragma: no cover - imported as NOOBRA.ai
            from ..core.config import get_settings

        settings = get_settings()
    ordered = []
    primary = (getattr(settings, "provider", None) or "gemini").strip().lower()
    fallbacks = list(getattr(settings, "fallback_providers", None) or [])
    for candidate in [primary] + fallbacks + ["groq", "openrouter"]:
        name = str(candidate).strip().lower()
        if name and name not in ordered:
            ordered.append(name)
    chain = []
    for name in ordered:
        try:
            provider = get_provider(name, settings=settings)
        except (ProviderError, AuthError) as exc:
            logger.debug("Provider %s unavailable: %s", name, exc)
            continue
        if provider.has_key():
            chain.append(provider)
        else:
            logger.debug("Provider %s has no API key configured; skipping", name)
    return chain


def list_available_providers(settings=None):
    """Return the names of providers that have an API key configured."""
    return [provider.name for provider in get_provider_chain(settings)]
