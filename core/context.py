"""Conversation context for NOOBRA.

Keeps the running chat history, the most recent file/folder the user
mentioned or the agent touched (so follow-ups like "open it" / "us ko
delete karo" can be resolved), and a short human-readable summary.
"""

from __future__ import annotations

import logging
from pathlib import Path

try:
    from ai.provider import ChatMessage
except ImportError:  # pragma: no cover - imported as NOOBRA.core
    try:
        from ..ai.provider import ChatMessage
    except ImportError:  # pragma: no cover - ai not importable yet
        ChatMessage = None  # type: ignore[assignment]

logger = logging.getLogger("noobra.core.context")

MAX_HISTORY = 40


class ConversationContext:
    """In-memory conversation + working-path state for one session."""

    def __init__(self, max_history: int = MAX_HISTORY):
        self.max_history = max_history
        self._history: list[dict] = []  # {"role": str, "content": str, ...}
        self._last_path: str | None = None
        self._last_file: str | None = None
        self._last_folder: str | None = None

    # -- history --------------------------------------------------------
    def add_user(self, text: str) -> None:
        """Record a user turn."""
        self._append({"role": "user", "content": str(text)})

    def add_assistant(self, text: str) -> None:
        """Record an assistant turn."""
        self._append({"role": "assistant", "content": str(text)})

    def add_tool_result(self, tool_name: str, result="", success: bool = True, **kwargs) -> None:
        """Record the outcome of a tool call.

        ``result`` may be a string or any object (converted with ``str``).
        ``kwargs`` accepts ``error=`` / extra fields for convenience.
        """
        content = str(result) if result != "" else ""
        if kwargs.get("error"):
            content = (content + f" (error: {kwargs['error']})").strip()
        self._append(
            {
                "role": "tool",
                "content": content,
                "tool": str(tool_name),
                "success": bool(success),
            }
        )

    def _append(self, entry: dict) -> None:
        self._history.append(entry)
        if len(self._history) > self.max_history:
            del self._history[: len(self._history) - self.max_history]

    def history(self, limit: int | None = None) -> list[dict]:
        """Return a copy of the history (most recent ``limit`` entries)."""
        entries = list(self._history)
        if limit is not None and limit >= 0:
            entries = entries[-limit:] if limit else []
        return entries

    def to_messages(self) -> list:
        """Return the history as a list of ``ChatMessage`` objects.

        Tool results become ``user``-role messages prefixed with the tool
        name, since not every provider accepts a ``tool`` role.
        """
        messages = []
        for entry in self._history:
            role = entry.get("role", "user")
            content = entry.get("content", "")
            if role == "tool":
                content = f"[Tool '{entry.get('tool', 'tool')}' result]: {content}"
                role = "user"
            if ChatMessage is not None:
                messages.append(ChatMessage(role=role, content=content))
            else:  # pragma: no cover - fallback if ai package is absent
                messages.append({"role": role, "content": content})
        return messages

    @property
    def last_user_text(self) -> str:
        """The most recent user message, or ``""`` when there is none."""
        for entry in reversed(self._history):
            if entry.get("role") == "user":
                return entry.get("content", "")
        return ""

    # -- last file / folder ---------------------------------------------
    def set_last_path(self, path: str | None, kind: str | None = None) -> None:
        """Remember ``path`` as the most recently referenced file/folder.

        ``kind`` may be ``"file"`` or ``"folder"``; when omitted it is
        inferred from the path suffix (a trailing separator or no suffix
        counts as a folder only when explicitly known -- otherwise it is
        recorded as the generic last path and as a file when it has an
        extension).
        """
        if not path:
            return
        text = str(path)
        self._last_path = text
        if kind == "folder" or text.endswith(("/", "\\")):
            self._last_folder = text.rstrip("/\\") or text
        elif kind == "file" or Path(text).suffix:
            self._last_file = text
        else:
            # No extension and no explicit kind: keep it as the last path
            # only, so "open it" still resolves, without guessing file/folder.
            pass

    @property
    def last_path(self) -> str | None:
        """The most recently referenced file or folder path, if any."""
        return self._last_path

    @property
    def last_file(self) -> str | None:
        """The most recently referenced file path, if any."""
        return self._last_file

    @property
    def last_folder(self) -> str | None:
        """The most recently referenced folder path, if any."""
        return self._last_folder

    # -- lifecycle --------------------------------------------------------
    def clear(self) -> None:
        """Drop all history and remembered paths."""
        self._history.clear()
        self._last_path = self._last_file = self._last_folder = None

    def summary(self) -> str:
        """Return a one-line summary of the conversation so far."""
        users = sum(1 for e in self._history if e.get("role") == "user")
        assistants = sum(1 for e in self._history if e.get("role") == "assistant")
        tools = sum(1 for e in self._history if e.get("role") == "tool")
        parts = [f"{users} user, {assistants} assistant, {tools} tool turns"]
        if self._last_path:
            parts.append(f"last path: {self._last_path}")
        last = self.last_user_text
        if last:
            parts.append(f"last user message: {last[:80]}")
        return "; ".join(parts)
