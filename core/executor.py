"""Plan executor for NOOBRA.

Runs a :class:`~core.planner.Plan` step by step against a tool registry:

* classifies every step via :mod:`core.permissions` and enforces
  approval (callback when provided; otherwise DANGEROUS is skipped and
  CAUTION runs only when the step was pre-approved),
* retries a failed step once -- SAFE tools only, never delete / submit /
  send / purchase,
* respects a ``threading.Event`` cancellation flag between steps,
* optionally verifies each step's result.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger("noobra.core.executor")

# Tool names that must never be retried, even if they look SAFE.
_NO_RETRY_TOOLS = {
    "delete_file", "delete_folder", "submit_form", "send_email",
    "send_message", "purchase", "install_software", "run_admin_command",
}


class Executor:
    """Executes plans against a tool registry."""

    def __init__(self, tool_registry: dict | None = None, approval_callback=None):
        self._registry = tool_registry  # may be None -> lazy import
        self.approval_callback = approval_callback

    # -- registry ---------------------------------------------------------
    def _get_registry(self) -> dict:
        if self._registry is not None:
            return self._registry
        try:
            try:
                from tools import get_tool_registry
            except ImportError:
                from ..tools import get_tool_registry  # type: ignore[import]
            registry = get_tool_registry()
            self._registry = dict(registry) if isinstance(registry, dict) else {}
        except Exception as exc:
            logger.warning("Could not load tool registry; running with no tools: %s", exc)
            self._registry = {}
        return self._registry

    # -- execution --------------------------------------------------------
    def execute(self, plan, context=None, progress_callback=None, cancel_event=None) -> dict:
        """Execute ``plan`` and return ``{success, results, message}``.

        ``results`` is a list of ``{step, success, result, error, verified}``
        dicts, one per step. ``cancel_event`` is a ``threading.Event``;
        when set, remaining steps are skipped.
        """
        results: list[dict] = []
        steps = list(getattr(plan, "steps", None) or [])
        total = len(steps)
        if total == 0:
            message = "Nothing to do."
            if getattr(plan, "clarification_needed", False):
                message = getattr(plan, "clarification_question", None) or message
            return {"success": False, "results": results, "message": message}

        registry = self._get_registry()
        cancelled = False
        for index, step in enumerate(steps):
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                results.append(self._result(step, False, None, "Cancelled by user", False))
                break
            self._notify(progress_callback, index, total, step, "started")
            step_result = self._run_step(step, registry, context)
            results.append(step_result)
            self._notify(progress_callback, index, total, step,
                         "done" if step_result["success"] else "failed")
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break

        succeeded = sum(1 for r in results if r["success"])
        success = bool(results) and succeeded == len(results) and not cancelled
        if cancelled:
            message = f"Cancelled after {succeeded}/{total} step(s) completed."
        elif success:
            message = f"All {total} step(s) completed successfully."
        else:
            message = f"{succeeded}/{total} step(s) completed; {total - succeeded} failed."
        return {"success": success, "results": results, "message": message}

    # -- one step ---------------------------------------------------------
    def _run_step(self, step, registry, context):
        tool_name = str(getattr(step, "tool", "") or "").strip()
        args = dict(getattr(step, "args", None) or {})
        if not tool_name:
            return self._result(step, False, None, "Plan step has no tool name", False)

        # Permission check, before anything runs.
        try:
            try:
                from core.permissions import classify_tool, requires_approval
            except ImportError:
                from .permissions import classify_tool, requires_approval
            level = classify_tool(tool_name, args)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Permission classification failed for %s: %s", tool_name, exc)
            return self._result(step, False, None, f"Permission check failed: {exc}", False)

        if requires_approval(level):
            approved = self._check_approval(step, level)
            if not approved:
                reason = (
                    f"Skipped: '{tool_name}' is {level.value} and needs confirmation"
                    if self.approval_callback is None
                    else f"Skipped: approval denied for '{tool_name}' ({level.value})"
                )
                logger.info("%s", reason)
                return self._result(step, False, None, reason, False)

        handler = registry.get(tool_name)
        if handler is None:
            error = f"Tool '{tool_name}' is not available"
            logger.warning("%s", error)
            return self._result(step, False, None, error, False)

        # Retry once for SAFE tools only; never for destructive/send tools.
        attempts = 2 if level.value == "safe" and tool_name not in _NO_RETRY_TOOLS else 1
        last_error = None
        for attempt in range(attempts):
            try:
                raw = self._call_tool(handler, tool_name, args)
                success, value, error = self._interpret_result(raw)
                verified = self._verify(step, success, value)
                if success:
                    if context is not None:
                        self._remember_path(step, context)
                        try:
                            context.add_tool_result(tool_name, value, success=True)
                        except Exception:
                            pass
                    return self._result(step, True, value, error, verified)
                last_error = error or f"Tool '{tool_name}' reported failure"
                logger.warning("Tool %s failed (attempt %d/%d): %s",
                               tool_name, attempt + 1, attempts, last_error)
            except Exception as exc:
                last_error = str(exc)
                logger.warning("Tool %s raised (attempt %d/%d): %s",
                               tool_name, attempt + 1, attempts, exc)
        return self._result(step, False, None, last_error or "Tool failed", False)

    def _check_approval(self, step, level) -> bool:
        """Return True when a CAUTION/DANGEROUS step may run."""
        if self.approval_callback is not None:
            try:
                return bool(self.approval_callback(step, level))
            except Exception as exc:
                logger.warning("Approval callback failed; treating as denied: %s", exc)
                return False
        if level.value == "dangerous":
            return False  # never run dangerous tools without confirmation
        # CAUTION with no callback: run only when the step was pre-approved.
        return bool(getattr(step, "approved", False) or (getattr(step, "args", None) or {}).get("approved"))

    @staticmethod
    def _call_tool(handler, tool_name, args):
        """Call a registry entry, whatever shape it has."""
        target = handler
        if isinstance(handler, dict):
            target = handler.get("function") or handler.get("handler") or handler.get("callable")
        if target is None and hasattr(handler, "execute"):
            target = handler.execute
        if target is None and hasattr(handler, "run"):
            target = handler.run
        if not callable(target):
            raise TypeError(f"Tool '{tool_name}' has no callable handler")
        try:
            return target(**args)
        except TypeError:
            # Some tools take a single args dict, or no arguments at all.
            try:
                return target(args)
            except TypeError:
                return target()

    @staticmethod
    def _interpret_result(raw):
        """Normalise a tool's return value to (success, value, error)."""
        if isinstance(raw, dict):
            success = raw.get("success", True)
            if "error" in raw and raw.get("error"):
                success = False
            error = raw.get("error") or raw.get("message") if not success else None
            value = raw.get("result", raw.get("data", raw))
            return bool(success), value, (str(error) if error else None)
        if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[0], bool):
            return raw[0], raw[1], None if raw[0] else str(raw[1])
        return True, raw, None

    @staticmethod
    def _verify(step, success, value) -> bool:
        """Check a step's ``verify`` requirement against its result."""
        if not getattr(step, "verify", None):
            return bool(success)
        if not success:
            return False
        if isinstance(value, dict):
            if "verified" in value:
                return bool(value["verified"])
            if "success" in value:
                return bool(value["success"])
        return True

    @staticmethod
    def _result(step, success, result, error, verified) -> dict:
        return {
            "step": step,
            "success": bool(success),
            "result": result,
            "error": error,
            "verified": bool(verified),
        }

    @staticmethod
    def _notify(progress_callback, index, total, step, status) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(index, total, step, status)
        except TypeError:
            try:
                progress_callback(index, total, step)
            except Exception as exc:
                logger.debug("Progress callback failed: %s", exc)
        except Exception as exc:
            logger.debug("Progress callback failed: %s", exc)

    @staticmethod
    def _remember_path(step, context) -> None:
        """Remember a path a successful step produced / touched."""
        args = getattr(step, "args", None) or {}
        path = args.get("path") or args.get("destination") or args.get("source")
        if path:
            try:
                context.set_last_path(str(path))
            except Exception:
                pass


def new_cancel_event() -> threading.Event:
    """Convenience helper: create a fresh cancellation event."""
    return threading.Event()
