"""Regression tests for the 2026-11-15 open_app bug.

An LLM plan returned ``open_app`` with ``{"app_name": "chrome"}``.
The executor's old fallback called ``open_app({"app_name": "chrome"})``
positionally, so the app name became a dict and launch failed with
``unknown app: {'app_name': 'chrome'}`` even though 'chrome' is known.
These tests pin the fix at three layers: the app tools accept the
alias, the executor normalises it, and the planner normalises LLM args.
"""

from core.executor import Executor
from core.planner import Planner
from tools import applications


def test_open_app_accepts_app_name_kwarg():
    result = applications.open_app(app_name="nonexistent-app-xyz")
    assert result["success"] is False
    # Must fail as an unknown *string* name, never as a dict.
    assert "{'app_name'" not in result["error"]
    assert "nonexistent-app-xyz" in result["error"]


def test_launch_app_unwraps_dict_name():
    result = applications.launch_app({"app_name": "nonexistent-app-xyz"})
    assert result["success"] is False
    assert "{'app_name'" not in result["error"]
    assert "nonexistent-app-xyz" in result["error"]


def test_open_app_accepts_google_chrome_name():
    # Friendly name must map to the canonical 'chrome' key.
    assert applications._norm("Google Chrome") == "chrome"
    assert applications._norm("vs code") == "vscode"


def test_executor_normalises_app_name_args():
    calls = {}

    def fake_open_app(name=None, **kwargs):
        calls["name"] = name
        return {"success": True, "result": "opened", "error": None, "verified": True}

    executor = Executor(tool_registry={"open_app": fake_open_app})
    plan = Planner._plan_from_llm_data(
        {"steps": [{"tool": "open_app", "args": {"app_name": "chrome"},
                    "description": "Open Chrome"}]},
        "Chrome kholo",
    )
    assert plan is not None
    assert plan.steps[0].args == {"name": "chrome"}
    outcome = executor.execute(plan)
    assert outcome["success"] is True
    assert calls["name"] == "chrome"


def test_executor_does_not_pass_dict_as_positional_arg():
    # Directly exercise _normalize_args + _call_tool with a dict-valued arg.
    executor = Executor(tool_registry={})
    args = executor._normalize_args("open_app", {"name": {"app_name": "chrome"}})
    assert args == {"name": "chrome"}
