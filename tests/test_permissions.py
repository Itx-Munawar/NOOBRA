"""Tests for core.permissions classification."""

import pytest

pytest.importorskip("core.permissions", reason="core.permissions not implemented yet")

from core.permissions import PermissionLevel, classify_tool, requires_approval  # noqa: E402


def _level(result):
    """Normalise classify_tool's return to a PermissionLevel / str."""
    if isinstance(result, PermissionLevel):
        return result
    # Tuple / object forms: take the first level-like element.
    if isinstance(result, (tuple, list)) and result:
        return _level(result[0])
    level = getattr(result, "level", None)
    if level is not None:
        return _level(level)
    return result


def test_open_app_is_safe():
    assert _level(classify_tool("open_app")) == PermissionLevel.SAFE


def test_move_file_is_caution():
    assert _level(classify_tool("move_file")) == PermissionLevel.CAUTION


def test_delete_file_is_dangerous():
    assert _level(classify_tool("delete_file")) == PermissionLevel.DANGEROUS


def test_requires_approval():
    assert requires_approval(PermissionLevel.SAFE) is False
    assert requires_approval(PermissionLevel.CAUTION) is True
    assert requires_approval(PermissionLevel.DANGEROUS) is True
