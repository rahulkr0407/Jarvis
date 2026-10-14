"""Action declarations and the explicit allowlist registry.

An :class:`ActionSpec` describes one action JARVIS is permitted to *propose*.
Phase 1 ships no implementations: ``handler`` is always ``None``. The field
exists so a later phase can attach a reviewed callable without changing the
policy or the controller.

There is deliberately no way to register a raw shell command or AI-generated
code here. If an action is not registered under its exact name, it is unknown,
and unknown actions are refused.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ActionSpec:
    """One allowlisted action.

    Attributes:
        name: The exact identifier the policy matches against.
        description: Human-readable summary, shown to the user.
        handler: The callable that performs the action. ``None`` in Phase 1
            because no real computer-control actions are implemented yet.
    """

    name: str
    description: str
    handler: Callable[..., object] | None = None


class ActionRegistry:
    """An explicit, closed set of known actions.

    Lookups are exact-match and read-only from the outside. Registering the same
    name twice overwrites the previous spec, which keeps the registry
    deterministic during construction.
    """

    def __init__(self, specs: Iterable[ActionSpec] = ()) -> None:
        self._specs: dict[str, ActionSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: ActionSpec) -> None:
        """Add (or replace) a single action specification."""
        self._specs[spec.name] = spec

    def is_registered(self, name: str) -> bool:
        """Return ``True`` only if ``name`` is an exact allowlist member."""
        return name in self._specs

    def get(self, name: str) -> ActionSpec | None:
        """Return the spec for ``name`` or ``None`` if it is unknown."""
        return self._specs.get(name)

    def names(self) -> tuple[str, ...]:
        """Return the registered action names in insertion order."""
        return tuple(self._specs)
