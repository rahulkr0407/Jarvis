"""Error types for the optional AI layer.

These are deliberately narrow so callers can tell the difference between "the
provider is not configured" (ordinary, not an error worth surfacing), "the call
failed or timed out" (recoverable; fall back to rule-based behaviour), and "the
model returned something we refuse to act on" (a safety event).
"""

from __future__ import annotations


class AIError(RuntimeError):
    """Base class for every AI-layer problem."""


class ProviderUnavailableError(AIError):
    """Raised when no provider is configured (for example, no API key)."""


class ProviderError(AIError):
    """Raised when the provider returned an error response or a bad payload."""


class LLMTimeoutError(AIError):
    """Raised when a provider call exceeded its time budget."""


class InvalidModelOutputError(AIError):
    """Raised when model output fails schema validation.

    This is a *safety* refusal: the output is malformed, oversized, or shaped
    like something the assistant must never act on.
    """


class UnknownActionError(InvalidModelOutputError):
    """Raised when the model proposes an action that is not in the allowlist."""
