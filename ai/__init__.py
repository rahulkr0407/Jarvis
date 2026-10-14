"""Optional AI conversation layer (Phase 5).

The whole package is **client-only** and network-isolated: it can make one
outbound call to a configured provider and return text, and nothing more. It has
no reference to the controller, the state machine, the action registry, or the
filesystem. The only way anything it produces can affect the machine is as a
*validated candidate proposal* that the assistant routes through the normal
policy and approval gate.

With no API key configured, a :class:`~ai.providers.null_provider.NullProvider`
stands in and the assistant behaves exactly as it did in Phase 4.
"""

from __future__ import annotations

from ai.client import AIClient, build_provider
from ai.config import AIConfig, load_ai_config
from ai.errors import (
    AIError,
    InvalidModelOutputError,
    LLMTimeoutError,
    ProviderError,
    ProviderUnavailableError,
    UnknownActionError,
)
from ai.env import load_dotenv, parse_dotenv
from ai.orchestrator import (
    AIAnswer,
    AIOrchestrator,
    AIOutcome,
    AIProposal,
    AIUnavailable,
)
from ai.provider import ChatMessage, LLMProvider, LLMResponse
from ai.responder import ConversationalResponder
from ai.schemas import ModelAction, ModelAnswer, ModelOutputValidator

__all__ = [
    "AIClient",
    "AIConfig",
    "AIError",
    "AIAnswer",
    "AIOrchestrator",
    "AIOutcome",
    "AIProposal",
    "AIUnavailable",
    "ChatMessage",
    "ConversationalResponder",
    "InvalidModelOutputError",
    "LLMProvider",
    "LLMResponse",
    "LLMTimeoutError",
    "ModelAction",
    "ModelAnswer",
    "ModelOutputValidator",
    "ProviderError",
    "ProviderUnavailableError",
    "UnknownActionError",
    "build_provider",
    "load_ai_config",
    "load_dotenv",
    "parse_dotenv",
]
