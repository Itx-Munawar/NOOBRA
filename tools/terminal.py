"""Terminal / shell command tool for NOOBRA.

Runs safe commands via ``subprocess`` with a timeout and a working-directory
restriction (via ``tools.files.is_path_allowed``). Dangerous patterns are
blocked before execution and return ``{"success": False, "error": "blocked
dangerous command"}``. Works fully on Linux and Windows.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
import sys

logger = logging.getLogger("noobra.tools")

try:
    from .files import is_path_allowed, resolve_user_path
except Exception:  # pragma: no cover - direct-module import fallback
    from files import is_path_allowed, resolve_user_path  # type: ignore

__all__ = ["run_command", "BLOCKED_PATTERNS"]

# Substrings / regexes (case-insensitive) that are never executed.
BLOCKED_PATTERNS = (
    r"\bformat\b", r"\bdiskpart\b", r"\bshutdown\b", r"\breboot\b",
    r"\bmkfs\b", r"\bdd\s+if=", r"rm\s+-rf\s+/", r"rm\s+-rf\s+\*",
    r"\bdel\s+/s\b", r"\bdel\s+/q\s+\*",
    r"powershell\s+.*-enc", r"powershell\s+.*-encodedcommand",
    r"curl\s+.*\|\s*(sh|bash)", r"wget\s+.*\|\s*(sh|bash)",
    r"\|\s*sh\b", r"\|\s*bash\b",
    r":\(\)\s*\{\s*:\|",          # fork bomb
    r"\breg\s+delete\b", r"\bbcdedit\b",
    r">\s*/dev/sd", r"\bchmod\s+777\s+/",
    r"rmdir\s+/s\s+/q\s+[a-z]:\\windows",
)
_BLOCKED_RE = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATTERNS]

#: Commands whose first word is explicitly considered safe.
SAFE_COMMANDS = {
    "dir", "ls", "echo", "pwd", "cd", "whoami", "hostname", "date", "time",
    "python", "python3", "py", "pip", "pip3", "git", "node", "npm", "code",
    "type", "cat", "head", "tail", "wc", "find", "grep", "where", "which",
    "systeminfo", "ipconfig", "ping", "tasklist", "ps", "env", "set",
}


def _ok(result=None, verified=False):
    return {"success": True, "result": result, "error": None, "verified": verified}


def _fail(error, result=None):
    return {"success": False, "result": result, "error": str(error), "verified": False}


def _is_blocked(command: str) -> str | None:
    for rx in _BLOCKED_RE:
        if rx.search(command):
            return rx.pattern
    # "rm -rf" anywhere outside an allowed temp/home path is blocked too.
    if re.search(r"\brm\s+-rf\b", command, re.IGNORECASE):
        return "rm -rf"
    return None


def run_command(command, cwd=None, timeout=30):
    """Run ``command`` and capture stdout/stderr.

    * Dangerous patterns (format, diskpart, shutdown, ``rm -rf /``,
      ``del /s``, ``powershell -enc``, ``curl|sh``, ...) are blocked.
    * ``cwd`` (if given) must pass ``is_path_allowed``; default is the home dir.
    * Returns ``{"stdout": str, "stderr": str, "returncode": int, "command": str}``.
    """
    if not command or not str(command).strip():
        return _fail("command is required")
    command = str(command).strip()

    blocked = _is_blocked(command)
    if blocked:
        logger.warning("blocked dangerous command: %r (matched %s)", command, blocked)
        return _fail("blocked dangerous command")

    # Resolve / validate the working directory.
    if cwd is None:
        workdir = os.path.expanduser("~")
    else:
        try:
            workdir = str(resolve_user_path(cwd))
        except Exception as exc:
            return _fail(f"invalid cwd: {exc}")
        if not is_path_allowed(workdir):
            return _fail(f"cwd not allowed: {workdir}")

    if not os.path.isdir(workdir):
        return _fail(f"cwd does not exist: {workdir}")

    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        timeout = 30
    timeout = max(1, min(timeout, 300))

    try:
        if sys.platform == "win32":
            # Windows builtins (dir, echo, ...) need a shell; the blocklist
            # above has already rejected dangerous input.
            proc = subprocess.run(command, shell=True, capture_output=True,
                                  text=True, timeout=timeout, cwd=workdir)
        else:
            argv = shlex.split(command)
            if not argv:
                return _fail("command is required")
            # Warn (but do not block) on commands outside the safe list —
            # they still run, since the blocklist is the security boundary.
            if argv[0].lower() not in SAFE_COMMANDS:
                logger.debug("run_command: %r not in SAFE_COMMANDS, running anyway",
                             argv[0])
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=timeout, cwd=workdir)
    except subprocess.TimeoutExpired:
        return _fail(f"command timed out after {timeout}s")
    except FileNotFoundError as exc:
        return _fail(f"command not found: {exc}")
    except Exception as exc:
        logger.exception("run_command failed for %r", command)
        return _fail(exc)

    result = {
        "command": command,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "returncode": proc.returncode,
        "cwd": workdir,
    }
    if proc.returncode != 0:
        # Command ran but failed — report it as a failure with the output.
        return {"success": False, "result": result,
                "error": f"command exited with code {proc.returncode}: "
                         f"{(proc.stderr or proc.stdout or '').strip()[:500]}",
                "verified": True}
    return _ok(result, verified=True)
