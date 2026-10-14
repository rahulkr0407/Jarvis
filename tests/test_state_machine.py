"""Tests for the assistant state machine."""

from __future__ import annotations

import pytest

from core.state_machine import (
    TRANSITIONS,
    AssistantStateMachine,
    InvalidTransitionError,
)
from core.states import AssistantState


def test_initial_state_is_idle():
    assert AssistantStateMachine().state is AssistantState.IDLE


def test_idle_may_only_go_to_listening():
    machine = AssistantStateMachine()
    assert machine.can_transition(AssistantState.LISTENING)
    assert not machine.can_transition(AssistantState.AWAITING_APPROVAL)
    assert not machine.can_transition(AssistantState.EXECUTING)
    assert not machine.can_transition(AssistantState.IDLE)


@pytest.mark.parametrize(
    "target",
    [AssistantState.IDLE, AssistantState.AWAITING_APPROVAL, AssistantState.EXECUTING],
)
def test_illegal_transition_from_idle_raises(target):
    machine = AssistantStateMachine()
    with pytest.raises(InvalidTransitionError):
        machine.transition(target)
    assert machine.state is AssistantState.IDLE


def test_full_legal_happy_path():
    machine = AssistantStateMachine()
    assert machine.transition(AssistantState.LISTENING) is AssistantState.LISTENING
    assert (
        machine.transition(AssistantState.AWAITING_APPROVAL)
        is AssistantState.AWAITING_APPROVAL
    )
    assert machine.transition(AssistantState.EXECUTING) is AssistantState.EXECUTING
    assert machine.transition(AssistantState.IDLE) is AssistantState.IDLE


def test_return_to_idle_allowed_from_every_active_state():
    for active in (
        AssistantState.LISTENING,
        AssistantState.AWAITING_APPROVAL,
        AssistantState.EXECUTING,
    ):
        machine = AssistantStateMachine(initial=active)
        assert machine.transition(AssistantState.IDLE) is AssistantState.IDLE


def test_executing_cannot_jump_to_listening():
    machine = AssistantStateMachine(initial=AssistantState.EXECUTING)
    with pytest.raises(InvalidTransitionError):
        machine.transition(AssistantState.LISTENING)


def test_invalid_transition_error_exposes_source_and_target():
    machine = AssistantStateMachine()
    with pytest.raises(InvalidTransitionError) as info:
        machine.transition(AssistantState.EXECUTING)
    assert info.value.source is AssistantState.IDLE
    assert info.value.target is AssistantState.EXECUTING


def test_every_active_state_can_reach_idle():
    # Guards against accidentally removing the escape hatch that cancellation
    # and rejection rely on.
    for state in AssistantState:
        assert AssistantState.IDLE in TRANSITIONS[state] or state is AssistantState.IDLE
