"""The provider interface the AI client depends on.

A provider is the only thing that talks to a network. Keeping it behind a tiny
:class:`LLMProvider` protocol means the rest of the assistant (and every test)
can run with no network at all: a :class:`~ai.providers.null_provider.NullProvider`
stands in when no key is configured.

Messages are plain data. A provider must never raise anything other than the
errors in :mod:`ai.errors`, and must never log or persist the API key.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ChatMessage:
    """One message in a chat exchange."""

    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class LLMResponse:
    """The text a provider returned, plus light metadata."""

    text: str
    model: str = ""
    raw: Mapping[str, object] | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """Anything that can turn a list of messages into text."""

    @property
    def name(self) -> str:
        """A short identifier (used for status display, never for secrets)."""

    def is_available(self) -> bool:
        """Return ``True`` when a call could actually succeed."""

    def complete(
        self, messages: Sequence[ChatMessage], *, timeout: float
    ) -> LLMResponse:
        """Return a completion or raise a typed error from :mod:`ai.errors`."""
