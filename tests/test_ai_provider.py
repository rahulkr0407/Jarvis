"""Tests for the LLM providers. No real network is ever used."""

from __future__ import annotations

import io
import json
import socket
import urllib.error

import pytest

from ai.errors import LLMTimeoutError, ProviderError, ProviderUnavailableError
from ai.provider import ChatMessage
from ai.providers import NullProvider, OpenAICompatibleProvider

MESSAGES = [ChatMessage("user", "hello")]


class FakeUrlResponse:
    """A minimal stand-in for the object urlopen returns."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self, limit: int | None = None) -> bytes:
        return self._body if limit is None else self._body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _completion(text: str, model: str = "test-model") -> bytes:
    return json.dumps(
        {"model": model, "choices": [{"message": {"content": text}}]}
    ).encode("utf-8")


# --------------------------------------------------------------------------- #
# Null provider
# --------------------------------------------------------------------------- #
def test_null_provider_is_never_available():
    provider = NullProvider()
    assert provider.is_available() is False
    with pytest.raises(ProviderUnavailableError):
        provider.complete(MESSAGES, timeout=1.0)


# --------------------------------------------------------------------------- #
# OpenAI-compatible provider
# --------------------------------------------------------------------------- #
def test_missing_key_is_unavailable():
    provider = OpenAICompatibleProvider(
        api_key="", base_url="https://api.example.com/v1", model="m"
    )
    assert provider.is_available() is False
    with pytest.raises(ProviderUnavailableError):
        provider.complete(MESSAGES, timeout=1.0)


def test_successful_completion(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["auth"] = request.get_header("Authorization")
        body = json.loads(request.data.decode("utf-8"))
        captured["body"] = body
        return FakeUrlResponse(_completion("hello there"))

    monkeypatch.setattr(
        "ai.providers.openai_compatible.urllib.request.urlopen", fake_urlopen
    )
    provider = OpenAICompatibleProvider(
        api_key="secret-key", base_url="https://api.example.com/v1", model="m"
    )
    response = provider.complete(MESSAGES, timeout=4.0)

    assert response.text == "hello there"
    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["timeout"] == 4.0
    assert captured["auth"] == "Bearer secret-key"
    assert captured["body"]["model"] == "m"
    assert captured["body"]["messages"][0]["content"] == "hello"


def test_endpoint_not_double_appended(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return FakeUrlResponse(_completion("ok"))

    monkeypatch.setattr(
        "ai.providers.openai_compatible.urllib.request.urlopen", fake_urlopen
    )
    provider = OpenAICompatibleProvider(
        api_key="k", base_url="https://host/v1/chat/completions", model="m"
    )
    provider.complete(MESSAGES, timeout=1.0)
    assert captured["url"] == "https://host/v1/chat/completions"


def test_http_error_becomes_provider_error(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 500, "boom", {}, io.BytesIO(b"")
        )

    monkeypatch.setattr(
        "ai.providers.openai_compatible.urllib.request.urlopen", fake_urlopen
    )
    provider = OpenAICompatibleProvider(api_key="k", base_url="https://h/v1", model="m")
    with pytest.raises(ProviderError):
        provider.complete(MESSAGES, timeout=1.0)


def test_socket_timeout_becomes_timeout_error(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise socket.timeout("timed out")

    monkeypatch.setattr(
        "ai.providers.openai_compatible.urllib.request.urlopen", fake_urlopen
    )
    provider = OpenAICompatibleProvider(api_key="k", base_url="https://h/v1", model="m")
    with pytest.raises(LLMTimeoutError):
        provider.complete(MESSAGES, timeout=1.0)


def test_url_error_with_timeout_reason_is_timeout(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError(socket.timeout("slow"))

    monkeypatch.setattr(
        "ai.providers.openai_compatible.urllib.request.urlopen", fake_urlopen
    )
    provider = OpenAICompatibleProvider(api_key="k", base_url="https://h/v1", model="m")
    with pytest.raises(LLMTimeoutError):
        provider.complete(MESSAGES, timeout=1.0)


def test_url_error_otherwise_is_unavailable(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(
        "ai.providers.openai_compatible.urllib.request.urlopen", fake_urlopen
    )
    provider = OpenAICompatibleProvider(api_key="k", base_url="https://h/v1", model="m")
    with pytest.raises(ProviderUnavailableError):
        provider.complete(MESSAGES, timeout=1.0)


def test_invalid_json_becomes_provider_error(monkeypatch):
    monkeypatch.setattr(
        "ai.providers.openai_compatible.urllib.request.urlopen",
        lambda request, timeout=None: FakeUrlResponse(b"not json"),
    )
    provider = OpenAICompatibleProvider(api_key="k", base_url="https://h/v1", model="m")
    with pytest.raises(ProviderError):
        provider.complete(MESSAGES, timeout=1.0)


def test_missing_choices_becomes_provider_error(monkeypatch):
    monkeypatch.setattr(
        "ai.providers.openai_compatible.urllib.request.urlopen",
        lambda request, timeout=None: FakeUrlResponse(b'{"model": "m"}'),
    )
    provider = OpenAICompatibleProvider(api_key="k", base_url="https://h/v1", model="m")
    with pytest.raises(ProviderError):
        provider.complete(MESSAGES, timeout=1.0)


def test_error_messages_never_contain_the_key(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 401, "unauthorized", {}, io.BytesIO(b"")
        )

    monkeypatch.setattr(
        "ai.providers.openai_compatible.urllib.request.urlopen", fake_urlopen
    )
    provider = OpenAICompatibleProvider(
        api_key="top-secret", base_url="https://h/v1", model="m"
    )
    with pytest.raises(ProviderError) as info:
        provider.complete(MESSAGES, timeout=1.0)
    assert "top-secret" not in str(info.value)
