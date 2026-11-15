"""Browser automation tools for NOOBRA (Playwright, guarded import).

``playwright`` is optional: if it is not installed, every method returns
``{"success": False, "error": "Playwright not installed: pip install playwright
&& playwright install chromium"}`` and the module still imports cleanly.

:class:`BrowserAgent` wraps a Playwright Chromium/Chrome session with a
tab list. Module-level convenience functions (``browser_navigate`` etc.)
use a process-wide singleton agent and are what the tool registry exposes.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from pathlib import Path

logger = logging.getLogger("noobra.tools")

try:
    from playwright.sync_api import sync_playwright  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    sync_playwright = None

__all__ = [
    "BrowserAgent",
    "get_browser_agent",
    "browser_navigate",
    "browser_search",
    "browser_read",
    "browser_click",
    "browser_fill",
    "browser_new_tab",
    "browser_close_tab",
    "browser_back",
    "browser_forward",
]

_PLAYWRIGHT_MISSING = (
    "Playwright not installed: pip install playwright "
    "&& playwright install chromium"
)


def _ok(result=None, verified=False):
    return {"success": True, "result": result, "error": None, "verified": verified}


def _fail(error, result=None):
    return {"success": False, "result": result, "error": str(error), "verified": False}


def _normalise_url(url: str) -> str:
    url = str(url).strip()
    if not url:
        raise ValueError("url is required")
    if "://" not in url:
        url = "https://" + url
    return url


class BrowserAgent:
    """A Playwright-driven browser with tab management."""

    def __init__(self):
        self._pw = None
        self._browser = None
        self._context = None
        self._pages: list = []
        self._current = -1
        self.headless = True

    # -- lifecycle ---------------------------------------------------------
    @property
    def is_launched(self) -> bool:
        return self._browser is not None

    @property
    def current_page(self):
        if self._pages and 0 <= self._current < len(self._pages):
            return self._pages[self._current]
        return None

    def launch(self, headless=False, use_chrome=True):
        """Launch the browser.

        Tries Chrome (``channel="chrome"``) first when ``use_chrome`` is set,
        falling back to bundled Chromium. On a headless Linux box a headed
        launch fails, so it retries headless automatically.
        """
        if sync_playwright is None:
            return _fail(_PLAYWRIGHT_MISSING)
        if self.is_launched:
            return _ok({"launched": True, "already": True}, verified=True)
        try:
            self._pw = sync_playwright().start()
            launched = None
            last_error = None
            used_headless = bool(headless)
            for want_headless in ([headless, True] if not headless else [True]):
                try:
                    if use_chrome:
                        try:
                            launched = self._pw.chromium.launch(
                                channel="chrome", headless=want_headless)
                            used_headless = want_headless
                            break
                        except Exception as exc:  # Chrome not installed
                            last_error = exc
                            logger.debug("channel=chrome launch failed: %s", exc)
                    launched = self._pw.chromium.launch(headless=want_headless)
                    used_headless = want_headless
                    break
                except Exception as exc:
                    last_error = exc
                    logger.debug("chromium launch (headless=%s) failed: %s",
                                 want_headless, exc)
            if launched is None:
                raise RuntimeError(f"could not launch browser: {last_error}")
            self._browser = launched
            self.headless = used_headless
            self._context = self._browser.new_context()
            page = self._context.new_page()
            self._pages = [page]
            self._current = 0
        except Exception as exc:
            logger.exception("BrowserAgent.launch failed")
            self.close()
            return _fail(exc)
        return _ok({"launched": True, "headless": self.headless,
                    "tabs": len(self._pages)}, verified=True)

    def _ensure(self):
        """Auto-launch (headless, for background use) if needed."""
        if self.is_launched:
            return None
        res = self.launch(headless=True, use_chrome=True)
        return None if res["success"] else res

    # -- navigation --------------------------------------------------------
    def navigate(self, url):
        """Navigate the current tab to ``url``; returns ``{"title", "url"}``."""
        err = self._ensure()
        if err:
            return err
        try:
            target = _normalise_url(url)
            self.current_page.goto(target, wait_until="domcontentloaded",
                                   timeout=30000)
            self.current_page.wait_for_timeout(500)
        except Exception as exc:
            logger.exception("navigate failed for %s", url)
            return _fail(exc)
        return _ok({"title": self.current_page.title(), "url": self.current_page.url},
                   verified=True)

    def new_tab(self, url=None):
        """Open a new tab (optionally navigating to ``url``) and switch to it."""
        err = self._ensure()
        if err:
            return err
        try:
            page = self._context.new_page()
            self._pages.append(page)
            self._current = len(self._pages) - 1
            if url:
                page.goto(_normalise_url(url), wait_until="domcontentloaded",
                          timeout=30000)
        except Exception as exc:
            logger.exception("new_tab failed")
            return _fail(exc)
        return _ok({"index": self._current, "title": page.title(),
                    "url": page.url, "tabs": len(self._pages)}, verified=True)

    def close_tab(self, index=-1):
        """Close tab ``index`` (default: current). At least one tab stays open."""
        if sync_playwright is None:
            return _fail(_PLAYWRIGHT_MISSING)
        if not self._pages:
            return _fail("no tabs open")
        try:
            idx = int(index)
        except (TypeError, ValueError):
            return _fail(f"invalid tab index: {index!r}")
        if idx < 0:
            idx = len(self._pages) + idx
        if not 0 <= idx < len(self._pages):
            return _fail(f"tab index out of range: {index}")
        try:
            if len(self._pages) == 1:
                # Keep one tab: navigate it home instead of closing the last.
                self._pages[0].goto("about:blank")
                return _ok({"closed": idx, "tabs": 1, "note": "kept last tab open"},
                           verified=True)
            self._pages[idx].close()
            del self._pages[idx]
            self._current = min(self._current, len(self._pages) - 1)
        except Exception as exc:
            logger.exception("close_tab failed")
            return _fail(exc)
        return _ok({"closed": idx, "tabs": len(self._pages)}, verified=True)

    def switch_tab(self, index):
        """Switch the current tab to ``index``."""
        if sync_playwright is None:
            return _fail(_PLAYWRIGHT_MISSING)
        try:
            idx = int(index)
        except (TypeError, ValueError):
            return _fail(f"invalid tab index: {index!r}")
        if not 0 <= idx < len(self._pages):
            return _fail(f"tab index out of range: {index}")
        try:
            self._current = idx
            self._pages[idx].bring_to_front()
        except Exception as exc:
            logger.exception("switch_tab failed")
            return _fail(exc)
        return _ok({"index": idx, "title": self._pages[idx].title(),
                    "url": self._pages[idx].url}, verified=True)

    def get_tabs(self):
        """Return a list of ``{"index", "title", "url", "active"}``."""
        if sync_playwright is None or not self._pages:
            return []
        tabs = []
        for i, page in enumerate(self._pages):
            try:
                tabs.append({"index": i, "title": page.title(),
                             "url": page.url, "active": i == self._current})
            except Exception:
                tabs.append({"index": i, "title": "", "url": "", "active": i == self._current})
        return tabs

    # -- search ------------------------------------------------------------
    def search_google(self, query):
        """Search Google for ``query`` in the current tab."""
        if not query:
            return _fail("query is required")
        url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(str(query))
        return self.navigate(url)

    def search_youtube(self, query):
        """Search YouTube for ``query`` in the current tab."""
        if not query:
            return _fail("query is required")
        url = ("https://www.youtube.com/results?search_query="
               + urllib.parse.quote_plus(str(query)))
        return self.navigate(url)

    # -- reading / interaction ----------------------------------------------
    def read_content(self):
        """Return ``{"title", "url", "text"}`` (text truncated to 8000 chars)."""
        err = self._ensure()
        if err:
            return err
        try:
            page = self.current_page
            text = page.locator("body").inner_text(timeout=5000)
        except Exception as exc:
            logger.exception("read_content failed")
            return _fail(exc)
        return _ok({"title": page.title(), "url": page.url,
                    "text": text[:8000]}, verified=True)

    def click(self, selector, timeout=5000):
        """Click the element matching ``selector`` (CSS / Playwright locator)."""
        err = self._ensure()
        if err:
            return err
        try:
            self.current_page.locator(selector).first.click(timeout=int(timeout))
        except Exception as exc:
            logger.exception("click failed for %s", selector)
            return _fail(exc)
        return _ok({"selector": selector, "clicked": True}, verified=True)

    def fill(self, selector, value):
        """Fill the element matching ``selector`` with ``value``."""
        err = self._ensure()
        if err:
            return err
        try:
            self.current_page.locator(selector).first.fill(str(value), timeout=5000)
        except Exception as exc:
            logger.exception("fill failed for %s", selector)
            return _fail(exc)
        return _ok({"selector": selector, "filled": True}, verified=True)

    def download(self, url, save_dir):
        """Download ``url`` into ``save_dir``; returns ``{"path": ...}``."""
        err = self._ensure()
        if err:
            return err
        try:
            dest_dir = Path(os.path.expanduser(str(save_dir)))
            dest_dir.mkdir(parents=True, exist_ok=True)
            with self.current_page.expect_download(timeout=30000) as dl_info:
                self.current_page.goto(_normalise_url(url),
                                       wait_until="domcontentloaded", timeout=30000)
            download = dl_info.value
            path = dest_dir / (download.suggested_filename or "download")
            download.save_as(str(path))
        except Exception as exc:
            logger.exception("download failed for %s", url)
            return _fail(exc)
        return _ok({"path": str(path), "url": str(url)}, verified=path.is_file())

    def back(self):
        """Go back in the current tab's history."""
        err = self._ensure()
        if err:
            return err
        try:
            self.current_page.go_back(wait_until="domcontentloaded", timeout=15000)
        except Exception as exc:
            return _fail(exc)
        return _ok({"url": self.current_page.url}, verified=True)

    def forward(self):
        """Go forward in the current tab's history."""
        err = self._ensure()
        if err:
            return err
        try:
            self.current_page.go_forward(wait_until="domcontentloaded", timeout=15000)
        except Exception as exc:
            return _fail(exc)
        return _ok({"url": self.current_page.url}, verified=True)

    def close(self):
        """Close the browser and release Playwright."""
        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._pages, self._current = [], -1
        self._browser = self._context = self._pw = None
        return _ok({"closed": True}, verified=True)


