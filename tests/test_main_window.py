"""Offscreen UI tests for the main window.

These run with the Qt ``offscreen`` platform plugin, so they need no display and
open no real window. They focus on the safety-relevant behaviour of the window
itself:

* constructing it opens **no** microphone and starts **no** listening;
* the assistant begins in IDLE;
* a typed command becomes a proposal only;
* approving runs the action exactly once and the real outcome is shown;
* a failing action is reported honestly, never as success.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication

from core.controller import AssistantController
from core.states import AssistantState
from security.policy import build_default_policy
from ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window_factory(qapp):
    created: list[MainWindow] = []

    def build(controller: AssistantController) -> MainWindow:
        window = MainWindow(controller=controller)
        created.append(window)
        return window

    yield build
    for window in created:
        window.close()
        window.deleteLater()
    qapp.processEvents()


def make_controller(executor=None) -> AssistantController:
    return AssistantController(build_default_policy(), executor=executor)


def test_starts_idle_and_opens_no_microphone(window_factory):
    sounddevice_already_loaded = "sounddevice" in sys.modules
    window = window_factory(make_controller())

    assert window._controller.state is AssistantState.IDLE
    assert "IDLE" in window.status_label.text()
    # No listen worker/thread is created until the user activates.
    assert window._listen_thread is None
    assert window._listen_worker is None
    # The microphone stack is imported lazily and must not be touched at startup.
    if not sounddevice_already_loaded:
        assert "sounddevice" not in sys.modules


def test_activate_button_is_enabled_at_startup(window_factory):
    window = window_factory(make_controller())
    assert window.activate_button.isEnabled() is True
    # isHidden() reflects the panel's own show/hide state even when the parent
    # window is never shown on screen (offscreen tests).
    assert window.approval_panel.isHidden() is True


def test_typed_command_creates_a_proposal_but_executes_nothing(window_factory):
    executed: list[str] = []

    def executor(name, arguments):
        executed.append(name)

    window = window_factory(make_controller(executor=executor))
    window.command_input.setText("open notepad")
    window._on_send_command()

    assert window._controller.state is AssistantState.AWAITING_APPROVAL
    assert executed == []
    assert window.approval_panel.isHidden() is False
    assert "open_application" in window.proposal_label.text()


def test_approving_runs_the_action_exactly_once(window_factory):
    executed: list[str] = []

    def executor(name, arguments):
        executed.append(name)

    window = window_factory(make_controller(executor=executor))
    window.command_input.setText("open notepad")
    window._on_send_command()
    window._on_approve()

    assert executed == ["open_application"]
    assert window._controller.state is AssistantState.IDLE
    assert "open_application" in window.message_label.text()


def test_failed_action_is_reported_honestly(window_factory):
    def executor(name, arguments):
        raise RuntimeError("simulated failure")

    window = window_factory(make_controller(executor=executor))
    window.command_input.setText("open notepad")
    window._on_send_command()
    window._on_approve()

    assert window._controller.state is AssistantState.IDLE
    # The UI must never claim success when the action failed.
    assert "did NOT succeed" in window.message_label.text()


def test_rejecting_a_proposal_clears_it_and_runs_nothing(window_factory):
    executed: list[str] = []

    def executor(name, arguments):
        executed.append(name)

    window = window_factory(make_controller(executor=executor))
    window.command_input.setText("open notepad")
    window._on_send_command()
    window._on_reject()

    assert window._controller.state is AssistantState.IDLE
    assert window._controller.pending_approval is None
    assert executed == []
    assert window.approval_panel.isHidden() is True


def test_cancel_clears_a_pending_proposal(window_factory):
    window = window_factory(make_controller())
    window.command_input.setText("open notepad")
    window._on_send_command()
    window._on_cancel()

    assert window._controller.state is AssistantState.IDLE
    assert window._controller.pending_approval is None
