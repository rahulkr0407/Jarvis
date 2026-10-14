"""Open an application that is on the configured allowlist.

Safety notes:

* The application is looked up in ``context.application_allowlist`` by exact
  name, so only applications a human put there can ever launch. Anything else is
  refused before a process is created.
* Launching uses :func:`subprocess.Popen` with an **explicit argument list** and
  ``shell=False``. No shell string is ever built, and nothing here can be
  influenced by a model — a transcript only ever selects an allowlisted key.
* The executable is resolved to a real file first; a bare name is looked up with
  :func:`shutil.which` (documented as a residual risk in the README).
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from actions.base import ActionResult, ActionContext, AppNotAllowedError


def _normalize_key(target: str) -> str:
    key = (target or "").strip().lower()
    if key.endswith(".exe"):
        key = key[:-4]
    return key


def _lookup_argv(context: ActionContext, target: str) -> Sequence[str]:
    key = _normalize_key(target)
    argv = context.application_allowlist.get(key)
    if not argv:
        raise AppNotAllowedError(
            f"Application '{target}' is not in the allowlist."
        )
    return argv


def _resolve_executable(name: str) -> Path:
    candidate = Path(name)
    if candidate.is_absolute() or candidate.parent != Path("."):
        resolved = candidate.resolve()
        if not resolved.exists():
            raise AppNotAllowedError(
                f"Application '{name}' was not found at that path."
            )
        return resolved
    found = shutil.which(name)
    if found is None:
        raise AppNotAllowedError(
            f"Application '{name}' was not found on PATH."
        )
    return Path(found)


def open_application(
    context: ActionContext, arguments: Mapping[str, object]
) -> ActionResult:
    """Launch an allowlisted application. Returns the new process id."""
    target = str(arguments.get("target", ""))
    argv = list(_lookup_argv(context, target))
    executable = _resolve_executable(argv[0])
    argv[0] = str(executable)

    if context.dry_run:
        return ActionResult(
            True, f"DRY-RUN: would launch '{target}' ({executable.name})."
        )

    try:
        process = subprocess.Popen(argv, shell=False, close_fds=True)
    except OSError as exc:
        raise AppNotAllowedError(f"Could not launch '{target}': {exc}") from exc

    return ActionResult(True, f"Launched '{target}' (pid {process.pid}).")
