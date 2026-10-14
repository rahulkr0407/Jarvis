"""Integration tests: AI as a fallback inside the assistant.

The key guarantees: rule-based commands never call AI; AI can only ever add a
*proposal* (never an execution); and every AI path still goes through the normal
policy + approval gate.
"""

from __future__ import annotations

import json

from core.assistant import VoiceAssistant
from core.command_router import CommandRouter
from core.controller import AssistantController
from core.states import AssistantState
from ai.client import AIClient
from ai.config import AIConfig
from ai.orchestrator import AIOrchestrator
from security.policy import build_default_policy
from tests.fakes import FakeProvider, FakeTTS

ENABLED = AIConfig(api_key="test-key")


def make_assistant(text: str = "", *, available: bool = True, with_ai: bool = True):
    controller = AssistantController(build_default_policy())
    tts = FakeTTS()
    orchestrator = None
    provider = None
    if with_ai:
        provider = FakeProvider(text, available=available)
        orchestrator = AIOrchestrator(AIClient(ENABLED, provider=provider))
    assistant = VoiceAssistant(
        controller, CommandRouter(), speak=tts.say, ai=orchestrator
    )
    return assistant, controller, tts, provider


def test_without_ai_unknown_is_refused_as_before():
    assistant, controller, tts, _ = make_assistant(with_ai=False)
    assistant.request_listening()
    assert assistant.submit_text("do my homework") is None
    assert controller.state is AssistantState.IDLE
    assert any("permitted action" in line for line in tts.spoken)


def test_ai_answer_is_spoken_without_any_proposal():
    raw = json.dumps({"type": "answer", "text": "Here is the answer."})
    assistant, controller, tts, _ = make_assistant(raw)
    assistant.request_listening()
    result = assistant.submit_text("explain gravity")
    assert result is None
    assert controller.state is AssistantState.IDLE
    assert "Here is the answer." in tts.spoken


def test_ai_valid_action_becomes_an_approval_proposal():
    raw = json.dumps(
        {
            "type": "propose_action",
            "action": {"name": "create_folder", "arguments": {"name": "plans"}},
        }
    )
    assistant, controller, _, _ = make_assistant(raw)
    assistant.request_listening()
    approval = assistant.submit_text("make a folder for my plans")
    assert approval is not None
    assert controller.pending_approval.action_name == "create_folder"


def test_ai_proposal_never_executes_on_its_own():
    raw = json.dumps(
        {
            "type": "propose_action",
            "action": {"name": "open_url", "arguments": {"url": "example.com"}},
        }
    )
    assistant, controller, _, _ = make_assistant(raw)
    assistant.request_listening()
    assistant.submit_text("take me to example dot com")
    assert controller.state is AssistantState.AWAITING_APPROVAL
    assert controller.last_outcome is None


def test_ai_unregistered_action_creates_no_proposal():
    raw = json.dumps(
        {
            "type": "propose_action",
            "action": {"name": "shutdown_pc", "arguments": {}},
        }
    )
    assistant, controller, tts, _ = make_assistant(raw)
    assistant.request_listening()
    result = assistant.submit_text("turn off the computer")
    assert result is None
    assert controller.state is AssistantState.IDLE
    assert controller.pending_approval is None


def test_ai_malformed_output_creates_no_proposal():
    assistant, controller, _, _ = make_assistant("not json at all")
    assistant.request_listening()
    assert assistant.submit_text("???") is None
    assert controller.state is AssistantState.IDLE


def test_rule_based_command_never_calls_the_ai():
    raw = json.dumps({"type": "answer", "text": "should not be used"})
    assistant, controller, _, provider = make_assistant(raw)
    assistant.request_listening()
    approval = assistant.submit_text("open notepad")
    assert approval is not None
    assert controller.pending_approval.action_name == "open_application"
    assert provider.calls == []


def test_cancel_never_reaches_the_ai():
    raw = json.dumps({"type": "answer", "text": "should not be used"})
    assistant, controller, _, provider = make_assistant(raw)
    assistant.request_listening()
    assistant.submit_text("cancel")
    assert controller.state is AssistantState.IDLE
    assert provider.calls == []


def test_ai_unavailable_still_returns_to_idle():
    assistant, controller, tts, _ = make_assistant(available=False)
    assistant.request_listening()
    assert assistant.submit_text("what is the weather") is None
    assert controller.state is AssistantState.IDLE
    assert tts.spoken
