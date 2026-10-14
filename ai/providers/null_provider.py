"""The provider used when no API key is configured.

It is not an error to have no provider: the assistant simply does not have AI
features. Every call raises :class:`ProviderUnavailableError`, which the client
turns into an ordinary "unavailable" outcome so rule-based behaviour continues
uninterrupted.
"""

from __future__ import annotations

from collections.abc import Sequence

from ai.errors import ProviderUnavailableError
from ai.provider import ChatMessage, LLMResponse


class NullProvider:
    """A provider that is never available."""

    @property
    def name(self) -> str:
        return "unavailable"

    def is_available(self) -> bool:
        return False

    def complete(
        self, messages: Sequence[ChatMessage], *, timeout: float
    ) -> LLMResponse:
        raise ProviderUnavailableError(
            "No AI provider is configured. Set JARVIS_LLM_API_KEY to enable it."
        )
