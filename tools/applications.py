"""Application launching / closing tools for NOOBRA.

Windows 11 is the target; on Linux, apps are launched via ``shutil.which``
/ ``xdg-open`` fallbacks so the module still works in the build environment.
All functions return ``{"success", "result", "error", "verified"}`` and never
raise for expected failures.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time

logger = logging.getLogger("noobra.tools")

__all__ = ["APP_MAP", "launch_app", "open_app", "close_app", "is_app_running"]

# ---------------------------------------------------------------------------
# App map: canonical name -> Windows paths/exe, Linux command, process names.
# ---------------------------------------------------------------------------

APP_MAP = {
    "chrome": {
        "name": "Google Chrome",
        "windows_paths": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ],
        "windows_exe": "chrome.exe",
        "linux_cmd": "google-chrome",
        "linux_alternatives": ["google-chrome-stable", "chromium", "chromium-browser"],
        "process_names": ["chrome.exe", "chrome", "google-chrome"],
    },
    "vscode": {
        "name": "Visual Studio Code",
        "windows_paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
            r"C:\Program Files\Microsoft VS Code\Code.exe",
        ],
        "windows_exe": "Code.exe",
        "linux_cmd": "code",
        "linux_alternatives": ["code-insiders", "codium"],
        "process_names": ["Code.exe", "code"],
    },
    "code": {  # alias for vscode
        "name": "Visual Studio Code",
        "windows_paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
            r"C:\Program Files\Microsoft VS Code\Code.exe",
        ],
        "windows_exe": "Code.exe",
        "linux_cmd": "code",
        "linux_alternatives": ["code-insiders", "codium"],
        "process_names": ["Code.exe", "code"],
    },
    "notepad": {
        "name": "Notepad",
        "windows_paths": [r"C:\Windows\System32\notepad.exe"],
        "windows_exe": "notepad.exe",
        "linux_cmd": "gedit",
        "linux_alternatives": ["gnome-text-editor", "kate", "mousepad", "xed"],
        "process_names": ["notepad.exe", "notepad", "gedit"],
    },
    "explorer": {
        "name": "File Explorer",
        "windows_paths": [r"C:\Windows\explorer.exe"],
        "windows_exe": "explorer.exe",
        "linux_cmd": "xdg-open",
        "linux_alternatives": ["nautilus", "dolphin", "thunar"],
        "process_names": ["explorer.exe", "nautilus", "dolphin"],
    },
    "settings": {
        "name": "Settings",
        "windows_paths": [],
        "windows_exe": "ms-settings:",
        "linux_cmd": "gnome-control-center",
        "linux_alternatives": ["gnome-settings", "systemsettings"],
        "process_names": ["SystemSettings.exe", "gnome-control-center"],
    },
    "calculator": {
        "name": "Calculator",
        "windows_paths": [r"C:\Windows\System32\calc.exe"],
        "windows_exe": "calc.exe",
        "linux_cmd": "gnome-calculator",
        "linux_alternatives": ["kcalc", "galculator"],
        "process_names": ["Calculator.exe", "calc.exe", "gnome-calculator"],
    },
    "paint": {
        "name": "Paint",
        "windows_paths": [r"C:\Windows\System32\mspaint.exe"],
        "windows_exe": "mspaint.exe",
        "linux_cmd": "gimp",
        "linux_alternatives": ["pinta", "kolourpaint", "drawing"],
        "process_names": ["mspaint.exe", "gimp", "pinta"],
    },
}


def _ok(result=None, verified=False):
    return {"success": True, "result": result, "error": None, "verified": verified}


def _fail(error, result=None):
    return {"success": False, "result": result, "error": str(error), "verified": False}


def _extract_name(value):
    """Unwrap an app name that arrived as a dict/list/alias.

    LLMs sometimes return ``{"app_name": "chrome"}`` as the *value* of a
    ``name`` argument, or call the tool with ``app_name=`` instead of
    ``name=``. Never stringify a dict into a lookup key — extract the
    first string inside it instead.
    """
    if isinstance(value, dict):
        for key in ("app_name", "name", "app", "application", "target", "value"):
            if key in value and isinstance(value[key], str) and value[key].strip():
                return value[key]
        for v in value.values():
            if isinstance(v, str) and v.strip():
                return v
            if isinstance(v, (list, tuple)) and v and isinstance(v[0], str):
                return v[0]
        return ""
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ""
    return "" if value is None else str(value)


def _norm(name: str) -> str:
    name = _extract_name(name)
    key = name.strip().lower().replace(" ", "").replace("_", "")
    # Friendly names -> canonical keys.
    return {
        "googlechrome": "chrome",
        "vscode": "vscode",
        "visualstudiocode": "vscode",
        "visualstudiocode": "vscode",
    }.get(key, key)


def _resolve_name(name=None, app=None, app_name=None, application=None, kwargs=None):
    """Pick the app name from any accepted alias, unwrapping dicts."""
    kwargs = kwargs or {}
    for candidate in (name, app, app_name, application,
                      kwargs.get("app_name"), kwargs.get("app"),
                      kwargs.get("application"), kwargs.get("target"),
                      kwargs.get("name")):
        extracted = _extract_name(candidate)
        if extracted.strip():
            return extracted
    return None


def _find_windows_exe(entry: dict):
    for candidate in entry.get("windows_paths", []):
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _find_linux_cmd(entry: dict):
    for cmd in [entry.get("linux_cmd")] + entry.get("linux_alternatives", []):
        if cmd and shutil.which(cmd):
            return cmd
    return None


def _ancestor_pids() -> set:
    """PIDs of this process and all its ancestors (via /proc).

    A ``pgrep -f`` pattern can match the command line of the very shell /
    tool-runner that invoked this check (its argv embeds the command text,
    including the app name). Those processes must never be reported as the
    app, and must never be killed by :func:`close_app`.
    """
    ancestors = set()
    pid = os.getpid()
    try:
        while pid and pid > 1 and pid not in ancestors:
            ancestors.add(pid)
            with open(f"/proc/{pid}/status", encoding="utf-8") as fh:
                ppid = None
                for line in fh:
                    if line.startswith("PPid:"):
                        ppid = int(line.split()[1])
                        break
            if ppid is None:
                break
            pid = ppid
    except (OSError, ValueError):
        ancestors.add(os.getpid())
        ancestors.add(os.getppid())
    return ancestors


def is_app_running(name=None, app=None, app_name=None, application=None, **kwargs):
    name = _resolve_name(name, app, app_name, application, kwargs)
    """Return ``{"running": bool, "pids": [...]}`` for an app/process name."""
    key = _norm(name)
    entry = APP_MAP.get(key)
    proc_names = entry["process_names"] if entry else [str(name)]
    pids: list[int] = []
    try:
        if sys.platform == "win32":
            out = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                text=True, timeout=10,
            )
            import csv, io
            for row in csv.reader(io.StringIO(out.stdout)):
                if row and row[0].strip('"').lower() in [p.lower() for p in proc_names]:
                    try:
                        pids.append(int(row[1]))
                    except (ValueError, IndexError):
                        pass
        else:
            # pgrep -f matches the full command line; fall back to -x.
            # Exclude this process and all its ancestors: a -f pattern can
            # match the shell/tool-runner that invoked this check, whose
            # argv embeds the command text (including the app name).
            _self_pids = _ancestor_pids()
            for proc in proc_names:
                for flag in (["-x"], ["-f"]):
                    out = subprocess.run(
                        ["pgrep"] + flag + [proc], capture_output=True,
                        text=True, timeout=10,
                    )
                    if out.returncode == 0:
                        for line in out.stdout.splitlines():
                            try:
                                pid = int(line.strip())
                                if pid not in pids and pid not in _self_pids:
                                    pids.append(pid)
                            except ValueError:
                                continue
                        break
    except FileNotFoundError:
        # pgrep/tasklist unavailable — fall back to ps.
        try:
            out = subprocess.run(["ps", "-eo", "pid,comm"], capture_output=True,
                                 text=True, timeout=10)
            for line in out.stdout.splitlines()[1:]:
                parts = line.split(None, 1)
                if len(parts) == 2 and parts[1].strip().lower() in [p.lower() for p in proc_names]:
                    pids.append(int(parts[0]))
        except Exception as exc:
            logger.exception("is_app_running fallback failed")
            return _fail(exc)
    except Exception as exc:
        logger.exception("is_app_running failed for %s", name)
        return _fail(exc)
    return _ok({"running": bool(pids), "pids": pids, "app": str(name)}, verified=True)


def launch_app(name=None, args=None, app=None, app_name=None, application=None, **kwargs):
    name = _resolve_name(name, app, app_name, application, kwargs)
    """Launch an app by canonical name (see ``APP_MAP``) or executable/path.

    On Windows uses ``subprocess.Popen`` / ``os.startfile`` for ms-settings: URIs;
    on Linux uses the mapped command or ``xdg-open``. Returns
    ``{"app": name, "pid": int|None, "command": ...}``.
    """
    if not name:
        return _fail("app name is required")
    key = _norm(name)
    entry = APP_MAP.get(key)
    args = list(args) if args else []

    # Direct path / executable given by the user.
    if os.path.sep in str(name) or str(name).lower().endswith(".exe"):
        target = os.path.expandvars(str(name))
        if not os.path.exists(target) and not shutil.which(target):
            return _fail(f"executable not found: {name}")
        cmd = [target] + args
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
        except Exception as exc:
            return _fail(exc)
        return _ok({"app": str(name), "pid": proc.pid, "command": cmd}, verified=True)

    if entry is None:
        # Unknown name: try it as a command on PATH (Linux) / start (Windows).
        cmd_name = shutil.which(str(name))
        if cmd_name:
            try:
                proc = subprocess.Popen([cmd_name] + args,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as exc:
                return _fail(exc)
            return _ok({"app": str(name), "pid": proc.pid, "command": [cmd_name] + args},
                       verified=True)
        return _fail(f"unknown app: {name!r} (known: {sorted(APP_MAP)})")

    if sys.platform == "win32":
        if key == "settings" or str(entry.get("windows_exe", "")).endswith(":"):
            try:
                os.startfile("ms-settings:")  # noqa: S606 - intentional, user-requested
            except Exception as exc:
                return _fail(exc)
            return _ok({"app": entry["name"], "pid": None, "command": "ms-settings:"},
                       verified=True)
        exe = _find_windows_exe(entry)
        if exe is None:
            # Fall back to letting Windows resolve it by exe name.
            exe = entry.get("windows_exe")
        try:
            proc = subprocess.Popen([exe] + args, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
        except Exception as exc:
            logger.exception("launch_app failed for %s", name)
            return _fail(exc)
        time.sleep(0.5)
        running = is_app_running(name)
        verified = bool(running.get("success") and running["result"]["running"])
        return _ok({"app": entry["name"], "pid": proc.pid, "command": [exe] + args},
                   verified=verified)

    # Linux fallback.
    cmd = _find_linux_cmd(entry)
    if cmd is None:
        if key == "explorer":
            # Open the home folder with whatever file manager exists.
            try:
                proc = subprocess.Popen(["xdg-open", os.path.expanduser("~")],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return _ok({"app": entry["name"], "pid": proc.pid,
                            "command": ["xdg-open", "~"]}, verified=True)
            except Exception as exc:
                return _fail(exc)
        return _fail(
            f"Windows-only app on Linux: {entry['name']} is not installed "
            f"(tried: {[entry.get('linux_cmd')] + entry.get('linux_alternatives', [])})"
        )
    try:
        full_args = [cmd] + args
        if key == "explorer" and not args:
            full_args = [cmd, os.path.expanduser("~")]
        proc = subprocess.Popen(full_args, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except Exception as exc:
        logger.exception("launch_app failed for %s", name)
        return _fail(exc)
    time.sleep(0.3)
    running = is_app_running(name)
    verified = bool(running.get("success") and running["result"]["running"])
    return _ok({"app": entry["name"], "pid": proc.pid, "command": full_args},
               verified=verified)


def open_app(name=None, args=None, app=None, app_name=None, application=None, **kwargs):
    name = _resolve_name(name, app, app_name, application, kwargs)
    """Alias for :func:`launch_app` used by the planner / tool registry."""
    return launch_app(name, args=args)


def close_app(name=None, app=None, app_name=None, application=None, **kwargs):
    name = _resolve_name(name, app, app_name, application, kwargs)
    """Terminate an app by name: ``taskkill`` on Windows, PID-based
    SIGTERM/SIGKILL on Linux. Verified by checking the app is no longer
    running afterwards."""
    if not name:
        return _fail("app name is required")
    key = _norm(name)
    entry = APP_MAP.get(key)
    proc_names = entry["process_names"] if entry else [str(name)]
    running = is_app_running(name)
    if running.get("success") and not running["result"]["running"]:
        return _ok({"app": str(name), "already_closed": True}, verified=True)
    if not running.get("success"):
        return _fail(f"could not check running state for {name}: {running.get('error')}")
    # Kill by explicit PID only — never `pkill -f <name>`, whose pattern can
    # match (and kill) this very process when its command line mentions the
    # app name. is_app_running() already excludes our own PID.
    import signal
    pids = list(running["result"]["pids"])
    try:
        if sys.platform == "win32":
            for proc in proc_names:
                if proc.lower().endswith(".exe"):
                    subprocess.run(["taskkill", "/F", "/IM", proc],
                                   capture_output=True, text=True, timeout=15)
        else:
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    continue
            time.sleep(0.5)
            after = is_app_running(name)
            if after.get("success") and after["result"]["running"]:
                for pid in after["result"]["pids"]:
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                    except (ProcessLookupError, PermissionError, OSError):
                        continue
    except Exception as exc:
        logger.exception("close_app failed for %s", name)
        return _fail(exc)
    time.sleep(0.5)
    after = is_app_running(name)
    still = bool(after.get("success") and after["result"]["running"])
    if still:
        return _fail(f"could not close {name}: still running (pids {after['result']['pids']})")
    return _ok({"app": str(name), "closed": True}, verified=True)
