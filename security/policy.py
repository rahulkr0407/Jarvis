"""The action policy: deny by default.

:class:`ActionPolicy` is the single authority on whether an action name is
permitted. It answers only yes/no; it never performs an action. The rule is
simple and strict: if the name is not registered in the allowlist, it is denied.

``build_default_policy`` wires the policy to the names declared in
``config.settings.ALLOWED_ACTIONS`` so there is exactly one place to review
which capabilities exist.
"""

from __future__ import annotations

from config import settings
from security.actions import ActionRegistry, ActionSpec


class PolicyViolation(PermissionError):
    """Raised when an action is requested that the policy does not allow."""

    def __init__(self, action_name: str) -> None:
        super().__init__(
            f"Action '{action_name}' is not permitted by the policy."
        )
        self.action_name = action_name


class ActionPolicy:
    """Answers whether a proposed action is allowed. Deny-by-default."""

    def __init__(self, registry: ActionRegistry) -> None:
        self._registry = registry

    def is_allowed(self, action_name: str) -> bool:
        """Return ``True`` only for exact allowlist members."""
        return self._registry.is_registered(action_name)

    def require_allowed(self, action_name: str) -> None:
        """Raise :class:`PolicyViolation` unless ``action_name`` is allowed."""
        if not self.is_allowed(action_name):
            raise PolicyViolation(action_name)

    def allowed_actions(self) -> tuple[str, ...]:
        """Return the names currently permitted by this policy."""
        return self._registry.names()


def build_default_policy() -> ActionPolicy:
    """Build the policy from ``config.settings.ALLOWED_ACTIONS``.

    Each name is registered with a human-readable description. Handlers are not
    attached here: execution is dispatched separately by
    :func:`actions.registry.build_executor`, so the policy stays a pure
    allowlist that never performs an action itself.
    """
    specs = [
        ActionSpec(
            name=name,
            description=settings.ACTION_DESCRIPTIONS.get(
                name, "Allowlisted action."
            ),
        )
        for name in settings.ALLOWED_ACTIONS
    ]
    return ActionPolicy(ActionRegistry(specs))
