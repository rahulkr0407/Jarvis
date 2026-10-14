"""The assistant controller: the only place the states actually move.

The controller ties together three things that must never be bypassed:

1. The :class:`~core.state_machine.AssistantStateMachine` (legal moves only).
2. The :class:`~security.policy.ActionPolicy` (deny-by-default allowlist).
3. :class:`~security.approval.ApprovalRequest` (exact-action, expiring approval).

Key safety properties implemented here:

* The assistant starts and stays IDLE until :meth:`AssistantController.activate`
  is called explicitly.
* An action is proposed **only** from LISTENING and only if the policy allows
  the exact name. The proposal carries the exact arguments.
* Execution happens **only** after the matching, non-expired approval is
  approved. A stale token, a missing proposal, or an expired one is refused.
* :meth:`AssistantController.cancel` clears any pending proposal and returns to
  IDLE, so a not-yet-started action can never run.
* Phase 1 has no real actions. The default executor refuses everything, so even
  an approved action reports "not implemented" rather than a false success.

The controller has **no** Qt dependency and takes an injectable clock and
executor, which makes every path above unit-testable.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from config import settings
from core.state_machine import AssistantStateMachine, InvalidTransitionError
from core.states import AssistantState
from security.approval import ApprovalRequest, create_approval
from security.policy import ActionPolicy, PolicyViolation

# A listener receives ``(event_name, payload_dict)``. The UI subscribes to turn
# these notifications into on-screen updates.
Listener = Callable[[str, Mapping[str, object]], None]


class AssistantError(RuntimeError):
    """Base class for controller-level errors."""


class ApprovalError(AssistantError):
    """Base class for problems in the approval flow."""


class NoPendingApprovalError(ApprovalError):
    """Raised when an approval is attempted but nothing is pending."""


class StaleApprovalError(ApprovalError):
    """Raised when a token does not match the current pending proposal."""


class ApprovalExpiredError(ApprovalError):
    """Raised when the pending proposal has passed its deadline."""


class ActionNotImplementedError(AssistantError):
    """Raised by the default executor: Phase 1 ships no real actions."""


@dataclass(frozen=True)
class ExecutionOutcome:
    """The honest result of an execution attempt.

    ``succeeded`` is ``True`` only when the executor completed with no error.
    The UI must display this value rather than assume success.
    """

    action_name: str
    started: bool
    succeeded: bool
    detail: str


def refusing_executor(action_name: str, arguments: Mapping[str, object]) -> object:
    """Default executor for Phase 1: refuse to do anything.

    Approving an action still exercises the full state flow, but because no
    handler exists the assistant reports "not implemented" instead of a false
    success.
    """
    raise ActionNotImplementedError(
        f"Action '{action_name}' is not implemented in Phase 1."
    )


class AssistantController:
    """Drives the assistant state machine. IDLE until activated."""

    def __init__(
        self,
        policy: ActionPolicy,
        *,
        executor: Callable[[str, Mapping[str, object]], object] | None = None,
        clock: Callable[[], float] = time.monotonic,
        approval_timeout: float = settings.APPROVAL_TIMEOUT_SECONDS,
    ) -> None:
        self._machine = AssistantStateMachine(AssistantState.IDLE)
        self._policy = policy
        self._executor = executor or refusing_executor
        self._clock = clock
        self._approval_timeout = approval_timeout
        self._pending: ApprovalRequest | None = None
        self._cancel_requested = False
        self._last_outcome: ExecutionOutcome | None = None
        self._listeners: list[Listener] = []

    # ------------------------------------------------------------------ #
    # Observers
    # ------------------------------------------------------------------ #
    def add_listener(self, listener: Listener) -> None:
        """Register a callback for state changes and lifecycle events."""
        self._listeners.append(listener)

    def _notify(self, event: str, payload: Mapping[str, object]) -> None:
        """Notify listeners, isolating them from each other's failures."""
        for listener in list(self._listeners):
            try:
                listener(event, payload)
            except Exception:  # a broken listener must not break the assistant
                pass

    def _transition_to(self, target: AssistantState) -> AssistantState:
        """Perform a transition and announce it. Raises if illegal."""
        previous = self._machine.state
        new_state = self._machine.transition(target)
        self._notify(
            "state_changed", {"previous": previous, "current": new_state}
        )
        return new_state

    # ------------------------------------------------------------------ #
    # Read-only views
    # ------------------------------------------------------------------ #
    @property
    def state(self) -> AssistantState:
        """The current assistant state."""
        return self._machine.state

    @property
    def pending_approval(self) -> ApprovalRequest | None:
        """The current proposal, or ``None``. Expires lazily on access."""
        self._expire_if_needed(self._clock())
        return self._pending

    @property
    def last_outcome(self) -> ExecutionOutcome | None:
        """The most recent execution outcome, if any."""
        return self._last_outcome

    # ------------------------------------------------------------------ #
    # Activation
    # ------------------------------------------------------------------ #
    def activate(self) -> AssistantState:
        """Explicitly begin listening. This is the only way out of IDLE."""
        self._cancel_requested = False
        return self._transition_to(AssistantState.LISTENING)

    # ------------------------------------------------------------------ #
    # Proposing an action
    # ------------------------------------------------------------------ #
    def propose_action(
        self,
        action_name: str,
        arguments: Mapping[str, object] | None = None,
    ) -> ApprovalRequest:
        """Propose one action for approval. Policy-checked and exact.

        Raises:
            InvalidTransitionError: if not currently LISTENING.
            PolicyViolation: if ``action_name`` is not allowlisted.
        """
        if self.state is not AssistantState.LISTENING:
            raise InvalidTransitionError(
                self.state, AssistantState.AWAITING_APPROVAL
            )

        arguments = dict(arguments or {})
        if not self._policy.is_allowed(action_name):
            raise PolicyViolation(action_name)

        approval = create_approval(
            action_name,
            arguments,
            now=self._clock(),
            ttl=self._approval_timeout,
        )
        self._pending = approval
        self._transition_to(AssistantState.AWAITING_APPROVAL)
        self._notify("action_proposed", {"approval": approval})
        return approval

    # ------------------------------------------------------------------ #
    # Approval flow
    # ------------------------------------------------------------------ #
    def approve(self, token: str | None = None) -> ExecutionOutcome:
        """Approve the pending action and run it.

        ``token`` binds the approval to one exact proposal. Passing a token that
        does not match the current proposal is refused as stale, so an old
        approval can never execute a newer, different action.
        """
        if self.state is not AssistantState.AWAITING_APPROVAL or self._pending is None:
            raise NoPendingApprovalError("No action is awaiting approval.")

        pending = self._pending

        if token is not None and token != pending.token:
            raise StaleApprovalError(
                "This approval does not match the pending action."
            )

        if pending.is_expired(self._clock()):
            self._discard_pending()
            self._transition_to(AssistantState.IDLE)
            self._notify("approval_expired", {})
            raise ApprovalExpiredError("The approval request has expired.")

        # Defence in depth: re-check the policy right before running.
        if not self._policy.is_allowed(pending.action_name):
            self._discard_pending()
            self._transition_to(AssistantState.IDLE)
            raise PolicyViolation(pending.action_name)

        return self._execute(pending)

    def reject(self) -> AssistantState:
        """Reject the pending action and return to IDLE."""
        if self.state is not AssistantState.AWAITING_APPROVAL:
            raise NoPendingApprovalError("No action is awaiting approval.")
        self._discard_pending()
        new_state = self._transition_to(AssistantState.IDLE)
        self._notify("approval_rejected", {})
        return new_state

    # ------------------------------------------------------------------ #
    # Cancellation
    # ------------------------------------------------------------------ #
    def cancel(self) -> AssistantState:
        """Stop everything and return to IDLE.

        Clears any pending proposal first, which guarantees a not-yet-started
        action cannot execute afterwards. Safe to call from any state.
        """
        self._cancel_requested = True
        self._discard_pending()
        if self.state is not AssistantState.IDLE:
            self._transition_to(AssistantState.IDLE)
        self._notify("cancelled", {})
        return self.state

    # ------------------------------------------------------------------ #
    # Timeout handling
    # ------------------------------------------------------------------ #
    def check_timeout(self, now: float | None = None) -> bool:
        """Expire a pending proposal if its deadline passed.

        Intended to be called periodically (e.g. from a UI timer). Returns
        ``True`` if a proposal was expired by this call.
        """
        return self._expire_if_needed(self._clock() if now is None else now)

    def _expire_if_needed(self, now: float) -> bool:
        if self._pending is not None and self._pending.is_expired(now):
            self._discard_pending()
            if self.state is AssistantState.AWAITING_APPROVAL:
                self._transition_to(AssistantState.IDLE)
            self._notify("approval_expired", {})
            return True
        return False

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _discard_pending(self) -> None:
        self._pending = None

    def _execute(self, pending: ApprovalRequest) -> ExecutionOutcome:
        """Run one approved action, then always return to IDLE."""
        action_name = pending.action_name
        arguments = pending.arguments
        # The action is now in flight; it is no longer a *pending* proposal.
        self._discard_pending()

        self._transition_to(AssistantState.EXECUTING)
        self._notify("action_started", {"action_name": action_name})

        if self._cancel_requested:
            # A cancel arrived before the action actually started: don't run it.
            self._cancel_requested = False
            outcome = ExecutionOutcome(
                action_name=action_name,
                started=False,
                succeeded=False,
                detail="Cancelled before the action started.",
            )
            self._last_outcome = outcome
            self._transition_to(AssistantState.IDLE)
            self._notify("action_finished", {"outcome": outcome})
            return outcome

        try:
            self._executor(action_name, arguments)
        except ActionNotImplementedError as exc:
            outcome = ExecutionOutcome(
                action_name=action_name,
                started=True,
                succeeded=False,
                detail=str(exc),
            )
        except Exception as exc:  # never let an executor crash the UI
            outcome = ExecutionOutcome(
                action_name=action_name,
                started=True,
                succeeded=False,
                detail=f"Execution failed: {exc}",
            )
        else:
            outcome = ExecutionOutcome(
                action_name=action_name,
                started=True,
                succeeded=True,
                detail="Completed.",
            )

        self._last_outcome = outcome
        self._transition_to(AssistantState.IDLE)
        self._notify("action_finished", {"outcome": outcome})
        return outcome
