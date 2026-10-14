"""Conversational answers and explanations.

This is the "chat" side of the AI layer. It builds the messages for a provider
call (a fixed system prompt plus the single user turn — the client is stateless),
and it provides a small **local** fallback so the assistant stays useful and
honest when no provider is configured.

The system prompt declares that the model is not a security authority. Nothing
here executes anything: an answer is only ever spoken.
"""

from __future__ import annotations

from collections.abc import Sequence

from ai.client import AIClient
from ai.config import AIConfig
from ai.provider import ChatMessage

#: Small, deterministic replies used when AI is unavailable. These are the
#: assistant describing itself, not performing any action.
_LOCAL_REPLIES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("who are you", "what are you", "your name"),
        "I'm JARVIS, a local Windows assistant. I can run a small set of "
        "approved actions on your command, and I only act after you approve.",
    ),
    (
        ("what can you do", "help", "commands", "capabilities"),
        "I can open allowlisted apps, open a web page, list a permitted folder, "
        "create a folder in my sandbox, or open a permitted file — each after "
        "your explicit approval. I can also answer questions if AI is enabled.",
    ),
    (
        ("thank you", "thanks", "thank"),
        "You're welcome.",
    ),
    (
        ("hello", "hi", "hey"),
        "Hello. Activate me with the button or Ctrl+Space when you need something.",
    ),
)


class ConversationalResponder:
    """Generates conversational text, with a local fallback when offline."""

    def __init__(self, client: AIClient, config: AIConfig | None = None) -> None:
        self._client = client
        self._config = config or client.config

    def is_available(self) -> bool:
        """Return ``True`` when a provider-backed answer is possible."""
        return self._client.is_available()

    def build_messages(self, user_text: str) -> list[ChatMessage]:
        """Build the stateless message list for one user turn."""
        prompt = (user_text or "").strip()[: self._config.max_prompt_chars]
        return [
            ChatMessage("system", self._config.system_prompt),
            ChatMessage("user", prompt),
        ]

    def local_answer(self, user_text: str) -> str:
        """Return a small canned reply, or an honest 'AI unavailable' message."""
        normalized = " ".join((user_text or "").lower().split())
        for triggers, reply in _LOCAL_REPLIES:
            if any(trigger in normalized for trigger in triggers):
                return reply
        return (
            "I don't have a rule for that, and AI features aren't configured. "
            "Set JARVIS_LLM_API_KEY to enable conversational answers."
        )
