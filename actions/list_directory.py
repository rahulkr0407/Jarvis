"""List the contents of a permitted directory.

The location word (``home``, ``documents``, ...) is resolved through
:attr:`ActionContext.folder_map`, so it can never name an arbitrary path. The
result is bounded by :attr:`ActionContext.max_directory_entries` so a huge
directory cannot flood the UI.
"""

from __future__ import annotations

from collections.abc import Mapping

from actions.base import ActionResult, ActionContext, ActionError, PathNotPermittedError
from actions.paths import resolve_within


def list_directory(
    context: ActionContext, arguments: Mapping[str, object]
) -> ActionResult:
    """Read the entries of a permitted directory (names only)."""
    location = str(arguments.get("location", ""))
    root = context.folder_map.get(location)
    if root is None:
        raise PathNotPermittedError(f"'{location}' is not a permitted location.")

    target = resolve_within(root, ".")
    if not target.exists():
        raise ActionError(f"Directory '{location}' does not exist.")
    if not target.is_dir():
        raise ActionError(f"'{location}' is not a directory.")

    if context.dry_run:
        return ActionResult(True, f"DRY-RUN: would list {location} ({target}).")

    entries = sorted(target.iterdir(), key=lambda entry: entry.name.lower())
    total = len(entries)
    shown = entries[: context.max_directory_entries]
    names = ", ".join(
        f"{entry.name}{'/' if entry.is_dir() else ''}" for entry in shown
    )

    noun = "entry" if total == 1 else "entries"
    if total == 0:
        return ActionResult(True, f"{location} is empty.")
    if total > len(shown):
        return ActionResult(
            True,
            f"{total} {noun} in {location} (showing first {len(shown)}): {names}",
        )
    return ActionResult(True, f"{total} {noun} in {location}: {names}")
