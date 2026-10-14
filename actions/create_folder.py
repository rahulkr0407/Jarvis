"""Create a new folder inside a permitted location.

Only a single-segment name is accepted (validated again here, not just in the
router), and the target is resolved inside the permitted root before anything is
created. A name containing a separator or ``..`` can therefore never escape the
workspace.
"""

from __future__ import annotations

from collections.abc import Mapping

from actions.base import ActionResult, ActionContext, ActionError, PathNotPermittedError
from actions.paths import resolve_within
from core.intents import validate_folder_name


def create_folder(
    context: ActionContext, arguments: Mapping[str, object]
) -> ActionResult:
    """Create one folder under a permitted location."""
    name = validate_folder_name(str(arguments.get("name", "")))
    if name is None:
        raise ActionError("That is not a valid folder name.")

    location = str(arguments.get("location", ""))
    root = context.folder_map.get(location)
    if root is None:
        raise PathNotPermittedError(f"'{location}' is not a permitted location.")

    target = resolve_within(root, name)

    if target.exists():
        if target.is_dir():
            return ActionResult(
                False, f"Folder '{name}' already exists in {location}."
            )
        raise ActionError(f"A file named '{name}' already exists in {location}.")

    if context.dry_run:
        return ActionResult(
            True, f"DRY-RUN: would create folder '{name}' in {location}."
        )

    try:
        root.mkdir(parents=True, exist_ok=True)
        target.mkdir(parents=False, exist_ok=False)
    except FileExistsError:
        return ActionResult(
            False, f"Folder '{name}' already exists in {location}."
        )
    except OSError as exc:
        raise ActionError(f"Could not create folder '{name}': {exc}") from exc

    return ActionResult(True, f"Created folder '{name}' in {location}.")
