"""Instruction planner for NOOBRA.

Turns a natural-language instruction (English, Roman Urdu, or a mix)
into a :class:`Plan` of tool steps. Strategy:

1. Try the LLM (first provider in the chain that answers) with a strict
   JSON-only prompt built from the available tool schemas.
2. If there is no provider/key, or the LLM fails / returns bad JSON,
   fall back to a rule-based parser that works fully offline.

The rule-based parser is real logic, not a stub: it handles opening
apps, creating folders, web/YouTube search, opening websites, listing
and reading files, and copying/moving files in both languages.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("noobra.core.planner")

# Roman Urdu cue words, used for language detection and for parsing.
ROMAN_URDU_KEYWORDS = {
    "kholo", "khol", "karo", "kar", "banao", "banado", "bana", "dhoondo",
    "dhoond", "par", "mein", "main", "mujhe", "mujh", "mera", "meri",
    "mere", "aur", "ka", "ki", "ke", "ko", "se", "hai", "hain", "tha",
    "kya", "kahan", "kab", "kaise", "chahiye", "dekho", "dikhao", "sunao",
    "batao", "likho", "parho", "chalao", "band", "karo", "jao",
}

APP_ALIASES = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "browser": "chrome",
    "vs code": "vs code",
    "vscode": "vs code",
    "visual studio code": "vs code",
    "code": "vs code",
    "notepad": "notepad",
    "explorer": "explorer",
    "file explorer": "explorer",
    "settings": "settings",
    "calculator": "calculator",
    "calc": "calculator",
    "word": "word",
    "excel": "excel",
    "powerpoint": "powerpoint",
    "paint": "paint",
    "terminal": "terminal",
    "cmd": "terminal",
    "spotify": "spotify",
    "whatsapp": "whatsapp",
    "youtube": "youtube",
    "telegram": "telegram",
    "discord": "discord",
    "zoom": "zoom",
    "teams": "teams",
    "outlook": "outlook",
    "edge": "edge",
    "firefox": "firefox",
}

KNOWN_FOLDERS = {
    "desktop": "Desktop",
    "documents": "Documents",
    "downloads": "Downloads",
    "pictures": "Pictures",
    "music": "Music",
    "videos": "Videos",
    "home": "",
}

KNOWN_TOOLS = {
    "open_app", "search_google", "search_youtube", "navigate", "read_file",
    "list_windows", "create_folder", "list_directory", "search_files",
    "read_content", "move_file", "copy_file", "rename_file",
    "organize_downloads", "run_command", "fill_form", "upload_file",
    "delete_file", "delete_folder", "run_admin_command", "send_email",
    "submit_form", "install_software", "close_app", "open_website",
    "open_file", "list_files", "write_file", "create_file",
}


def detect_roman_urdu(text: str) -> bool:
    """Return True when ``text`` looks like Roman Urdu (or a mix of it)."""
    if not text:
        return False
    words = set(re.findall(r"[a-zA-Z]+", text.lower()))
    return bool(words & ROMAN_URDU_KEYWORDS)


@dataclass
class PlanStep:
    """One tool call in a plan."""

    tool: str
    args: dict = field(default_factory=dict)
    description: str = ""
    verify: str | None = None
    approved: bool = False  # set True once the user approved this step


@dataclass
class Plan:
    """A planned (or not-yet-plannable) response to an instruction."""

    steps: list = field(default_factory=list)
    clarification_needed: bool = False
    clarification_question: str | None = None


class Planner:
    """Builds a :class:`Plan` from an instruction, via LLM then rules."""

    def __init__(self, provider_chain=None):
        # provider_chain: list of BaseProvider, or None (lazy, offline-first
        # callers may pass [] to force the rule-based parser).
        self.provider_chain = provider_chain

    # -- public API -----------------------------------------------------
    def plan(self, instruction: str, context=None, tool_schemas=None) -> Plan:
        """Plan ``instruction`` into tool steps (or a clarification)."""
        text = (instruction or "").strip()
        if not text:
            return Plan(
                clarification_needed=True,
                clarification_question=(
                    "Please tell me what you'd like me to do. / "
                    "Batao, main aap ke liye kya karoon?"
                ),
            )
        # Ambiguous instructions are clarified before any LLM/rule work.
        ambiguous = self._ambiguous_clarification(text, context)
        if ambiguous is not None:
            return ambiguous

        chain = self._resolve_chain()
        if chain:
            try:
                llm_plan = self._plan_with_llm(text, context, tool_schemas, chain)
                if llm_plan is not None:
                    return llm_plan
            except Exception as exc:  # LLM failure -> rule fallback, never crash
                logger.warning("LLM planning failed, using rule-based fallback: %s", exc)
        return self._plan_with_rules(text, context)

    # -- LLM planning ---------------------------------------------------
    def _resolve_chain(self):
        if self.provider_chain is not None:
            return list(self.provider_chain)
        try:
            try:
                from ai import get_provider_chain
            except ImportError:
                from ..ai import get_provider_chain
            return get_provider_chain()
        except Exception as exc:
            logger.debug("Could not build provider chain: %s", exc)
            return []

    def _plan_with_llm(self, text, context, tool_schemas, chain):
        tools = self._tool_descriptions(tool_schemas)
        try:
            from ai.provider import ChatMessage
        except ImportError:
            from ..ai.provider import ChatMessage
        history_text = ""
        if context is not None:
            try:
                history_text = f"Conversation so far:\n{context.summary()}\n"
            except Exception:
                history_text = ""
        prompt = (
            "You are NOOBRA's planner. Convert the user's instruction into a plan.\n"
            f"{history_text}"
            "Available tools (use ONLY these tool names):\n"
            f"{tools}\n\n"
            "Instruction: " + text + "\n\n"
            "Reply with ONLY a JSON object, no other text, no code fences:\n"
            '{"steps": [{"tool": "<tool name>", "args": {...}, '
            '"description": "<short description>", "verify": "<how to check it worked or null>"}], '
            '"clarification_needed": false, "clarification_question": null}\n'
            "If the instruction is ambiguous or a required target is missing, "
            'return {"steps": [], "clarification_needed": true, '
            '"clarification_question": "<your question in the user\'s language>"}.'
        )
        messages = [
            ChatMessage(role="system", content="You output only valid JSON plans."),
            ChatMessage(role="user", content=prompt),
        ]
        last_error = None
        for provider in chain:
            try:
                data = provider.chat_json(messages, temperature=0.2)
                return self._plan_from_llm_data(data, text)
            except Exception as exc:
                last_error = exc
                logger.warning("Provider %s failed during planning: %s", provider.name, exc)
                continue
        if last_error is not None:
            logger.debug("All providers failed during planning: %s", last_error)
        return None

    @staticmethod
    def _tool_descriptions(tool_schemas):
        if tool_schemas:
            lines = []
            for schema in tool_schemas:
                if isinstance(schema, dict):
                    lines.append(
                        f"- {schema.get('name')}: {schema.get('description', '')} "
                        f"args: {json.dumps(schema.get('parameters', {}))}"
                    )
                else:
                    lines.append(f"- {getattr(schema, 'name', schema)}: "
                                 f"{getattr(schema, 'description', '')}")
            return "\n".join(lines)
        return "\n".join(
            f"- {name}" for name in sorted(KNOWN_TOOLS)
        )

    @staticmethod
    def _normalize_llm_args(tool, args):
        """Map LLM arg aliases to schema names, unwrapping dict values."""
        out = dict(args or {})
        for key, value in list(out.items()):
            if isinstance(value, dict):
                for sub in ("app_name", "name", "app", "value", "target"):
                    if sub in value and isinstance(value[sub], str):
                        out[key] = value[sub]
                        break
                else:
                    first = next((v for v in value.values() if isinstance(v, str)), None)
                    if first is not None:
                        out[key] = first
        aliases = {
            "app_name": "name", "app": "name", "application": "name",
            "source": "src", "destination": "dst",
            "source_path": "src", "destination_path": "dst",
        }
        for alias, canonical in aliases.items():
            if alias in out and canonical not in out:
                out[canonical] = out.pop(alias)
            elif alias in out:
                out.pop(alias, None)
        return out

    @staticmethod
    def _plan_from_llm_data(data, text):
        if not isinstance(data, dict):
            return None
        if data.get("clarification_needed"):
            question = data.get("clarification_question") or (
                "Could you give me a bit more detail about what you'd like?"
            )
            return Plan(clarification_needed=True, clarification_question=str(question))
        steps = []
        for raw in data.get("steps") or []:
            if not isinstance(raw, dict):
                continue
            tool = str(raw.get("tool", "")).strip()
            if not tool:
                continue
            if tool not in KNOWN_TOOLS:
                logger.warning("LLM suggested unknown tool %r; skipping step", tool)
                continue
            steps.append(
                PlanStep(
                    tool=tool,
                    args=Planner._normalize_llm_args(tool, dict(raw.get("args") or {})),
                    description=str(raw.get("description") or f"Run {tool}"),
                    verify=raw.get("verify"),
                )
            )
        if not steps:
            return None  # fall through to the rule-based parser
        return Plan(steps=steps)

    # -- ambiguity --------------------------------------------------------
    @staticmethod
    def _ambiguous_clarification(text, context):
        lowered = text.lower().strip()
        roman = detect_roman_urdu(text)
        # "delete this folder/file" (or "delete it") with no named target.
        if re.search(r"\b(delete|remove|hatao|delete karo)\b", lowered):
            if re.search(r"\b(this|that|it|ye|yeh|is|us)\b", lowered) and not re.search(
                r"[\"'“”][^\"'“”]+[\"'“”]|\b\w+\.(txt|pdf|docx|jpg|png|mp3|mp4)\b", lowered
            ):
                # A named path after "delete" counts as a target; bare
                # "delete this folder" does not.
                if not re.search(r"\bdelete\s+(?:this\s+)?(?:the\s+)?([a-z0-9 _\-/\\]+)$", lowered):
                    return Plan(
                        clarification_needed=True,
                        clarification_question=(
                            "Kaunsa folder/file delete karna hai? Naam ya path batao."
                            if roman else
                            "Which folder or file should I delete? Please give its name or path."
                        ),
                    )
                # The regex above matches almost anything, so re-check:
                # only treat it as targeted if a quoted name / filename /
                # known folder was given.
                if not re.search(
                    r"[\"'][^\"']+[\"']|\.(txt|pdf|docx|jpg|png|mp3|mp4)\b|"
                    r"\b(desktop|documents|downloads)\b", lowered
                ):
                    return Plan(
                        clarification_needed=True,
                        clarification_question=(
                            "Kaunsa folder/file delete karna hai? Naam ya path batao."
                            if roman else
                            "Which folder or file should I delete? Please give its name or path."
                        ),
                    )
        # "open it" / "close it" / "us ko kholo" with no remembered path.
        if re.search(r"\b(open|close|kholo|band karo)\s+(it|is|us|ye|yeh)\b", lowered) or lowered in {
            "open it", "close it", "kholo", "khol do", "us ko kholo", "is ko kholo",
        }:
            last_path = None
            if context is not None:
                try:
                    last_path = context.last_path
                except Exception:
                    last_path = None
            if not last_path:
                return Plan(
                    clarification_needed=True,
                    clarification_question=(
                        "Kya kholoon? App, file ya website ka naam batao."
                        if roman else
                        "What should I open? Please give the app, file, or website name."
                    ),
                )
        return None

    # -- rule-based planning (offline) ------------------------------------
    def _plan_with_rules(self, text, context, _allow_split=True) -> Plan:
        lowered = text.lower().strip()
        roman = detect_roman_urdu(text)

        # Multi-action instructions joined by "aur"/"and", e.g.
        # "Chrome kholo aur YouTube par Python tutorials search karo."
        if _allow_split:
            parts = re.split(r"\s+(?:aur|and)\s+", text.strip(), flags=re.IGNORECASE)
            if len(parts) > 1:
                steps: list[PlanStep] = []
                for part in parts:
                    sub = self._plan_with_rules(part, context, _allow_split=False)
                    if sub.clarification_needed or not sub.steps:
                        break
                    steps.extend(sub.steps)
                else:
                    return Plan(steps=steps)
                # If any part could not be planned, fall through and plan
                # the whole instruction as a single step instead.

        # 1. Close an app: "chrome band karo / close notepad"
        #    (English verb-first AND Roman Urdu verb-final order.)
        match = re.search(r"\b(?:close|band karo|band kar|close karo)\s+(?:the\s+)?(.+?)\s*$", lowered)
        if not match:
            match = re.search(r"^(.+?)\s+(?:band karo|band kar|close karo)\s*[.!?]*$", lowered)
        if match:
            app = self._match_app(match.group(1)) or match.group(1).strip()
            return Plan(steps=[PlanStep(
                tool="close_app", args={"name": app},
                description=f"Close {app}", verify=f"{app} is no longer running",
            )])

        # 2. Create a folder: "Desktop par X folder banao" / "create folder named X on Desktop"
        step = self._rule_create_folder(text, lowered)
        if step:
            return Plan(steps=[step])

        # 3. Search YouTube / Google.
        step = self._rule_search(text, lowered)
        if step:
            return Plan(steps=[step])

        # 4. Copy / move a file.
        step = self._rule_copy_move(text, lowered)
        if step:
            return Plan(steps=[step])

        # 5. Delete a named file/folder (target present -> real step).
        match = re.search(
            r"\bdelete\s+(?:the\s+)?(?:folder|file)?\s*[\"'“”]?([^\"'“”]+?)[\"'“”]?\s*$", lowered
        )
        if re.search(r"\b(delete|remove)\b", lowered) and match and match.group(1).strip():
            target = match.group(1).strip()
            if target not in ("this", "that", "it", "ye", "yeh", "is", "us"):
                is_folder = "folder" in lowered
                return Plan(steps=[PlanStep(
                    tool="delete_folder" if is_folder else "delete_file",
                    args={"path": self._resolve_path(target)},
                    description=f"Delete {target}",
                    verify=f"{target} no longer exists",
                )])

        # 6. Open a website / URL.
        url = self._extract_url(text)
        if url and re.search(r"\b(open|kholo|visit|go to|navigate)\b", lowered):
            return Plan(steps=[PlanStep(
                tool="browser_navigate", args={"url": url},
                description=f"Open {url}", verify=f"{url} is open in the browser",
            )])

        # 7. List files in a folder: "Desktop par files dikhao / list files in Downloads"
        match = re.search(
            r"\b(?:list|show|dikhao|dekho|dikhado)\b.*\b(?:files?|folders?)\b.*\b(?:in|on|par|mein|of)\s+([a-z0-9 _\-/\\]+?)\s*$",
            lowered,
        )
        if match or re.search(r"\b(list|show)\b.*\bfiles?\b", lowered):
            folder = (match.group(1).strip() if match else "Desktop")
            return Plan(steps=[PlanStep(
                tool="list_directory", args={"path": self._resolve_path(folder)},
                description=f"List files in {folder}",
                verify=f"file list for {folder} returned",
            )])

        # 8. Read a file: "read X / X file parho"
        match = re.search(r"\b(?:read|parho|open|kholo)\b.*?\b([a-z0-9_\- ]+\.(?:txt|md|pdf|docx|csv|log|json))\b", lowered)
        if match:
            name = match.group(1).strip()
            return Plan(steps=[PlanStep(
                tool="read_file", args={"path": self._resolve_path(name)},
                description=f"Read {name}", verify=f"contents of {name} returned",
            )])

        # 9. Search for a file: "X file dhoondo / find file named X"
        match = re.search(r"\b(?:find|search|dhoondo|dhoond)\b.*?\b(?:file|folder)?\s*(?:named\s+)?([a-z0-9_\- ]+?)\s*$", lowered)
        if match and re.search(r"\b(file|dhoond|find)\b", lowered):
            query = match.group(1).strip().strip("\"'")
            if query and query not in ("it", "this"):
                return Plan(steps=[PlanStep(
                    tool="search_files", args={"directory": str(Path.home()), "pattern": query},
                    description=f"Search for {query}",
                    verify=f"search results for {query} returned",
                )])

        # 10. Organize downloads.
        if re.search(r"\borganize\b.*\bdownloads?\b", lowered) or "downloads organize" in lowered:
            return Plan(steps=[PlanStep(
                tool="organize_downloads", args={},
                description="Organize the Downloads folder",
                verify="Downloads folder is organized",
            )])

        # 11. Open an app (incl. "it" with context): "Chrome kholo / open vs code"
        #     Roman Urdu is verb-final ("Chrome kholo"), English verb-first.
        app_match = re.search(r"\b(?:open|kholo|khol|launch|start|chalao)\b\s+(?:the\s+)?(.+?)\s*$", lowered)
        if not app_match:
            app_match = re.search(r"^(.+?)\s+(?:kholo|khol|open karo|launch karo|chalao)\s*[.!?]*$", lowered)
        if app_match:
            target = app_match.group(1).strip().strip("\"'")
            if target in ("it", "is", "us", "ye", "yeh") and context is not None:
                last_path = None
                try:
                    last_path = context.last_path
                except Exception:
                    last_path = None
                if last_path:
                    return Plan(steps=[PlanStep(
                        tool="browser_navigate", args={"url": last_path if str(last_path).startswith("http") else "file://" + str(last_path)},
                        description=f"Open {last_path}", verify=f"{last_path} is open",
                    )])
            app = self._match_app(target)
            if app:
                return Plan(steps=[PlanStep(
                    tool="open_app", args={"name": app},
                    description=f"Open {app}", verify=f"{app} is open",
                )])
            if target:
                # Unknown app name: still try opening it by name.
                return Plan(steps=[PlanStep(
                    tool="open_app", args={"name": target},
                    description=f"Open {target}", verify=f"{target} is open",
                )])

        # 12. "Open it" with context but no verb match above.
        if context is not None:
            try:
                if context.last_path and lowered in ("open it", "kholo", "khol do"):
                    return Plan(steps=[PlanStep(
                        tool="browser_navigate", args={"url": str(context.last_path) if str(context.last_path).startswith("http") else "file://" + str(context.last_path)},
                        description=f"Open {context.last_path}",
                        verify=f"{context.last_path} is open",
                    )])
            except Exception:
                pass

        # Nothing matched: ask for clarification rather than guessing.
        return Plan(
            clarification_needed=True,
            clarification_question=(
                "Sorry, main samjha nahi — aap kya karwana chahte hain? "
                "Misaal: 'Chrome kholo', 'Desktop par Notes folder banao', "
                "ya 'YouTube par Python search karo'."
                if roman else
                "Sorry, I didn't understand that — what would you like me to do? "
                "For example: 'Open Chrome', 'Create a folder named Notes on Desktop', "
                "or 'Search YouTube for Python tutorials'."
            ),
        )

    # -- rule helpers -----------------------------------------------------
    @staticmethod
    def _extract_url(text: str) -> str | None:
        """Return the first URL / domain in ``text``, normalised, or None."""
        match = re.search(r"https?://[^\s\"'<>]+", text, re.IGNORECASE)
        if match:
            return match.group(0).rstrip(".,)")
        match = re.search(r"\b(?:www\.)?[a-z0-9\-]+\.[a-z]{2,}(?:/[^\s\"'<>]*)?", text, re.IGNORECASE)
        if match:
            url = match.group(0).rstrip(".,)")
            return url if url.lower().startswith("http") else "https://" + url
        return None

    @staticmethod
    def _match_app(target: str) -> str | None:
        target = target.strip().lower()
        if target in APP_ALIASES:
            return APP_ALIASES[target]
        for alias, canonical in APP_ALIASES.items():
            if alias in target:
                return canonical
        return None

    @staticmethod
    def _resolve_path(target: str) -> str:
        """Resolve a bare name / known folder into an absolute-ish path."""
        target = target.strip().strip("\"'").strip()
        if not target:
            return str(Path.home())
        if os.path.isabs(target) or re.match(r"^[A-Za-z]:[\\/]", target):
            return target
        lowered = target.lower()
        for folder_key, folder_name in KNOWN_FOLDERS.items():
            if lowered == folder_key or lowered.startswith(folder_key + " ") or lowered.startswith(folder_key + "/") or lowered.startswith(folder_key + "\\"):
                rest = target[len(folder_key):].strip(" /\\")
                base = Path.home() / folder_name if folder_name else Path.home()
                return str(base / rest) if rest else str(base)
            if lowered.endswith(" " + folder_key) or lowered.endswith("/" + folder_key):
                return str(Path.home() / folder_name) if folder_name else str(Path.home())
        # A filename with an extension probably lives on the Desktop.
        if Path(target).suffix:
            return str(Path.home() / "Desktop" / target)
        return str(Path.home() / target)

    def _rule_create_folder(self, text, lowered):
        # "create folder named X on Desktop" / "Desktop par X folder banao"
        # Run on the original text (case-insensitive) so the folder name
        # keeps its original capitalisation.
        match = re.search(
            r"\b(?:create|make|banao|banado|bana)\b.*?\bfolder\b\s*(?:named\s+|called\s+)?"
            r"[\"'“”]?([A-Za-z0-9 _\-]+?)[\"'“”]?\s*(?:on|in|par|mein)?\s*"
            r"(desktop|documents|downloads|home)?\s*[.!?]*$",
            text, re.IGNORECASE,
        )
        if not match:
            match = re.search(
                r"\b(desktop|documents|downloads|home)\b\s+par\s+"
                r"[\"'“”]?([A-Za-z0-9 _\-]+?)[\"'“”]?\s+folder\s+(?:banao|banado|bana)\b",
                text, re.IGNORECASE,
            )
            if match:
                location, name = match.group(1).lower(), match.group(2)
                path = str((Path.home() / KNOWN_FOLDERS[location]) / name.strip()) if KNOWN_FOLDERS[location] else str(Path.home() / name.strip())
                return PlanStep(tool="create_folder", args={"path": path},
                                description=f"Create folder {name.strip()} on {location}",
                                verify=f"folder {name.strip()} exists")
            return None
        name = match.group(1).strip()
        location = (match.group(2) or "desktop").strip().lower()
        if name in ("a", "an", "the", ""):
            return None
        base = Path.home() / KNOWN_FOLDERS.get(location, "Desktop") if KNOWN_FOLDERS.get(location) else Path.home()
        path = str(base / name)
        return PlanStep(tool="create_folder", args={"path": path},
                        description=f"Create folder {name} on {location.title()}",
                        verify=f"folder {name} exists")

    def _rule_search(self, text, lowered):
        # YouTube first (more specific), then Google. Run on the original
        # text (case-insensitive) so the query keeps its capitalisation.
        yt = re.search(
            r"\byoutube\b.*?\b(?:search|dhoondo|karo|par)\b\s*(?:for\s+)?(.+?)\s*$", text, re.IGNORECASE
        ) or re.search(
            r"\bsearch\b.*?\byoutube\b\s*(?:for\s+)?(.+?)\s*$", text, re.IGNORECASE
        ) or re.search(
            r"\byoutube\b\s+par\s+(.+?)\s*(?:search|dhoondo)?\s*(?:karo)?\s*$", text, re.IGNORECASE
        )
        if yt:
            query = self._clean_query(yt.group(1))
            if query:
                return PlanStep(tool="search_youtube", args={"query": query},
                                description=f"Search YouTube for {query}",
                                verify=f"YouTube results for {query} shown")
        g = re.search(
            r"\bgoogle\b.*?\b(?:search|dhoondo|karo|par)\b\s*(?:for\s+)?(.+?)\s*$", text, re.IGNORECASE
        ) or re.search(
            r"\bsearch\b.*?\bgoogle\b\s*(?:for\s+)?(.+?)\s*$", text, re.IGNORECASE
        ) or re.search(
            r"\bgoogle\b\s+par\s+(.+?)\s*(?:search|dhoondo)?\s*(?:karo)?\s*$", text, re.IGNORECASE
        ) or re.search(
            r"\bsearch\s+(?:google\s+)?for\s+(.+?)\s*$", text, re.IGNORECASE
        )
        if g:
            query = self._clean_query(g.group(1))
            if query:
                return PlanStep(tool="search_google", args={"query": query},
                                description=f"Search Google for {query}",
                                verify=f"Google results for {query} shown")
        return None

    @staticmethod
    def _clean_query(query: str) -> str:
        query = query.strip().strip("\"'").rstrip(".!?").strip()
        # Repeatedly strip trailing/leading filler words ("search karo",
        # "karo", "par", "for", ...) until the query stops changing.
        for _ in range(5):
            cleaned = re.sub(
                r"\b(search|karo|kar|dhoondo|dhoond|par|for)\b\s*$", "", query,
                flags=re.IGNORECASE,
            ).strip().rstrip(".!?").strip()
            cleaned = re.sub(
                r"^(search|karo|kar|for)\s+", "", cleaned, flags=re.IGNORECASE,
            ).strip()
            if cleaned == query:
                break
            query = cleaned
        return query

    def _rule_copy_move(self, text, lowered):
        match = re.search(
            r"\b(copy|move)\b\s+(?:the\s+)?(?:file\s+)?(.+?)\s+to\s+(.+?)\s*$", lowered
        )
        if not match:
            match = re.search(
                r"\b(copy|move)\b\s+(?:the\s+)?(.+?)\s+(?:ko|to)\s+(.+?)\s*(?:mein|par|to)?\s*$",
                lowered,
            )
        if not match:
            return None
        verb, source, dest = match.group(1), match.group(2).strip(), match.group(3).strip()
        if not source or not dest:
            return None
        tool = "copy_file" if verb == "copy" else "move_file"
        return PlanStep(tool=tool,
                        args={"source": self._resolve_path(source),
                              "destination": self._resolve_path(dest)},
                        description=f"{verb.title()} {source} to {dest}",
                        verify=f"{source} is in {dest}")