# ---------------------------------------------------------------------------
# Singleton + module-level convenience functions (used by the tool registry)
# ---------------------------------------------------------------------------

_AGENT: BrowserAgent | None = None


def get_browser_agent() -> BrowserAgent:
    """Return the process-wide singleton :class:`BrowserAgent`."""
    global _AGENT
    if _AGENT is None:
        _AGENT = BrowserAgent()
    return _AGENT


def browser_navigate(url):
    return get_browser_agent().navigate(url)


def browser_search(query):
    """Search Google (the registry's ``browser_search`` tool)."""
    return get_browser_agent().search_google(query)


def search_google(query):
    """Search Google — alias used by the planner (same as browser_search)."""
    return get_browser_agent().search_google(query)


def search_youtube(query):
    """Search YouTube — alias used by the planner."""
    return get_browser_agent().search_youtube(query)


def browser_read():
    return get_browser_agent().read_content()


def browser_click(selector, timeout=5000):
    return get_browser_agent().click(selector, timeout=timeout)


def browser_fill(selector, value):
    return get_browser_agent().fill(selector, value)


def browser_new_tab(url=None):
    return get_browser_agent().new_tab(url)


def browser_close_tab(index=-1):
    return get_browser_agent().close_tab(index)


def browser_back():
    return get_browser_agent().back()


def browser_forward():
    return get_browser_agent().forward()
