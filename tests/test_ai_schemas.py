"""Tests for strict validation of model output.

This is the safety-critical gate: the model must not be able to smuggle an
unregistered action or a malformed shape into the assistant.
"""

from __future__ import annotations

import json

import pytest

from ai.errors import InvalidModelOutputError, UnknownActionError
from ai.schemas import (
    ModelAction,
    ModelAnswer,
    ModelOutputValidator,
    build_default_validator,
)


@pytest.fixture()
def validator() -> ModelOutputValidator:
    return build_default_validator()


def _action(name: str, arguments: dict | None = None) -> str:
    return json.dumps(
        {
            "type": "propose_action",
            "action": {"name": name, "arguments": arguments or {}},
        }
    )


# --------------------------------------------------------------------------- #
# Answers
# --------------------------------------------------------------------------- #
def test_valid_answer(validator):
    parsed = validator.parse('{"type": "answer", "text": "Hello there."}')
    assert isinstance(parsed, ModelAnswer)
    assert parsed.text == "Hello there."


def test_answer_with_extra_field_is_rejected(validator):
    with pytest.raises(InvalidModelOutputError):
        validator.parse('{"type": "answer", "text": "x", "extra": 1}')


def test_empty_answer_is_rejected(validator):
    with pytest.raises(InvalidModelOutputError):
        validator.parse('{"type": "answer", "text": "   "}')


def test_oversized_answer_is_rejected(validator):
    huge = "a" * (validator._max_output_chars + 1)
    with pytest.raises(InvalidModelOutputError):
        validator.parse(json.dumps({"type": "answer", "text": huge}))


# --------------------------------------------------------------------------- #
# Malformed structure
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not json",
        "[1, 2, 3]",
        '"a string"',
        '{"type": "unknown"}',
        '{"no": "type"}',
        '{"type": "propose_action"}',
        '{"type": "propose_action", "action": "nope"}',
        '{"type": "propose_action", "action": {"arguments": {}}}',
        '{"type": "propose_action", "action": {"name": "tell_time", "arguments": []}}',
    ],
)
def test_malformed_output_is_rejected(validator, raw):
    with pytest.raises(InvalidModelOutputError):
        validator.parse(raw)


def test_code_fence_is_tolerated(validator):
    fenced = "```json\n" + _action("tell_time") + "\n```"
    parsed = validator.parse(fenced)
    assert isinstance(parsed, ModelAction)
    assert parsed.action_name == "tell_time"


# --------------------------------------------------------------------------- #
# Registered intents only
# --------------------------------------------------------------------------- #
def test_unregistered_action_is_refused(validator):
    with pytest.raises(UnknownActionError):
        validator.parse(_action("delete_everything"))


def test_unregistered_action_is_an_invalid_output_error(validator):
    # UnknownActionError is a subtype, so callers can catch either.
    with pytest.raises(InvalidModelOutputError):
        validator.parse(_action("format_c_drive"))


# --------------------------------------------------------------------------- #
# Argument validation mirrors the rule-based router
# --------------------------------------------------------------------------- #
def test_tell_time_takes_no_arguments(validator):
    parsed = validator.parse(_action("tell_time"))
    assert parsed.arguments == {}


def test_tell_time_rejects_unexpected_arguments(validator):
    with pytest.raises(InvalidModelOutputError):
        validator.parse(_action("tell_time", {"x": 1}))


def test_open_url_is_normalized(validator):
    parsed = validator.parse(_action("open_url", {"url": "example.com"}))
    assert parsed.arguments["url"].startswith("https://")


def test_open_url_rejects_dangerous_scheme(validator):
    with pytest.raises(InvalidModelOutputError):
        validator.parse(_action("open_url", {"url": "javascript:alert(1)"}))


def test_open_application_allowlist_enforced(validator):
    parsed = validator.parse(_action("open_application", {"target": "notepad"}))
    assert parsed.arguments["target"] == "notepad"
    with pytest.raises(InvalidModelOutputError):
        validator.parse(_action("open_application", {"target": "powershell"}))


def test_create_folder_validates_name_and_location(validator):
    parsed = validator.parse(
        _action("create_folder", {"name": "plans", "location": "documents"})
    )
    assert parsed.arguments == {"name": "plans", "location": "documents"}
    with pytest.raises(InvalidModelOutputError):
        validator.parse(
            _action("create_folder", {"name": "..", "location": "documents"})
        )
    with pytest.raises(InvalidModelOutputError):
        validator.parse(
            _action("create_folder", {"name": "x", "location": "C:\\Windows"})
        )


def test_open_file_rejects_executable_extension(validator):
    with pytest.raises(InvalidModelOutputError):
        validator.parse(_action("open_file", {"name": "evil.exe"}))
    parsed = validator.parse(_action("open_file", {"name": "notes.txt"}))
    assert parsed.arguments["name"] == "notes.txt"


def test_set_volume_is_clamped(validator):
    parsed = validator.parse(_action("set_volume", {"level": 500}))
    assert parsed.arguments["level"] == 100


def test_search_web_validates_query(validator):
    parsed = validator.parse(_action("search_web", {"query": "cats"}))
    assert parsed.arguments["query"] == "cats"


def test_oversized_argument_is_rejected(validator):
    with pytest.raises(InvalidModelOutputError):
        validator.parse(_action("search_web", {"query": "x" * 5000}))
