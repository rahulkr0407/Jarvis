"""High-level orchestration: turn user input into an approval request.

:class:`VoiceAssistant` is the small glue layer the UI talks to. It is
**Qt-free** and does not perform any blocking I/O itself:

* It receives already-produced input (a typed line, or a
  :class:`~core.voice_pipeline.ListenResult` from the worker thread).
* It routes that input through the allowlist-only :class:`CommandRouter`.
* If the input maps to allowed action, it asks the controller to *propose* it —
  which moves to ``AWAITING_APPROVAL`` and still requires the user to approve.
* Otherwise it speaks a short reply and returns the assistant to ``IDLE``.

Crucially, nothing here can reach ``EXECUTING``: recognizing a phrase only ever
creates a proposal. Speech is treated as untrusted input throughout.

When the deterministic router has no match, an *optional* AI orchestrator may be
consulted (Phase 5). It is only ever allowed to produce a conversational reply or
a candidate proposal — which still goes through the exact same policy and
approval gate. The assistant holds no path by which AI can execute anything.

The ``speak`` callback is injected by the UI (it forwards to a TTS worker
thread); a no-op is used by default so core stays silent and testable.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from core.command_router import CommandRouter
from core.controller import AssistantController
from core.intents import IntentName
from core.states import AssistantState
from core.voice_pipeline import ListenResult, ListenStatus
from security.approval import ApprovalRequest

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a core->ai import
    from ai.orchestrator import AIOrchestrator


class VoiceAssistant:
    """Coordinates controller, router, and speech output for one interaction."""

    def __init__(
        self,
        controller: AssistantController,
        router: CommandRouter | None = None,
        *,
        speak: Callable[[str], None] | None = None,
        ai: "AIOrchestrator | None" = None,
    ) -> None:
        self._controller = controller
        self._router = router or CommandRouter()
        self._speak = speak or (lambda text: None)
        self._ai = ai

    @property
    def controller(self) -> AssistantController:
        """The underlying controller (read-only access for the UI)."""
        return self._controller

    # ------------------------------------------------------------------ #
    # Activation
    # ------------------------------------------------------------------ #
    def request_listening(self) -> bool:
        """Enter LISTENING if currently IDLE. Returns whether it happened.

        This is the *only* entry point into listening, and it is only ever
        called from an explicit user gesture.
        """
        if self._controller.state is not AssistantState.IDLE:
            return False
        self._controller.activate()
        self._speak("Listening.")
        return True

    def cancel(self) -> None:
        """Stop and return to IDLE. Safe from any state."""
        self._controller.cancel()

    # ------------------------------------------------------------------ #
    # Input handling
    # ------------------------------------------------------------------ #
    def submit_text(self, text: str) -> ApprovalRequest | None:
        """Route a typed or transcribed line into a proposal or a reply.

        Returns the created :class:`ApprovalRequest` when an allowed action was
        proposed, otherwise ``None``.
        """
        text = (text or "").strip()
        if not text:
            self._speak("I didn't catch that.")
            self._return_to_idle()
            return None

        intent = self._router.route(text)
        if intent is None:
            return self._handle_unknown(text)

        # Control command: stop everything and clear any pending proposal.
        # It needs no approval and never reaches the approval panel.
        if intent.action_name == IntentName.CANCEL_COMMAND.value:
            self._controller.cancel()
            self._speak("Cancelled.")
            return None

        return self.propose_action(intent.action_name, dict(intent.arguments))

    def propose_action(
        self, action_name: str, arguments: Mapping[str, object] | None = None
    ) -> ApprovalRequest | None:
        """Propose one structured action through the normal approval path.

        This is the same safe entry point :meth:`submit_text` uses; the UI calls
        it directly for actions it builds itself (for example a file chosen in a
        picker). It only ever creates a *proposal* — never an execution.
        """
        # Typed or UI actions arrive while IDLE; activate quietly so we can propose.
        if self._controller.state is AssistantState.IDLE:
            self._controller.activate()
        if self._controller.state is not AssistantState.LISTENING:
            self._speak("I'm not ready for a command right now.")
            return None

        try:
            approval = self._controller.propose_action(
                action_name, dict(arguments or {})
            )
        except Exception as exc:  # policy/transition problems are reported, not fatal
            self._speak("I couldn't propose that.")
            self._return_to_idle()
            self._notify_message(f"Could not propose action: {exc}")
            return None

        self._speak(f"Proposed {action_name}. Awaiting your approval.")
        return approval

    def handle_listen_result(self, result: ListenResult) -> None:
        """React to a finished listen/transcribe cycle."""
        if result.status is ListenStatus.OK:
            self.submit_text(result.transcript)
            return

        if result.status is ListenStatus.CANCELLED:
            self._return_to_idle()
            return

        # NO_SPEECH / MICROPHONE_ERROR / TRANSCRIPTION_ERROR
        self._speak(result.message or "I couldn't hear a command.")
        self._return_to_idle()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _handle_unknown(self, text: str) -> ApprovalRequest | None:
        """Handle input the deterministic router did not recognize.

        When an AI orchestrator is present it may supply a conversational reply
        or a *candidate* proposal. A proposal is routed through the normal
        :meth:`propose_action` path, so policy and approval still apply. With no
        AI (or on any AI failure) this behaves exactly as Phase 4 did.
        """
        if self._ai is None:
            self._speak("I don't have a permitted action for that.")
            self._return_to_idle()
            return None

        # Imported lazily so core stays importable without the ai package.
        from ai.orchestrator import AIAnswer, AIProposal, AIUnavailable

        outcome = self._ai.interpret(text)

        if isinstance(outcome, AIProposal):
            approval = self.propose_action(
                outcome.action_name, dict(outcome.arguments)
            )
            if approval is None:
                self._speak("I couldn't propose that.")
                self._return_to_idle()
            return approval

        if isinstance(outcome, AIAnswer):
            self._speak(outcome.text)
            self._return_to_idle()
            return None

        # AIUnavailable (or unexpected): speak the safe message and stop.
        message = (
            outcome.message
            if isinstance(outcome, AIUnavailable)
            else "I couldn't help with that."
        )
        self._speak(message)
        self._return_to_idle()
        return None

    def _return_to_idle(self) -> None:
        if self._controller.state is AssistantState.LISTENING:
            self._controller.cancel()

    def _notify_message(self, message: str) -> None:
        # Best-effort: surface a message through the controller's listeners so
        # the UI can display it, without inventing a new event contract.
        for listener in list(getattr(self._controller, "_listeners", [])):
            try:
                listener("assistant_message", {"message": message})
            except Exception:
                pass
