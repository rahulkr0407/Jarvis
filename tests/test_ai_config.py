"""Tests for AI configuration loading and secret handling."""

from __future__ import annotations

from ai.config import AIConfig, load_ai_config
from config import settings


def test_defaults_when_environment_is_empty():
    config = load_ai_config({})
    assert config.api_key == ""
    assert config.base_url == settings.AI_BASE_URL
    assert config.model == settings.AI_MODEL
    assert config.enabled is True
    assert config.has_credentials() is False
    assert config.is_usable() is False


def test_environment_overrides_defaults():
    config = load_ai_config(
        {
            "JARVIS_LLM_API_KEY": "k",
            "JARVIS_LLM_BASE_URL": "http://localhost:11434/v1",
            "JARVIS_LLM_MODEL": "local-model",
            "JARVIS_LLM_TIMEOUT": "3.5",
        }
    )
    assert config.api_key == "k"
    assert config.base_url == "http://localhost:11434/v1"
    assert config.model == "local-model"
    assert config.timeout_seconds == 3.5
    assert config.is_usable() is True


def test_openai_key_fallback_is_accepted():
    config = load_ai_config({"OPENAI_API_KEY": "from-openai"})
    assert config.api_key == "from-openai"


def test_ai_disabled_flag():
    config = load_ai_config(
        {"JARVIS_LLM_API_KEY": "k", "JARVIS_AI_ENABLED": "false"}
    )
    assert config.enabled is False
    assert config.is_usable() is False


def test_invalid_timeout_falls_back_to_default():
    config = load_ai_config({"JARVIS_LLM_TIMEOUT": "not-a-number"})
    assert config.timeout_seconds == settings.AI_TIMEOUT_SECONDS
    config = load_ai_config({"JARVIS_LLM_TIMEOUT": "-5"})
    assert config.timeout_seconds == settings.AI_TIMEOUT_SECONDS


def test_repr_never_leaks_the_key():
    config = AIConfig(api_key="super-secret-value")
    text = repr(config)
    assert "super-secret-value" not in text
    assert "<set>" in text


def test_repr_marks_unset_key():
    assert "<unset>" in repr(AIConfig())
