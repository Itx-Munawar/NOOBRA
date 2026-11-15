"""Shared pytest fixtures for NOOBRA tests.

Ensures the project root (the folder containing ``main.py``) is on
``sys.path`` so ``core`` / ``ai`` / ``tools`` / ``memory`` imports work
regardless of where pytest is invoked from. Tests that need optional
modules use ``pytest.importorskip`` / guarded imports in each file,
so collection never fails on Linux when another workstream is absent.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
