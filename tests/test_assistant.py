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


# --------------------------------------------------------------------------- #
# Phase 3: new intents
# --------------------------------------------------------------------------- #
def test_cancel_command_returns_to_idle_without_approval():
    assistant, controller, _ = make_assistant()
    assistant.request_listening()
    result = assistant.submit_text("cancel")
    assert result is None
    assert controller.state is AssistantState.IDLE
    assert controller.pending_approval is None


def test_cancel_command_clears_a_pending_proposal():
    assistant, controller, _ = make_assistant()
    assistant.request_listening()
    assistant.submit_text("open notepad")
    assert controller.state is AssistantState.AWAITING_APPROVAL
    assistant.submit_text("stop")
    assert controller.state is AssistantState.IDLE
    assert controller.pending_approval is None


def test_cancel_command_from_idle_is_safe():
    assistant, controller, _ = make_assistant()
    assert assistant.submit_text("never mind") is None
    assert controller.state is AssistantState.IDLE


def test_tell_time_proposes_and_never_executes():
    assistant, controller, _ = make_assistant()
    assistant.request_listening()
    approval = assistant.submit_text("what time is it")
    assert approval is not None
    assert controller.pending_approval.action_name == "tell_time"
    assert controller.state is AssistantState.AWAITING_APPROVAL
    assert controller.last_outcome is None


def test_list_directory_proposes_with_safe_location():
    assistant, controller, _ = make_assistant()
    assistant.request_listening()
    approval = assistant.submit_text("list files in documents")
    assert approval is not None
    assert controller.pending_approval.action_name == "list_directory"
    assert controller.pending_approval.arguments["location"] == "documents"


def test_create_folder_proposes_with_validated_args():
    assistant, controller, _ = make_assistant()
    assistant.request_listening()
    approval = assistant.submit_text("create folder plans in documents")
    assert approval is not None
    assert controller.pending_approval.action_name == "create_folder"
    assert controller.pending_approval.arguments == {
        "name": "plans",
        "location": "documents",
    }


def test_unsafe_folder_command_is_refused():
    assistant, controller, _ = make_assistant()
    assistant.request_listening()
    assert assistant.submit_text("create folder plans in C:\\Windows") is None
    assert controller.state is AssistantState.IDLE


# --------------------------------------------------------------------------- #
# Phase 4: structured proposals from the UI
# --------------------------------------------------------------------------- #
def test_propose_action_creates_a_proposal_from_idle():
    assistant, controller, _ = make_assistant()
    approval = assistant.propose_action("open_file", {"path": "x"})
    assert approval is not None
    assert controller.pending_approval.action_name == "open_file"
    assert controller.state is AssistantState.AWAITING_APPROVAL


def test_propose_action_never_executes():
    assistant, controller, _ = make_assistant()
    assistant.propose_action("open_url", {"url": "https://example.com"})
    assert controller.state is not AssistantState.EXECUTING
    assert controller.last_outcome is None


def test_propose_action_denied_by_policy_returns_none():
    assistant, controller, _ = make_assistant()
    result = assistant.propose_action("format_c_drive", {})
    assert result is None
    assert controller.state is AssistantState.IDLE


def test_typed_open_url_proposes():
    assistant, controller, _ = make_assistant()
    assistant.request_listening()
    approval = assistant.submit_text("go to example.com")
    assert approval is not None
    assert controller.pending_approval.action_name == "open_url"
