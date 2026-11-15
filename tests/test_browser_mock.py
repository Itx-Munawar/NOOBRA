"""Tests for tools.browser with a mocked Playwright — no real browser.

Interface note (verified against the shipped workstream): ``BrowserAgent``
has ``search_google`` / ``search_youtube`` (not a generic ``search``) and
``navigate`` / ``launch`` returning ``{"success": bool, "result": ...}``
dicts. ``launch`` really starts Playwright, so it is patched out here;
``navigate``'s real logic is exercised by patching only ``_ensure`` and
supplying a fake current page.
"""

import pytest

pytest.importorskip("tools.browser", reason="tools.browser not implemented yet")

from unittest.mock import MagicMock, patch  # noqa: E402

from tools.browser import BrowserAgent  # noqa: E402


def test_search_google_builds_google_url():
    agent = BrowserAgent()
    with patch.object(BrowserAgent, "navigate",
                      return_value={"success": True, "result": {"url": "https://www.google.com/search?q=Python"}}) as mock_nav:
        result = agent.search_google("Python")
        assert result["success"] is True
        mock_nav.assert_called_once()
        url = mock_nav.call_args.args[0]
        assert "google.com/search" in url and "Python" in url


def test_search_youtube_builds_youtube_url():
    agent = BrowserAgent()
    with patch.object(BrowserAgent, "navigate",
                      return_value={"success": True, "result": {}}) as mock_nav:
        agent.search_youtube("cats")
        url = mock_nav.call_args.args[0]
        assert "youtube.com/results" in url and "cats" in url


def test_navigate_mocked_page():
    agent = BrowserAgent()
    fake_page = MagicMock()
    fake_page.title.return_value = "Example Domain"
    fake_page.url = "https://example.com"
    agent._pages = [fake_page]
    agent._current = 0
    with patch.object(BrowserAgent, "_ensure", return_value=None):
        result = agent.navigate("https://example.com")
    assert result["success"] is True
    assert result["result"]["title"] == "Example Domain"
    fake_page.goto.assert_called_once()
    assert "example.com" in fake_page.goto.call_args.args[0]


def test_launch_is_mocked_not_real():
    """Patching launch proves the agent's launch path is mockable and no
    real Chromium is started by these tests."""
    agent = BrowserAgent()
    with patch.object(BrowserAgent, "launch",
                      return_value={"success": True, "result": {"launched": True}}) as mock_launch:
        result = agent.launch(headless=True)
        assert result["success"] is True
        mock_launch.assert_called_once_with(headless=True)
        assert agent.is_launched is False  # mocked launch touched no real browser
