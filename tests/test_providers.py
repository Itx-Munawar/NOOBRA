"""Tests for ai providers (mocked HTTP, no real keys).

Interface note (verified against the shipped workstream):
``get_provider`` / ``get_provider_chain`` live in the ``ai`` package
(``ai/__init__.py``), while ``BaseProvider`` / ``ProviderError`` /
``RateLimitError`` / ``ChatMessage`` / ``ToolDefinition`` live in
``ai.provider``. The task brief said "ai.provider: ... ai.get_provider"
— the functions are in the ``ai`` package, not the submodule.
"""

import pytest

pytest.importorskip("ai.provider", reason="ai.provider not implemented yet")
pytest.importorskip("ai", reason="ai package not implemented yet")

from ai import get_provider, get_provider_chain  # noqa: E402
from ai.provider import ChatMessage, ProviderError, RateLimitError  # noqa: E402


def _make_settings(monkeypatch, provider="gemini", gemini=None, groq=None, openrouter=None):
    """Build a Settings object directly (avoids the cached get_settings)."""
    from core.config import Settings

    return Settings(
        provider=provider,
        gemini_api_key=gemini or "",
        groq_api_key=groq or "",
        openrouter_api_key=openrouter or "",
    )


def _call(provider, text="Hello"):
    messages = [ChatMessage(role="user", content=text)]
    return provider.chat(messages)


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(payload)

    def json(self):
        return self._payload


def _gemini_ok_payload():
    return {"candidates": [{"content": {"parts": [{"text": "hello from Gemini"}]}}]}


def test_gemini_success(monkeypatch):
    settings = _make_settings(monkeypatch, gemini="test-key")
    provider = get_provider("gemini", settings)
    monkeypatch.setattr(
        "requests.post",
        lambda url, *a, **k: _FakeResponse(200, _gemini_ok_payload()),
    )
    reply = _call(provider)
    assert "hello from gemini" in str(reply).lower()


def test_rate_limit_error_on_429(monkeypatch):
    settings = _make_settings(monkeypatch, gemini="test-key")
    provider = get_provider("gemini", settings)
    monkeypatch.setattr(
        "requests.post", lambda *a, **k: _FakeResponse(429, {"error": {"message": "quota"}}))
    with pytest.raises(RateLimitError):
        _call(provider)


def test_chain_skips_providers_without_keys(monkeypatch):
    settings = _make_settings(monkeypatch, gemini=None, groq=None, openrouter=None)
    assert list(get_provider_chain(settings)) == []


def test_chain_includes_only_keyed_providers(monkeypatch):
    settings = _make_settings(monkeypatch, gemini="g-key", groq=None, openrouter=None)
    chain = list(get_provider_chain(settings))
    assert len(chain) == 1
    assert chain[0].name == "gemini"


def test_chain_falls_back_after_rate_limit(monkeypatch):
    """A 429 from Gemini surfaces as RateLimitError so the caller/chain
    can fall back to the next provider (Groq), which then succeeds."""
    settings = _make_settings(monkeypatch, gemini="g-key", groq="groq-key")
    chain = list(get_provider_chain(settings))
    assert [p.name for p in chain] == ["gemini", "groq"]

    def fake_post(url, *args, **kwargs):
        if "generativelanguage" in str(url):
            return _FakeResponse(429, {"error": {"message": "quota"}})
        return _FakeResponse(200, {"choices": [{"message": {"content": "groq reply"}}]})

    monkeypatch.setattr("requests.post", fake_post)
    with pytest.raises(RateLimitError):
        _call(chain[0])
    assert _call(chain[1]) == "groq reply"
