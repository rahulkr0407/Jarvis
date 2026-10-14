"""Open a user-selected file with its default application.

This is the most *capable* action, so it is also the most tightly restricted:

* The path must resolve **inside a permitted directory** (``..`` and symlink
  escapes are rejected).
* Its extension must be on the safe-open allowlist. Executable and script types
  (``.exe``, ``.bat``, ``.cmd``, ``.ps1``, ``.lnk``, ``.scr``, ``.reg`` ...) can
  never be opened, because opening them would run code.
* The file must exist and be a regular file.

Two argument shapes are accepted: ``{"path": ...}`` for a file chosen in the UI,
or ``{"name": ..., "location": ...}`` for a single file named by text.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from actions.base import (
    ActionResult,
    ActionContext,
    ActionError,
    FileTypeNotAllowedError,
    PathNotPermittedError,
)
from actions.paths import find_permitted_root, resolve_within
from core.intents import validate_folder_name


def _resolve_target(
    context: ActionContext, arguments: Mapping[str, object]
) -> Path:
    if "path" in arguments and arguments.get("path"):
        return find_permitted_root(
            str(arguments["path"]), list(context.permitted_directories)
        )

    name = validate_folder_name(str(arguments.get("name", "")))
    if name is None:
        raise ActionError("That is not a valid file name.")
    location = str(arguments.get("location", ""))
    root = context.folder_map.get(location)
    if root is None:
        raise PathNotPermittedError(f"'{location}' is not a permitted location.")
    return resolve_within(root, name)


def _open_with_default_app(path: Path) -> None:
    """Ask the OS to open ``path``. Never builds a shell string."""
    startfile = getattr(os, "startfile", None)
    if startfile is not None:  # Windows
        startfile(str(path))
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"  # pragma: no cover
    subprocess.Popen([opener, str(path)], shell=False, close_fds=True)


def open_file(
    context: ActionContext, arguments: Mapping[str, object]
) -> ActionResult:
    """Open a permitted, non-executable file with its default application."""
    target = _resolve_target(context, arguments)

    extension = target.suffix.lower()
    if extension not in context.safe_extensions:
        raise FileTypeNotAllowedError(
            f"Files ending in '{extension or '(none)'}' are not allowed to open."
        )

    if not target.exists():
        raise ActionError(f"File '{target.name}' does not exist.")
    if not target.is_file():
        raise ActionError(f"'{target.name}' is not a regular file.")

    if context.dry_run:
        return ActionResult(True, f"DRY-RUN: would open file '{target.name}'.")

    try:
        _open_with_default_app(target)
    except OSError as exc:
        raise ActionError(f"Could not open '{target.name}': {exc}") from exc

    return ActionResult(True, f"Opened file '{target.name}'.")
