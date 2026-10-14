"""A minimal OpenAI-compatible chat provider built on the standard library.

No third-party HTTP dependency is used. The provider speaks the widely supported
``POST {base_url}/chat/completions`` shape, so it works with OpenAI, Azure
OpenAI-compatible gateways, and local servers such as Ollama or LM Studio
(point ``JARVIS_LLM_BASE_URL`` at the local endpoint to keep data on-machine).

Safety notes:

* The API key is held privately and is **never** written to logs, audit records,
  preferences, or exception messages.
* Responses are read with a hard byte cap, so a hostile server cannot exhaust
  memory.
* Every failure is mapped to a typed error in :mod:`ai.errors`; nothing here
  raises a bare exception.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence

from ai.errors import LLMTimeoutError, ProviderError, ProviderUnavailableError
from ai.provider import ChatMessage, LLMResponse

#: Generous cap for a chat completion body. Completions are small text.
_MAX_RESPONSE_BYTES = 1_000_000


class OpenAICompatibleProvider:
    """A chat provider for any OpenAI-compatible ``/chat/completions`` endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        max_tokens: int = 512,
    ) -> None:
        self._api_key = api_key or ""
        self._base_url = (base_url or "").rstrip("/")
        self._model = model
        self._max_tokens = max_tokens

    @property
    def name(self) -> str:
        return "openai_compatible"

    def is_available(self) -> bool:
        return bool(self._api_key.strip() and self._base_url)

    def _endpoint(self) -> str:
        if self._base_url.endswith("/chat/completions"):
            return self._base_url
        return f"{self._base_url}/chat/completions"

    def complete(
        self, messages: Sequence[ChatMessage], *, timeout: float
    ) -> LLMResponse:
        if not self.is_available():
            raise ProviderUnavailableError("The AI provider is not configured.")

        body = {
            "model": self._model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "temperature": 0,
            "max_tokens": self._max_tokens,
        }
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint(),
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(_MAX_RESPONSE_BYTES)
        except urllib.error.HTTPError as exc:
            # Do not echo the body/key; the status is enough to act on.
            raise ProviderError(
                f"The AI provider returned HTTP {exc.code}."
            ) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise LLMTimeoutError("The AI provider timed out.") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise LLMTimeoutError("The AI provider timed out.") from exc
            raise ProviderUnavailableError(
                "The AI provider could not be reached."
            ) from exc

        return self._parse(raw)

    def _parse(self, raw: bytes) -> LLMResponse:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProviderError("The AI provider returned invalid JSON.") from exc
        if not isinstance(payload, Mapping):
            raise ProviderError("The AI provider returned an unexpected payload.")

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError("The AI provider returned no choices.")
        first = choices[0]
        if not isinstance(first, Mapping):
            raise ProviderError("The AI provider returned a malformed choice.")
        message = first.get("message")
        if not isinstance(message, Mapping):
            raise ProviderError("The AI provider returned no message.")
        content = message.get("content")
        if not isinstance(content, str):
            raise ProviderError("The AI provider returned no text content.")

        model = payload.get("model")
        return LLMResponse(
            text=content,
            model=str(model) if isinstance(model, str) else self._model,
        )
