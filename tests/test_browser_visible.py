"""Regression tests for the 2026-11-15 Chrome/search split bug.

User report (Roman Urdu): "chrome opened but kuch search nhi kara" —
Chrome opened, but no search happened (visibly).

Cause: open_app launched Chrome with subprocess, while search_youtube
used a *separate* headless Playwright browser. The search ran invisibly;
the user only saw the empty Chrome window.

Fix: BrowserAgent._ensure() launches headed, and open_app for Chrome
prefers the shared Playwright browser, so search reuses the same
visible window.
"""

from unittest.mock import MagicMock, patch

from tools import applications
from tools.browser import BrowserAgent


def test_ensure_launches_headed_not_headless():
    agent = BrowserAgent()
    with patch.object(BrowserAgent, "launch",
                      return_value={"success": True, "result": {"launched": True}}) as mock_launch:
        assert agent._ensure() is None
        mock_launch.assert_called_once()
        assert mock_launch.call_args.kwargs.get("headless") is False


def test_open_chrome_prefers_playwright_headed():
    fake_agent = MagicMock()
    fake_agent.is_launched = False
    fake_agent.launch.return_value = {"success": True, "result": {"launched": True, "headless": False}}
    with patch("tools.browser.get_browser_agent", return_value=fake_agent):
        result = applications.launch_app("chrome")
    assert result["success"] is True
    assert result["result"].get("via") == "playwright"
    fake_agent.launch.assert_called_once_with(headless=False, use_chrome=True)


def test_open_chrome_falls_back_when_playwright_fails():
    # Playwright unavailable / launch fails -> subprocess path, not a crash.
    # On Linux with no Chrome installed this fails as "Windows-only app",
    # which is the pre-existing graceful degradation — the point is it
    # does not raise and does not claim a dict-named app.
    fake_agent = MagicMock()
    fake_agent.is_launched = False
    fake_agent.launch.return_value = {"success": False, "error": "no browser"}
    with patch("tools.browser.get_browser_agent", return_value=fake_agent):
        result = applications.launch_app("chrome")
    assert isinstance(result, dict)
    assert "success" in result
