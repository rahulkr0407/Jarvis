"""The action dispatcher: the only place actions are actually invoked.

:func:`build_executor` returns the callable the controller runs after approval.
It owns three cross-cutting concerns so the individual action modules stay small:

* **Dispatch** — an exact name-to-handler map. A name with no handler is reported
  as "not implemented" rather than silently ignored.
* **Timeouts** — every handler runs on a short-lived daemon thread and is given a
  hard deadline. A handler that overruns yields a clear timeout result instead of
  freezing the assistant; the timeout cannot force-kill arbitrary OS work, which
  is documented as a limitation.
* **Auditing** — every attempt is written to the audit log with scrubbed
  arguments.

Expected failures are returned as a failed :class:`ActionResult` (not raised) so
the UI can show a clean message. Only an action with no handler raises, which the
controller already renders as "not implemented".
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping

from actions.base import (
    ActionResult,
    ActionContext,
    ActionError,
    ExecutionTimeoutError,
)
from actions.create_folder import create_folder
from actions.list_directory import list_directory
from actions.open_application import open_application
from actions.open_file import open_file
from actions.open_url import open_url
from core.controller import ActionNotImplementedError

Handler = Callable[[ActionContext, Mapping[str, object]], ActionResult]

#: The complete set of implemented actions. Anything not here is "not implemented".
ACTION_HANDLERS: dict[str, Handler] = {
    "open_application": open_application,
    "open_url": open_url,
    "list_directory": list_directory,
    "create_folder": create_folder,
    "open_file": open_file,
}


def _audit(
    context: ActionContext,
    action_name: str,
    arguments: Mapping[str, object],
    *,
    succeeded: bool,
    detail: str,
) -> None:
    try:
        context.audit.record(
            action_name,
            arguments,
            succeeded=succeeded,
            detail=detail,
            dry_run=context.dry_run,
        )
    except Exception:
        # A misbehaving audit logger must never break an action.
        pass


def _run_with_timeout(
    handler: Handler, context: ActionContext, arguments: Mapping[str, object]
) -> ActionResult:
    timeout = context.timeout_seconds
    if not timeout or timeout <= 0:
        return handler(context, arguments)

    box: dict[str, object] = {}

    def target() -> None:
        try:
            box["result"] = handler(context, arguments)
        except BaseException as exc:  # re-raised on the caller's thread below
            box["error"] = exc

    thread = threading.Thread(target=target, name="jarvis-action", daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        raise ExecutionTimeoutError(
            f"Action exceeded the {timeout:g}s time limit."
        )
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    result = box.get("result")
    if isinstance(result, ActionResult):
        return result
    return ActionResult(True, str(result) if result else "Completed.")


def build_executor(
    context: ActionContext,
) -> Callable[[str, Mapping[str, object]], ActionResult]:
    """Return the executor callable for the given action context."""

    def executor(
        action_name: str, arguments: Mapping[str, object]
    ) -> ActionResult:
        handler = ACTION_HANDLERS.get(action_name)
        if handler is None:
            detail = f"Action '{action_name}' is not implemented."
            _audit(context, action_name, arguments, succeeded=False, detail=detail)
            raise ActionNotImplementedError(detail)

        try:
            result = _run_with_timeout(handler, context, arguments)
        except ActionError as exc:
            detail = str(exc)
            _audit(context, action_name, arguments, succeeded=False, detail=detail)
            return ActionResult(False, detail)
        except Exception as exc:
            detail = f"Action failed: {exc}"
            _audit(context, action_name, arguments, succeeded=False, detail=detail)
            return ActionResult(False, detail)

        _audit(
            context,
            action_name,
            arguments,
            succeeded=result.succeeded,
            detail=result.detail,
        )
        return result

    return executor
