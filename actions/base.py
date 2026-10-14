"""Shared types for the permission-controlled action layer.

An :class:`ActionContext` carries everything an action needs to do its job
safely and testably: the directories it may touch, the application allowlist,
the safe file extensions, a timeout, whether it is a dry run, and an audit
logger. Nothing in the context grants a capability on its own — the controller
still requires an exact-match approval before any handler runs.

A handler has the signature ``handler(context, arguments) -> ActionResult`` and
must never call ``shell=True``, never execute text produced by a model, and never
write outside ``context.permitted_directories``.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from actions.audit import AuditLogger, FileAuditLogger, NullAuditLogger
from config import settings


@dataclass(frozen=True)
class ActionResult:
    """The honest result of one action.

    ``succeeded`` is ``True`` only when the action actually completed. The
    controller displays ``detail`` verbatim instead of assuming success.
    """

    succeeded: bool
    detail: str


class ActionError(RuntimeError):
    """Base class for a refusal or a known failure inside an action."""


class PathNotPermittedError(ActionError):
    """Raised when a path resolves outside the permitted workspace."""


class AppNotAllowedError(ActionError):
    """Raised when an application is not in the configured allowlist."""


class UrlNotAllowedError(ActionError):
    """Raised when a URL is malformed or uses a non-http(s) scheme."""


class FileTypeNotAllowedError(ActionError):
    """Raised when a file's extension is not on the safe-open list."""


class ExecutionTimeoutError(ActionError):
    """Raised when an action exceeds its execution time budget."""


@dataclass(frozen=True)
class ActionContext:
    """Everything an action needs, injected so actions stay testable.

    All directories are already resolved. ``dry_run`` makes every action report
    what it *would* do without touching the filesystem or launching anything.
    """

    permitted_directories: tuple[Path, ...]
    folder_map: Mapping[str, Path]
    application_allowlist: Mapping[str, Sequence[str]]
    safe_extensions: frozenset[str]
    timeout_seconds: float
    max_directory_entries: int
    dry_run: bool = False
    audit: AuditLogger = field(default_factory=NullAuditLogger)
    clock: Callable[[], float] = time.time


def build_action_context(
    *,
    dry_run: bool | None = None,
    audit: AuditLogger | None = None,
    clock: Callable[[], float] = time.time,
) -> ActionContext:
    """Build the default context from :mod:`config.settings`.

    The workspace is a project-local sandbox; every location word maps to a
    sub-directory inside it, so the assistant can never reach a real user folder
    unless the configuration is deliberately changed.
    """
    workspace = Path(settings.WORKSPACE_ROOT)
    if not workspace.is_absolute():
        workspace = settings.PROJECT_ROOT / workspace

    folder_map = {
        name: (workspace / relative).resolve()
        for name, relative in settings.FOLDER_MAP.items()
    }
    permitted = tuple(dict.fromkeys(folder_map.values()))

    if audit is None:
        audit_path = Path(settings.AUDIT_LOG_PATH)
        if not audit_path.is_absolute():
            audit_path = settings.PROJECT_ROOT / audit_path
        audit = FileAuditLogger(audit_path, clock=clock)

    return ActionContext(
        permitted_directories=permitted,
        folder_map=folder_map,
        application_allowlist={
            key: tuple(value)
            for key, value in settings.APPLICATION_ALLOWLIST.items()
        },
        safe_extensions=frozenset(
            ext.lower() for ext in settings.SAFE_OPEN_EXTENSIONS
        ),
        timeout_seconds=settings.EXECUTION_TIMEOUT_SECONDS,
        max_directory_entries=settings.MAX_DIRECTORY_ENTRIES,
        dry_run=settings.DRY_RUN if dry_run is None else dry_run,
        audit=audit,
        clock=clock,
    )
