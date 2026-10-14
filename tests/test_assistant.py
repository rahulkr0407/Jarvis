"""Tests for the voice assistant orchestration layer.

The central safety property under test: recognized or typed text can only ever
create a *proposal*. It can never reach EXECUTING on its own.
"""

from __future__ import annotations

from core.assistant import VoiceAssistant
from core.command_router import CommandRouter, Intent
from core.controller import AssistantController
from core.states import AssistantState
from core.voice_pipeline import ListenResult, ListenStatus
from security.policy import build_default_policy
from tests.fakes import FakeTTS


def make_assistant():
    controller = AssistantController(build_default_policy())
    tts = FakeTTS()
    assistant = VoiceAssistant(controller, CommandRouter(), speak=tts.say)
    return assistant, controller, tts


def test_request_listening_from_idle():
    assistant, controller, tts = make_assistant()
    assert assistant.request_listening() is True
    assert controller.state is AssistantState.LISTENING


def test_request_listening_twice_is_refused():
    assistant, controller, _ = make_assistant()
    assistant.request_listening()
    assert assistant.request_listening() is False
    assert controller.state is AssistantState.LISTENING


def test_submit_text_proposes_allowed_action():
    assistant, controller, _ = make_assistant()
    assistant.request_listening()
    approval = assistant.submit_text("open notepad")
    assert approval is not None
    assert controller.state is AssistantState.AWAITING_APPROVAL
    assert controller.pending_approval.action_name == "open_application"


def test_submit_text_never_executes_on_its_own():
    assistant, controller, _ = make_assistant()
    assistant.request_listening()
    assistant.submit_text("open notepad")
    assert controller.state is not AssistantState.EXECUTING
    assert controller.last_outcome is None


def test_submit_text_untrusted_command_is_refused():
    assistant, controller, _ = make_assistant()
    assistant.request_listening()
    result = assistant.submit_text("run format c: now")
    assert result is None
    assert controller.state is AssistantState.IDLE
    assert controller.pending_approval is None


def test_typed_text_from_idle_activates_then_proposes():
    assistant, controller, _ = make_assistant()
    approval = assistant.submit_text("set volume 30")
    assert approval is not None
    assert controller.state is AssistantState.AWAITING_APPROVAL
    assert controller.pending_approval.action_name == "set_volume"
    assert controller.pending_approval.arguments["level"] == 30


def test_handle_listen_result_ok_proposes():
    assistant, controller, _ = make_assistant()
    assistant.request_listening()
    intent = Intent("open_application", {"target": "notepad"})
    result = ListenResult(ListenStatus.OK, transcript="open notepad", intent=intent)
    assistant.handle_listen_result(result)
    assert controller.state is AssistantState.AWAITING_APPROVAL


def test_handle_listen_result_ok_unroutable_returns_idle():
    assistant, controller, _ = make_assistant()
    assistant.request_listening()
    result = ListenResult(ListenStatus.OK, transcript="what is the weather", intent=None)
    assistant.handle_listen_result(result)
    assert controller.state is AssistantState.IDLE


def test_handle_listen_result_no_speech_returns_idle_and_speaks():
    assistant, controller, tts = make_assistant()
    assistant.request_listening()
    assistant.handle_listen_result(
        ListenResult(ListenStatus.NO_SPEECH, message="No speech detected.")
    )
    assert controller.state is AssistantState.IDLE
    assert any("speech" in line.lower() for line in tts.spoken)


def test_handle_listen_result_microphone_error_returns_idle():
    assistant, controller, _ = make_assistant()
    assistant.request_listening()
    assistant.handle_listen_result(
        ListenResult(ListenStatus.MICROPHONE_ERROR, message="boom")
    )
    assert controller.state is AssistantState.IDLE


def test_handle_listen_result_cancelled_returns_idle():
    assistant, controller, _ = make_assistant()
    assistant.request_listening()
    assistant.handle_listen_result(ListenResult(ListenStatus.CANCELLED))
    assert controller.state is AssistantState.IDLE


def test_cancel_returns_to_idle():
    assistant, controller, _ = make_assistant()
    assistant.request_listening()
    assistant.cancel()
    assert controller.state is AssistantState.IDLE
