"""Tests for the AI client's availability and error handling."""

from __future__ import annotations

import pytest

from ai.client import AIClient, build_provider
from ai.config import AIConfig
from ai.errors import LLMTimeoutError, ProviderUnavailableError
from ai.provider import ChatMessage
from ai.providers import NullProvider, OpenAICompatibleProvider
from tests.fakes import FakeProvider

MESSAGES = [ChatMessage("user", "hi")]


def test_no_key_yields_null_provider():
    provider = build_provider(AIConfig(api_key=""))
    assert isinstance(provider, NullProvider)


def test_key_yields_openai_compatible_provider():
    provider = build_provider(AIConfig(api_key="k"))
    assert isinstance(provider, OpenAICompatibleProvider)


def test_unknown_provider_name_fails_closed():
    provider = build_provider(AIConfig(api_key="k", provider="mystery"))
    assert isinstance(provider, NullProvider)


def test_client_unavailable_without_key():
    client = AIClient(AIConfig(api_key=""))
    assert client.is_available() is False
    with pytest.raises(ProviderUnavailableError):
        client.complete(MESSAGES)


def test_client_disabled_flag_overrides_available_provider():
    client = AIClient(
        AIConfig(api_key="k", enabled=False),
        provider=FakeProvider("hello"),
    )
    assert client.is_available() is False
    with pytest.raises(ProviderUnavailableError):
        client.complete(MESSAGES)


def test_client_returns_provider_response():
    client = AIClient(
        AIConfig(api_key="k"),
        provider=FakeProvider("answer"),
    )
    assert client.is_available() is True
    assert client.complete(MESSAGES).text == "answer"


def test_client_propagates_timeout():
    client = AIClient(
        AIConfig(api_key="k"),
        provider=FakeProvider(error=LLMTimeoutError("slow")),
    )
    with pytest.raises(LLMTimeoutError):
        client.complete(MESSAGES)
