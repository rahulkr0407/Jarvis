"""A tiny, explicit state machine for the assistant.

Instead of sprinkling ``if state == ...`` checks everywhere, all legal moves are
declared once in :data:`TRANSITIONS`. A move that is not in the table raises
:class:`InvalidTransitionError`, so an illegal state can never be reached by
accident.

Legal moves:

    IDLE              -> LISTENING
    LISTENING         -> AWAITING_APPROVAL, IDLE
    AWAITING_APPROVAL -> EXECUTING, IDLE
    EXECUTING         -> IDLE

Returning to IDLE is allowed from every active state; that is how cancellation
and rejection work. There is no automatic path out of IDLE, which keeps the
assistant idle unless the user acts.
"""

from __future__ import annotations

from collections.abc import Mapping

from core.states import AssistantState


class InvalidTransitionError(RuntimeError):
    """Raised when a caller asks for a move the state machine forbids."""

    def __init__(self, source: AssistantState, target: AssistantState) -> None:
        super().__init__(
            f"Invalid transition: {source.name} -> {target.name}"
        )
        self.source = source
        self.target = target


#: The complete transition table. Read this as "from each state, you may go to
#: these states". frozenset makes the lookup order-independent.
TRANSITIONS: Mapping[AssistantState, frozenset[AssistantState]] = {
    AssistantState.IDLE: frozenset({AssistantState.LISTENING}),
    AssistantState.LISTENING: frozenset(
        {AssistantState.AWAITING_APPROVAL, AssistantState.IDLE}
    ),
    AssistantState.AWAITING_APPROVAL: frozenset(
        {AssistantState.EXECUTING, AssistantState.IDLE}
    ),
    AssistantState.EXECUTING: frozenset({AssistantState.IDLE}),
}


class AssistantStateMachine:
    """Holds the current state and enforces legal transitions."""

    def __init__(self, initial: AssistantState = AssistantState.IDLE) -> None:
        self._state = initial

    @property
    def state(self) -> AssistantState:
        """The current state (read-only)."""
        return self._state

    def can_transition(self, target: AssistantState) -> bool:
        """Return ``True`` if moving to ``target`` is currently legal."""
        return target in TRANSITIONS[self._state]

    def transition(self, target: AssistantState) -> AssistantState:
        """Move to ``target`` or raise :class:`InvalidTransitionError`."""
        if not self.can_transition(target):
            raise InvalidTransitionError(self._state, target)
        self._state = target
        return self._state
