"""Integration regression tests (added by the coordinator).

The original per-module tests all passed while the end-to-end path was
broken: the planner emitted tool names / argument names the registry
did not have (search_google/search_youtube/navigate, open_app(app=...),
create_folder(name=...), search_files(query=..., path=...)). These tests
pin the planner -> executor -> registry contract so that cannot regress.
"""

import pytest

pytest.importorskip("core.planner", reason="core.planner not implemented")
pytest.importorskip("tools", reason="tools registry not implemented")

from core.agent import NoobraAgent  # noqa: E402
from core.context import ConversationContext  # noqa: E402
from core.executor import Executor  # noqa: E402
from core.planner import Planner  # noqa: E402
from tools import TOOL_SCHEMAS, get_tool_registry  # noqa: E402


def test_every_schema_has_a_registry_callable():
    registry = get_tool_registry()
    missing = [s["name"] for s in TOOL_SCHEMAS if s["name"] not in registry]
    assert not missing, f"schemas without registry entry: {missing}"
    assert set(registry) == {s["name"] for s in TOOL_SCHEMAS}


def test_planner_tools_all_exist_in_registry():
    registry = get_tool_registry()
    planner = Planner(provider_chain=[])
    ctx = ConversationContext()
    instructions = [
        "Chrome kholo",
        "Chrome kholo aur YouTube par Python tutorials search karo",
        "Google par Python search karo",
        "Desktop par Notes folder banao",
        "open youtube.com",
        "list files in Downloads",
        "organize downloads",
        "close notepad",
        "find file named notes",
    ]
    for text in instructions:
        plan = planner.plan(text, ctx, TOOL_SCHEMAS)
        assert not plan.clarification_needed, f"{text!r} unexpectedly needs clarification"
        for step in plan.steps:
            assert step.tool in registry, f"{text!r} -> unknown tool {step.tool!r}"


def test_executor_open_app_uses_name_not_dict():
    """open_app(chrome) must fail (on Linux) as 'not installed', never as
    'unknown app: {dict}' — the old planner passed {"app": ...} and the
    executor's TypeError fallback fed the whole dict as the app name."""
    planner = Planner(provider_chain=[])
    plan = planner.plan("Chrome kholo", ConversationContext(), TOOL_SCHEMAS)
    assert plan.steps[0].args == {"name": "chrome"}
    result = Executor().execute(plan)
    assert result["results"][0]["error"] is not None
    assert "unknown app: {'app'" not in result["results"][0]["error"]


def test_executor_search_tools_are_available():
    """search_google/search_youtube must reach the browser tool (and fail
    there with 'Playwright not installed' on this Linux box), never with
    'Tool ... is not available'."""
    planner = Planner(provider_chain=[])
    for text in ("Google par Python search karo", "YouTube par Python search karo"):
        plan = planner.plan(text, ConversationContext(), TOOL_SCHEMAS)
        result = Executor().execute(plan)
        err = result["results"][0]["error"] or ""
        assert "is not available" not in err, f"{text!r}: {err}"
        assert "Playwright" in err or "browser" in err.lower(), f"{text!r}: {err}"


def test_agent_end_to_end_offline(tmp_path, monkeypatch):
    """Agent handles a folder-creation instruction end to end, in a
    sandboxed home, and the folder really appears."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Planner / files resolve via Path.home(); patch both modules' Path.
    import core.planner as planner_mod
    import tools.files as files_mod

    monkeypatch.setattr(planner_mod.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(files_mod, "_home", lambda: tmp_path)
    agent = NoobraAgent()
    reply = agent.handle_instruction("Desktop par AgentTest folder banao")
    assert (tmp_path / "Desktop" / "AgentTest").is_dir(), reply
    assert "AgentTest" in reply
