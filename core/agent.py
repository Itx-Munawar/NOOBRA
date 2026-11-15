"""NOOBRA agent: the top-level orchestration for one instruction.

Flow: record the instruction in the conversation context -> plan it
(LLM, falling back to offline rules) -> execute it step by step with
permission checks -> report the outcome in the user's own language
(English, Roman Urdu, or a mix, matching what they used).

No Windows-only imports here; tools and memory are loaded lazily so a
missing optional workstream can never break import.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger("noobra.core.agent")


class NoobraAgent:
    """A personal AI desktop agent for one user session."""

    def __init__(self, settings=None, provider_chain=None, tool_registry=None, memory=None):
        self.settings = settings
        if self.settings is None:
            try:
                from core.config import get_settings
            except ImportError:
                from .config import get_settings
            self.settings = get_settings()
        self.memory = memory  # optional; used by callers, loaded lazily if needed
        self._cancel_event = threading.Event()
        self._running = False

        # Conversation context (lazy import keeps the module import-safe).
        try:
            from core.context import ConversationContext
        except ImportError:
            from .context import ConversationContext
        self.context = ConversationContext()

        # Provider chain: explicit, else the configured fallback chain.
        if provider_chain is not None:
            self.provider_chain = list(provider_chain)
        else:
            try:
                try:
                    from ai import get_provider_chain
                except ImportError:
                    from ..ai import get_provider_chain
                self.provider_chain = get_provider_chain(self.settings)
            except Exception as exc:
                logger.warning("Could not build provider chain: %s", exc)
                self.provider_chain = []

        # Planner and executor (lazy imports avoid import cycles).
        try:
            from core.planner import Planner
        except ImportError:
            from .planner import Planner
        try:
            from core.executor import Executor
        except ImportError:
            from .executor import Executor
        self.planner = Planner(provider_chain=self.provider_chain)
        self.executor = Executor(tool_registry=tool_registry)

    # -- main entry points ------------------------------------------------
    def handle_instruction(self, text: str) -> str:
        """Handle one user instruction and return a human reply."""
        text = (text or "").strip()
        roman = self._is_roman_urdu(text)
        if not text:
            reply = (
                "Batao, main aap ke liye kya karoon?"
                if roman else "Please tell me what you'd like me to do."
            )
            return reply

        self._cancel_event.clear()
        self._running = True
        try:
            self.context.add_user(text)
            try:
                plan = self.planner.plan(text, context=self.context)
            except Exception as exc:
                logger.exception("Planning failed: %s", exc)
                reply = self._failure_reply(
                    roman, "planning your request", str(exc), succeeded=[], failed=["planning"]
                )
                self.context.add_assistant(reply)
                return reply

            if getattr(plan, "clarification_needed", False):
                question = getattr(plan, "clarification_question", None) or (
                    "Could you give me a bit more detail?"
                    if not roman else "Thora aur detail batao?"
                )
                self.context.add_assistant(question)
                return question

            steps = list(getattr(plan, "steps", None) or [])
            if not steps:
                reply = (
                    "Sorry, main samjha nahi — aap kya karwana chahte hain?"
                    if roman else "Sorry, I didn't understand that — what would you like me to do?"
                )
                self.context.add_assistant(reply)
                return reply

            try:
                outcome = self.executor.execute(
                    plan, context=self.context, cancel_event=self._cancel_event
                )
            except Exception as exc:
                logger.exception("Execution failed: %s", exc)
                reply = self._failure_reply(roman, "running your request", str(exc),
                                            succeeded=[], failed=[s.tool for s in steps])
                self.context.add_assistant(reply)
                return reply

            reply = self._format_outcome(outcome, roman)
            self.context.add_assistant(reply)
            return reply
        finally:
            self._running = False

    def handle_text(self, text: str) -> str:
        """Alias for :meth:`handle_instruction`."""
        return self.handle_instruction(text)

    # -- lifecycle ----------------------------------------------------------
    def stop(self) -> None:
        """Request cancellation of the currently running instruction."""
        self._cancel_event.set()
        self._running = False

    @property
    def status(self) -> dict:
        """Return a small status snapshot for the UI / caller."""
        provider_name = None
        if self.provider_chain:
            provider_name = getattr(self.provider_chain[0], "name", None)
        return {
            "running": self._running,
            "cancelled": self._cancel_event.is_set(),
            "provider": provider_name or getattr(self.settings, "provider", "gemini"),
            "providers_available": [
                getattr(p, "name", "?") for p in self.provider_chain
            ],
            "history_count": len(self.context.history()),
            "last_path": self.context.last_path,
        }

    # -- language + replies -------------------------------------------------
    @staticmethod
    def _is_roman_urdu(text: str) -> bool:
        try:
            try:
                from core.planner import detect_roman_urdu
            except ImportError:
                from .planner import detect_roman_urdu
            return detect_roman_urdu(text)
        except Exception:
            return False

    def _format_outcome(self, outcome: dict, roman: bool) -> str:
        results = outcome.get("results") or []
        succeeded = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        def describe(result):
            step = result.get("step")
            return getattr(step, "description", None) or getattr(step, "tool", "step")

        if outcome.get("success"):
            if roman:
                lines = ["Ho gaya! ✅"]
                for result in succeeded:
                    lines.append(f"• {describe(result)}")
                return "\n".join(lines)
            lines = ["Done! ✅"]
            for result in succeeded:
                lines.append(f"• {describe(result)}")
            return "\n".join(lines)

        # Partial or total failure: say what worked and what did not.
        if roman:
            lines = []
            if succeeded:
                lines.append("Kuch kaam ho gaya:")
                for result in succeeded:
                    lines.append(f"• {describe(result)}")
            lines.append("Ye nahi ho saka:")
            for result in failed:
                error = result.get("error") or "unknown error"
                lines.append(f"• {describe(result)} — {error}")
            lines.append("Dobara try karna chahte hain, ya kuch aur batao?")
            return "\n".join(lines)
        lines = []
        if succeeded:
            lines.append("Some steps completed:")
            for result in succeeded:
                lines.append(f"• {describe(result)}")
        lines.append("This did not work:")
        for result in failed:
            error = result.get("error") or "unknown error"
            lines.append(f"• {describe(result)} — {error}")
        lines.append("Want to try again, or tell me something else?")
        return "\n".join(lines)

    @staticmethod
    def _failure_reply(roman, stage, error, succeeded, failed) -> str:
        if roman:
            return (
                f"Sorry, {stage} mein masla aa gaya: {error}. "
                "Dobara try karein ya instruction thora saaf likh dein."
            )
        return (
            f"Sorry, something went wrong while {stage}: {error}. "
            "Please try again or rephrase the instruction."
        )
