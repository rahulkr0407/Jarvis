"""Configuration for the optional AI provider.

All values come from environment variables so **no secret is ever committed**.
:func:`load_ai_config` reads the well-known ``JARVIS_LLM_*`` variables and falls
back to the safe defaults in :mod:`config.settings`.

The API key is the only required value: with no key the provider is reported as
unavailable and the assistant keeps working exactly as it did in Phase 4.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from config import settings

#: Environment variable names. The API key is intentionally the only secret.
ENV_API_KEY = "JARVIS_LLM_API_KEY"
ENV_BASE_URL = "JARVIS_LLM_BASE_URL"
ENV_MODEL = "JARVIS_LLM_MODEL"
ENV_PROVIDER = "JARVIS_LLM_PROVIDER"
ENV_TIMEOUT = "JARVIS_LLM_TIMEOUT"
ENV_AI_ENABLED = "JARVIS_AI_ENABLED"


def _first(env: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = env.get(name)
        if value:
            return value
    return ""


def _to_bool(value: str, default: bool) -> bool:
    text = (value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _to_float(value: str, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


@dataclass(frozen=True)
class AIConfig:
    """Resolved AI configuration. Immutable and safe to hold in memory.

    ``api_key`` is stored but must never be logged or persisted. Use
    :meth:`has_credentials` rather than checking the key directly.
    """

    api_key: str = ""
    base_url: str = settings.AI_BASE_URL
    model: str = settings.AI_MODEL
    provider: str = settings.AI_PROVIDER
    timeout_seconds: float = settings.AI_TIMEOUT_SECONDS
    enabled: bool = settings.AI_ENABLED_DEFAULT
    max_prompt_chars: int = settings.AI_MAX_PROMPT_CHARS
    max_output_chars: int = settings.AI_MAX_OUTPUT_CHARS
    system_prompt: str = settings.AI_SYSTEM_PROMPT

    def has_credentials(self) -> bool:
        """Return ``True`` when an API key is present."""
        return bool(self.api_key and self.api_key.strip())

    def is_usable(self) -> bool:
        """Return ``True`` when AI may actually be used (enabled + key)."""
        return bool(self.enabled and self.has_credentials())

    def __repr__(self) -> str:  # never leak the key in logs/reprs
        return (
            f"AIConfig(provider={self.provider!r}, model={self.model!r}, "
            f"base_url={self.base_url!r}, timeout_seconds={self.timeout_seconds!r}, "
            f"enabled={self.enabled!r}, api_key={'<set>' if self.has_credentials() else '<unset>'})"
        )


def load_ai_config(env: Mapping[str, str] | None = None) -> AIConfig:
    """Build an :class:`AIConfig` from an environment mapping.

    Defaults come from :mod:`config.settings`; environment variables override
    them. ``JARVIS_LLM_API_KEY`` is the (optional) secret.
    """
    source = os.environ if env is None else env
    return AIConfig(
        api_key=_first(source, ENV_API_KEY, "OPENAI_API_KEY"),
        base_url=_first(source, ENV_BASE_URL) or settings.AI_BASE_URL,
        model=_first(source, ENV_MODEL) or settings.AI_MODEL,
        provider=_first(source, ENV_PROVIDER) or settings.AI_PROVIDER,
        timeout_seconds=_to_float(
            _first(source, ENV_TIMEOUT), settings.AI_TIMEOUT_SECONDS
        ),
        enabled=_to_bool(
            _first(source, ENV_AI_ENABLED), settings.AI_ENABLED_DEFAULT
        ),
    )
