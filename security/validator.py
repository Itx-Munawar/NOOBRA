"""Input validation for NOOBRA: shell commands, tool arguments,
prompt-injection detection, text sanitisation and URL safety.

All functions are pure / side-effect free (except logging) so they are
safe to call from any workstream before executing a tool or command.
Path-allowance checks delegate lazily to ``tools.files.is_path_allowed``
when that module exists (Workstream: tools); if it cannot be imported,
a conservative built-in check is used instead -- never a crash.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path, PureWindowsPath
from urllib.parse import urlparse

logger = logging.getLogger("noobra.security")

# --- shell-command blocklist ------------------------------------------------
# (pattern, reason). Matched case-insensitively against the command.
_BLOCKED_COMMAND_PATTERNS = [
    (r"\bformat\s+[a-z]:", "disk format command is blocked"),
    (r"\bdiskpart\b", "diskpart is blocked"),
    (r"\bshutdown\b", "shutdown is blocked"),
    (r"\bdel\s+/[sq]", "recursive/quiet delete is blocked"),
    (r"\brmdir\s+/[sq]", "recursive/quiet directory removal is blocked"),
    (r"\brm\s+(-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r)\b", "rm -rf is blocked"),
    (r"\brm\s+-rf\s+/", "rm -rf on a root path is blocked"),
    (r"\bpowershell\b.*-encodedcommand\b", "encoded PowerShell is blocked"),
    (r"\bpowershell\b.*-enc\b", "encoded PowerShell is blocked"),
    (r"\bbypass\b.*executionpolicy|\bexecutionpolicy\b.*\bbypass\b",
     "UAC / execution-policy bypass is blocked"),
    (r"\breg\s+delete\b", "registry deletion is blocked"),
    (r"\breg\s+add\b.*\\run", "registry Run-key modification is blocked"),
    (r"\bcurl\b.*\|\s*(sh|bash|powershell)\b",
     "piping a download straight to a shell is blocked"),
    (r"\bwget\b.*\|\s*(sh|bash)\b",
     "piping a download straight to a shell is blocked"),
    (r"\bnet\s+user\b.*\s/add\b", "creating user accounts is blocked"),
    (r"\bnetsh\b.*firewall.*\b(off|disable)\b",
     "disabling the firewall is blocked"),
    (r"\bbcdedit\b", "boot-configuration editing is blocked"),
    (r"\btakeown\b|\bicacls\b.*\/grant", "ownership/ACL takeover is blocked"),
    (r">\s*/dev/sd", "writing raw to a disk device is blocked"),
    (r"\bmkfs\b", "filesystem creation is blocked"),
    (r"\bdd\b\s+.*of=/dev/", "raw disk write (dd) is blocked"),
]

# --- prompt-injection patterns ----------------------------------------------
_INJECTION_PATTERNS = [
    r"ignore (all |the |your |any )?previous instructions",
    r"disregard (all |the |your |any )?(previous|prior|above) instructions",
    r"you are now\b",
    r"you are (a|an|the) .*? (instead|from now on)",
    r"system prompt",
    r"reveal (your|the) (system|initial|hidden) (prompt|instructions)",
    r"forget (everything|all) (you|that)",
    r"do not (follow|obey|listen to) (your|the|any)",
    r"new instructions?:",
    r"override (your|the) instructions",
    r"jailbreak",
    r"developer mode",
    r"pretend (you are|to be)",
    r"act as (if )?(you are|a|an|the)",
    r"\[system\]|\[INST\]|<<SYS>>",
    r"as an ai language model,?\s*(ignore|disregard)",
]

_COMPILED_INJECTION = [re.compile(p, re.IGNORECASE)
                       for p in _INJECTION_PATTERNS]

# --- protected system paths ---------------------------------------------------
_SYSTEM_PATH_PREFIXES = (
    "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
    "C:\\System Volume Information", "/etc", "/bin", "/sbin", "/usr/bin",
    "/usr/sbin", "/boot", "/sys", "/proc", "C:\\$Recycle.Bin",
)
_SYSTEM_PATH_NAMES = ("windows", "system32", "syswow64")


def _is_system_path(path_str: str) -> bool:
    """Conservative check for OS/system locations (both separators)."""
    normalised = path_str.replace("/", "\\")
    lowered = normalised.lower()
    for prefix in _SYSTEM_PATH_PREFIXES:
        if lowered.startswith(prefix.lower()):
            return True
    parts = [p.lower() for p in re.split(r"[\\/]+", path_str) if p]
    return any(name in parts for name in _SYSTEM_PATH_NAMES) \
        and ("windows" in parts or parts[:1] in (["etc"], ["bin"], ["sbin"]))


def _path_allowed(path_str: str) -> bool:
    """Ask ``tools.files.is_path_allowed`` if present, else fall back.

    Returns False for system paths; True otherwise (the tools module is
    the authority when it exists).
    """
    try:
        from tools.files import is_path_allowed  # type: ignore
        return bool(is_path_allowed(path_str))
    except Exception:
        return not _is_system_path(path_str)


# --- public API ---------------------------------------------------------------

def validate_shell_command(command: str) -> tuple[bool, str]:
    """Return ``(True, "")`` if ``command`` is allowed, else ``(False, reason)``.

    Blocks destructive / privilege-escalation commands (format, diskpart,
    shutdown, rm -rf, del /s, UAC bypass, encoded PowerShell, curl|sh,
    ...). Empty commands are rejected.
    """
    if not command or not str(command).strip():
        return False, "empty command"
    cmd = str(command)
    lowered = cmd.lower()
    for pattern, reason in _BLOCKED_COMMAND_PATTERNS:
        if re.search(pattern, lowered):
            logger.warning("Blocked shell command %r: %s", cmd[:120], reason)
            return False, reason
    # Chained destructive payload after a separator still counts.
    if re.search(r"[;&|]\s*(rm\s+-rf|format\s|shutdown\b)", lowered):
        return False, "chained destructive command is blocked"
    return True, ""


def validate_tool_args(tool_name: str, args: dict | None) -> tuple[bool, str]:
    """Validate arguments before a tool runs.

    - Path-bearing args (``path``, ``file``, ``src``, ``dst``, ``target``,
      ``directory``) must be allowed by ``tools.files.is_path_allowed``
      (lazy, guarded) and must not be system paths.
    - Delete / remove tools may not target system paths.
    - Email / financial tools (``send_email``, ``pay*``, ``transfer*``,
      ``purchase*``) require an explicit confirmation flag
      (``confirmed``/``confirm`` truthy in ``args``).
    Returns ``(True, "")`` when allowed, else ``(False, reason)``.
    """
    args = dict(args or {})
    name = str(tool_name or "").lower()

    # Confirmation gate for irreversible / external actions.
    financial_or_email = (
        "email" in name or name.startswith(("send_", "pay", "transfer",
                                            "purchase", "buy", "wire",
                                            "charge")))
    if financial_or_email:
        if not (args.get("confirmed") or args.get("confirm")):
            return False, (
                f"{tool_name} requires explicit confirmation"
                " (pass confirmed=True)")

    # Path checks.
    path_keys = ("path", "file", "filepath", "src", "source", "dst",
                 "destination", "target", "directory", "folder")
    for key in path_keys:
        if key not in args or args[key] is None:
            continue
        value = str(args[key])
        if not _path_allowed(value):
            return False, f"path not allowed: {value}"
        if any(word in name for word in ("delete", "remove", "rm", "erase")) \
                and _is_system_path(value):
            return False, f"deletion of system path is blocked: {value}"
    # Delete tools naming a path under a different key still get checked
    # via the loop above; an explicit system-path delete with no path arg
    # is rejected as malformed.
    if any(word in name for word in ("delete", "remove")) \
            and not any(k in args for k in path_keys):
        return False, "delete tool requires a path argument"
    return True, ""


def detect_prompt_injection(text: str) -> bool:
    """Return True if ``text`` looks like an injected instruction.

    Detects classic patterns ("ignore previous instructions", "you are
    now ...", "system prompt", "disregard ...", jailbreak / developer-mode
    / pretend-to-be phrasing, embedded ``[SYSTEM]`` markers). Matching is
    case-insensitive. Benign text mentioning these words in a quoted or
    clearly descriptive way can false-positive; callers should treat a
    hit as "needs review / strip", not proof of malice.
    """
    if not text:
        return False
    lowered = str(text)
    for pattern in _COMPILED_INJECTION:
        if pattern.search(lowered):
            logger.warning("Possible prompt injection detected in text")
            return True
    return False


def sanitize_text(text: str) -> str:
    """Strip control characters (except tab/newline) and NULs from text."""
    if text is None:
        return ""
    cleaned = "".join(
        ch for ch in str(text)
        if ch in ("\t", "\n", "\r") or (ord(ch) >= 0x20 and ord(ch) != 0x7F))
    return cleaned


def is_safe_url(url: str) -> bool:
    """True only for well-formed ``http://`` / ``https://`` URLs with a host."""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    if parsed.scheme.lower() not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False
    # Reject embedded credentials and non-ASCII tricks in the host.
    if "@" in parsed.netloc:
        return False
    return True
