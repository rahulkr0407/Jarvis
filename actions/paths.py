"""Path confinement helpers.

The single rule enforced here: a path an action wants to use must resolve to a
location **inside** one of the configured permitted roots. Resolution follows
symlinks first, so a link that points outside the workspace is rejected exactly
like a ``..`` traversal would be.
"""

from __future__ import annotations

from pathlib import Path

from actions.base import PathNotPermittedError


def resolve_within(root: Path | str, candidate: Path | str) -> Path:
    """Resolve ``candidate`` relative to ``root`` and require it to stay inside.

    ``candidate`` may be absolute or relative. Raises
    :class:`PathNotPermittedError` if the resolved path escapes ``root``.
    """
    root_resolved = Path(root).resolve()
    candidate_path = Path(candidate)
    if candidate_path.is_absolute():
        resolved = candidate_path.resolve()
    else:
        resolved = (root_resolved / candidate_path).resolve()

    if not resolved.is_relative_to(root_resolved):
        raise PathNotPermittedError(
            f"Path '{candidate}' is outside the permitted area."
        )
    return resolved


def find_permitted_root(
    candidate: Path | str, roots: tuple[Path, ...] | list[Path]
) -> Path:
    """Return the resolved ``candidate`` if it lies under any permitted root.

    Used for paths that arrive directly (for example a file chosen in the UI)
    rather than relative to a named folder. Raises
    :class:`PathNotPermittedError` when no permitted root contains it.
    """
    resolved = Path(candidate).resolve()
    for root in roots:
        root_resolved = Path(root).resolve()
        if resolved.is_relative_to(root_resolved):
            return resolved
    raise PathNotPermittedError(
        f"Path '{candidate}' is outside the permitted area."
    )
