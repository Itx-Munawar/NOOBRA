#!/usr/bin/env python3
"""NOOBRA — Personal AI Desktop Agent (Windows 11).

Entry point. Launches the PySide6 GUI when available (and a display
is present, and ``--cli`` / ``--no-gui`` was not given); otherwise
falls back to a CLI REPL loop. No API keys are required to start —
the planner has a rule-based fallback and the agent reports clearly
when a provider key is missing.

Usage:
    python main.py                  # GUI if possible, else CLI
    python main.py --cli            # force CLI REPL
    python main.py --no-gui         # same as --cli
    python main.py --text "Chrome kholo"
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Make the project root importable (core / ai / tools / ... live here).
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("noobra")


def _load_env() -> None:
    """Load .env if python-dotenv is installed; never crash if not."""
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(ROOT / ".env")
    except Exception as exc:
        logger.debug(".env loading skipped: %s", exc)


def _make_agent():
    """Create NoobraAgent, or return None (with a log) if core is absent."""
    try:
        from core.agent import NoobraAgent  # type: ignore

        return NoobraAgent()
    except Exception as exc:
        logger.warning("NoobraAgent unavailable (%s); running in limited mode", exc)
        return None


def _run_cli(agent, text: str | None = None) -> int:
    """CLI REPL: read instructions, print replies. Returns exit code."""
    print("NOOBRA — Personal AI Agent (CLI mode)")
    print("Type 'exit' or 'quit' to leave. Roman Urdu ya English, dono chalte hain.")
    if agent is None:
        print("Note: core agent is not available yet — replies will be limited.")
    if text:
        print(f"> {text}")
        print(_handle(agent, text))
        return 0
    while True:
        try:
            line = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nKhuda Hafiz! 👋")
            return 0
        if not line:
            continue
        if line.lower() in ("exit", "quit", "bye", "khuda hafiz"):
            print("Khuda Hafiz! 👋")
            return 0
        print("NOOBRA:", _handle(agent, line))


def _handle(agent, text: str) -> str:
    if agent is None:
        return ("Agent core is not installed yet. I understood your request "
                f"({text!r}) but cannot execute it without core.agent.")
    try:
        return str(agent.handle_instruction(text))
    except Exception as exc:
        logger.exception("handle_instruction failed")
        return f"Sorry, something went wrong: {exc}"


def _display_present() -> bool:
    """Windows always has a display; on Linux require $DISPLAY / Wayland."""
    if os.name == "nt":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _run_gui(agent) -> int:
    """Launch the Qt GUI. Raises ImportError/RuntimeError if unavailable."""
    from PySide6.QtWidgets import QApplication  # noqa: PLC0415

    from ui.main_window import MainWindow  # noqa: PLC0415

    app = QApplication(sys.argv)
    window = MainWindow(agent=agent)
    window.show()
    return app.exec()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="NOOBRA — Personal AI Agent")
    parser.add_argument("--cli", action="store_true", help="Force CLI mode")
    parser.add_argument("--no-gui", action="store_true", help="Force CLI mode")
    parser.add_argument("--text", help="Run one instruction and exit")
    args = parser.parse_args(argv)

    _load_env()
    agent = _make_agent()

    if args.text:
        print(_handle(agent, args.text))
        return 0
    if args.cli or args.no_gui:
        return _run_cli(agent)

    if not _display_present():
        logger.info("No display detected — falling back to CLI mode")
        return _run_cli(agent)
    try:
        return _run_gui(agent)
    except ImportError as exc:
        logger.warning("PySide6 unavailable (%s) — falling back to CLI mode", exc)
        return _run_cli(agent)
    except Exception as exc:
        logger.warning("GUI failed to start (%s) — falling back to CLI mode", exc)
        return _run_cli(agent)


if __name__ == "__main__":
    sys.exit(main())
