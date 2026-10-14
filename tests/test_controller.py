"""End-to-end tests for the controller: transitions, policy, approval, cancel."""

from __future__ import annotations

import pytest

from core.controller import (
    ApprovalExpiredError,
    AssistantController,
    NoPendingApprovalError,
    StaleApprovalError,
)
from core.state_machine import InvalidTransitionError
from core.states import AssistantState
from security.policy import PolicyViolation, build_default_policy


class FakeClock:
    """A controllable clock so timeout tests are instant and deterministic."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, delta: float) -> None:
        self.now += delta


def make_controller(**kwargs) -> AssistantController:
    return AssistantController(build_default_policy(), **kwargs)


# --------------------------------------------------------------------------- #
# Activation
# --------------------------------------------------------------------------- #
def test_starts_idle_and_has_no_pending_action():
    controller = make_controller()
    assert controller.state is AssistantState.IDLE
    assert controller.pending_approval is None


def test_activate_moves_to_listening():
    controller = make_controller()
    assert controller.activate() is AssistantState.LISTENING


def test_cannot_activate_twice():
    controller = make_controller()
    controller.activate()
    with pytest.raises(InvalidTransitionError):
        controller.activate()


# --------------------------------------------------------------------------- #
# Proposing
# --------------------------------------------------------------------------- #
def test_propose_requires_listening():
    controller = make_controller()
    with pytest.raises(InvalidTransitionError):
        controller.propose_action("open_application")


def test_propose_allowed_action_awaits_approval():
    controller = make_controller()
    controller.activate()
    approval = controller.propose_action("open_application", {"target": "notepad"})
    assert controller.state is AssistantState.AWAITING_APPROVAL
    assert controller.pending_approval is approval
    assert approval.arguments["target"] == "notepad"


def test_propose_unknown_action_denied_and_state_unchanged():
    controller = make_controller()
    controller.activate()
    with pytest.raises(PolicyViolation):
        controller.propose_action("run_shell", {"cmd": "format c:"})
    assert controller.state is AssistantState.LISTENING
    assert controller.pending_approval is None


# --------------------------------------------------------------------------- #
# Approval / execution
# --------------------------------------------------------------------------- #
def test_default_executor_reports_not_implemented_not_success():
    controller = make_controller()
    controller.activate()
    controller.propose_action("open_application", {"target": "notepad"})
    outcome = controller.approve()
    assert outcome.started is True
    assert outcome.succeeded is False
    assert "not implemented" in outcome.detail.lower()
    assert controller.state is AssistantState.IDLE


def test_custom_executor_receives_exact_action_and_arguments():
    calls: list[tuple[str, dict]] = []

    def executor(name: str, arguments) -> str:
        calls.append((name, dict(arguments)))
        return "ok"

    controller = make_controller(executor=executor)
    controller.activate()
    controller.propose_action("set_volume", {"level": 42})
    outcome = controller.approve()
    assert outcome.succeeded is True
    assert calls == [("set_volume", {"level": 42})]


def test_executor_failure_is_reported_not_hidden():
    def executor(name, arguments):
        raise RuntimeError("device busy")

    controller = make_controller(executor=executor)
    controller.activate()
    controller.propose_action("open_application")
    outcome = controller.approve()
    assert outcome.started is True
    assert outcome.succeeded is False
    assert "device busy" in outcome.detail


def test_approve_without_pending_is_refused():
    controller = make_controller()
    with pytest.raises(NoPendingApprovalError):
        controller.approve()


# --------------------------------------------------------------------------- #
# Stale / forged approvals
# --------------------------------------------------------------------------- #
def test_wrong_token_is_rejected_and_proposal_kept():
    controller = make_controller()
    controller.activate()
    controller.propose_action("open_application")
    with pytest.raises(StaleApprovalError):
        controller.approve("not-the-real-token")
    assert controller.state is AssistantState.AWAITING_APPROVAL
    assert controller.pending_approval is not None


def test_old_approval_token_cannot_approve_a_newer_action():
    controller = make_controller()
    controller.activate()
    first = controller.propose_action("open_application")
    controller.reject()

    controller.activate()
    second = controller.propose_action("set_volume", {"level": 10})
    assert first.token != second.token

    with pytest.raises(StaleApprovalError):
        controller.approve(first.token)
    assert controller.state is AssistantState.AWAITING_APPROVAL


def test_correct_explicit_token_approves():
    controller = make_controller()
    controller.activate()
    approval = controller.propose_action("open_application")
    outcome = controller.approve(approval.token)
    assert outcome.started is True


# --------------------------------------------------------------------------- #
# Timeouts
# --------------------------------------------------------------------------- #
def test_expired_approval_is_refused_and_state_resets():
    clock = FakeClock()
    controller = make_controller(clock=clock, approval_timeout=10.0)
    controller.activate()
    controller.propose_action("open_application")
    clock.advance(10.0)
    with pytest.raises(ApprovalExpiredError):
        controller.approve()
    assert controller.state is AssistantState.IDLE
    assert controller.pending_approval is None


def test_check_timeout_expires_pending_proposal():
    clock = FakeClock()
    controller = make_controller(clock=clock, approval_timeout=10.0)
    controller.activate()
    controller.propose_action("open_application")
    clock.advance(10.0)
    assert controller.check_timeout() is True
    assert controller.state is AssistantState.IDLE


def test_check_timeout_is_false_before_deadline():
    clock = FakeClock()
    controller = make_controller(clock=clock, approval_timeout=10.0)
    controller.activate()
    controller.propose_action("open_application")
    clock.advance(9.9)
    assert controller.check_timeout() is False
    assert controller.state is AssistantState.AWAITING_APPROVAL


# --------------------------------------------------------------------------- #
# Rejection / cancellation
# --------------------------------------------------------------------------- #
def test_reject_returns_to_idle_and_clears_pending():
    controller = make_controller()
    controller.activate()
    controller.propose_action("open_application")
    assert controller.reject() is AssistantState.IDLE
    assert controller.pending_approval is None


def test_cancel_from_awaiting_discards_proposal():
    controller = make_controller()
    controller.activate()
    controller.propose_action("open_application")
    assert controller.cancel() is AssistantState.IDLE
    with pytest.raises(NoPendingApprovalError):
        controller.approve()


def test_cancel_prevents_pending_action_from_executing():
    executed: list[str] = []

    def executor(name, arguments):
        executed.append(name)

    controller = make_controller(executor=executor)
    controller.activate()
    controller.propose_action("open_application")
    controller.cancel()
    with pytest.raises(NoPendingApprovalError):
        controller.approve()
    assert executed == []


def test_cancel_when_idle_is_safe():
    controller = make_controller()
    assert controller.cancel() is AssistantState.IDLE


# --------------------------------------------------------------------------- #
# Observers
# --------------------------------------------------------------------------- #
def test_listener_receives_state_change_events():
    events: list[str] = []
    controller = make_controller()
    controller.add_listener(lambda event, payload: events.append(event))
    controller.activate()
    assert "state_changed" in events


def test_broken_listener_does_not_break_controller():
    controller = make_controller()

    def bad_listener(event, payload):
        raise RuntimeError("listener boom")

    controller.add_listener(bad_listener)
    assert controller.activate() is AssistantState.LISTENING
