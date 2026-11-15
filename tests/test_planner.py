"""Tests for core.planner — rule-based fallback, no API key needed.

Interface note (verified against the shipped workstream):
``Planner(provider_chain=[])`` forces the rule-based parser (passing
``provider=None`` would lazily build a chain from env). The web-search
tool is named ``search_google`` in the shipped planner, not
``browser_search`` as the brief suggested.
"""

import pytest

pytest.importorskip("core.planner", reason="core.planner not implemented yet")

from core.planner import Planner  # noqa: E402


def _planner():
    return Planner(provider_chain=[])


def _steps(plan):
    return list(getattr(plan, "steps", []) or [])


def _step_text(step):
    return f"{getattr(step, 'tool', '')} {getattr(step, 'args', {})}".lower()


def test_open_chrome():
    plan = _planner().plan("Chrome kholo", context={}, tool_schemas=[])
    steps = _steps(plan)
    assert steps, "planner should produce a step for 'Chrome kholo'"
    assert any(s.tool == "open_app" and "chrome" in str(s.args).lower() for s in steps)


def test_create_folder_on_desktop():
    plan = _planner().plan("Desktop par Test folder banao", context={}, tool_schemas=[])
    steps = _steps(plan)
    assert steps
    assert any(s.tool == "create_folder" for s in steps)
    assert "test" in " ".join(_step_text(s) for s in steps)


def test_browser_search():
    plan = _planner().plan("Google par Python search karo", context={}, tool_schemas=[])
    steps = _steps(plan)
    assert steps
    assert any(s.tool == "search_google" for s in steps)
    assert "python" in " ".join(_step_text(s) for s in steps)


def test_ambiguous_delete_needs_clarification():
    plan = _planner().plan("delete this folder", context={}, tool_schemas=[])
    assert plan.clarification_needed is True
    assert plan.clarification_question
