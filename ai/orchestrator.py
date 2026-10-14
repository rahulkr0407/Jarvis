"""Turn untrusted text into either a spoken answer or a *candidate* proposal.

The orchestrator is the top of the AI layer and the only piece the assistant
talks to. It never executes anything and holds no reference to the controller:

* It asks the provider for one reply (stateless: system prompt + the user turn).
* It validates that reply strictly with :class:`ai.schemas.ModelOutputValidator`.
* It returns a plain outcome the assistant can act on safely.

Whatever comes back, the assistant still routes a proposed action through the
normal policy + approval gate. A model answer is only ever spoken.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ai.client import AIClient
from ai.errors import AIError, InvalidModelOutputError
from ai.responder import ConversationalResponder
from ai.schemas import (
    ModelAction,
    ModelAnswer,
    ModelOutputValidator,
    build_default_validator,
)


@dataclass(frozen=True)
class AIAnswer:
    """A conversational reply to speak."""

    text: str


@dataclass(frozen=True)
class AIProposal:
    """A validated candidate action. Not approved, not executed."""

    action_name: str
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class AIUnavailable:
    """AI could not produce a usable result. ``message`` is safe to speak."""

    message: str


AIOutcome = AIAnswer | AIProposal | AIUnavailable


class AIOrchestrator:
    """Coordinates the client, the validator, and the responder."""

    def __init__(
        self,
        client: AIClient,
        *,
        validator: ModelOutputValidator | None = None,
        responder: ConversationalResponder | None = None,
    ) -> None:
        self._client = client
        self._validator = validator or build_default_validator()
        self._responder = responder or ConversationalResponder(client, client.config)

    @property
    def client(self) -> AIClient:
        """The underlying client (for status display/tests)."""
        return self._client

    def is_available(self) -> bool:
        """Return ``True`` when a provider call could be attempted."""
        return self._client.is_available()

    def interpret(self, user_text: str) -> AIOutcome:
        """Interpret one user turn. Never raises; never executes."""
        text = (user_text or "").strip()
        if not text:
            return AIUnavailable("I didn't catch that.")

        if not self._client.is_available():
            return AIUnavailable(self._responder.local_answer(text))

        try:
            response = self._client.complete(self._responder.build_messages(text))
        except AIError:
            # Timeout, unreachable host, provider error: fall back locally.
            return AIUnavailable(self._responder.local_answer(text))

        try:
            parsed = self._validator.parse(response.text)
        except InvalidModelOutputError:
            # A safety refusal: never act on malformed or unregistered output.
            return AIUnavailable(
                "I couldn't turn that into a safe reply, so I did nothing."
            )

        if isinstance(parsed, ModelAction):
            return AIProposal(parsed.action_name, dict(parsed.arguments))
        if isinstance(parsed, ModelAnswer):
            return AIAnswer(parsed.text)
        # Defensive: an unexpected type is treated as unusable.
        return AIUnavailable("I couldn't turn that into a safe reply, so I did nothing.")
