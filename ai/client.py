"""The AI client: configuration + provider + a single guarded call.

The client is intentionally thin. It knows *how to call* a provider safely —
availability check, hard timeout, typed errors — but not *what to do* with the
result. Interpretation and validation live in :mod:`ai.orchestrator` and
:mod:`ai.schemas`.

The API key never leaves this layer: it lives inside the provider, is never
logged, and never appears in an error message.
"""

from __future__ import annotations

from collections.abc import Sequence

from ai.config import AIConfig, load_ai_config
from ai.errors import ProviderUnavailableError
from ai.provider import ChatMessage, LLMProvider, LLMResponse
from ai.providers.null_provider import NullProvider
from ai.providers.openai_compatible import OpenAICompatibleProvider


def build_provider(config: AIConfig) -> LLMProvider:
    """Return a provider for ``config``, or a null provider if unusable."""
    if not config.is_usable():
        return NullProvider()
    if config.provider == "openai_compatible":
        return OpenAICompatibleProvider(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
        )
    # Unknown provider names fail closed: AI is simply unavailable.
    return NullProvider()


class AIClient:
    """Calls the configured provider for a single completion."""

    def __init__(
        self, config: AIConfig | None = None, provider: LLMProvider | None = None
    ) -> None:
        self._config = config or load_ai_config()
        self._provider = provider if provider is not None else build_provider(self._config)

    @property
    def config(self) -> AIConfig:
        """The resolved configuration (safe to inspect; never leaks the key)."""
        return self._config

    @property
    def provider_name(self) -> str:
        """A short provider identifier for status display."""
        return self._provider.name

    def is_available(self) -> bool:
        """Return ``True`` when a call could actually be attempted."""
        return self._config.enabled and self._provider.is_available()

    def complete(self, messages: Sequence[ChatMessage]) -> LLMResponse:
        """Call the provider once, raising a typed error on failure.

        Raises:
            ProviderUnavailableError: when AI is disabled or unconfigured.
        """
        if not self._config.enabled:
            raise ProviderUnavailableError("AI features are disabled.")
        if not self._provider.is_available():
            raise ProviderUnavailableError("No AI provider is configured.")
        return self._provider.complete(
            messages, timeout=self._config.timeout_seconds
        )
