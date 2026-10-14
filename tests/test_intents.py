"""Tests for the intent vocabulary and its argument validators.

The validators are the choke point where untrusted text is turned into bounded,
safe argument values. These tests pin down that paths, traversal, control
characters, and over-long values can never pass.
"""

from __future__ import annotations

import pytest

from core.intents import (
    Intent,
    IntentName,
    resolve_safe_root,
    validate_app_target,
    validate_folder_name,
    validate_search_query,
)


def test_intent_name_covers_the_full_vocabulary():
    assert {name.value for name in IntentName} == {
        "open_application",
        "open_url",
        "open_file",
        "search_web",
        "tell_time",
        "list_directory",
        "create_folder",
        "cancel_command",
        "unknown",
    }


def test_intent_arguments_are_read_only():
    intent = Intent("open_application", {"target": "notepad"})
    with pytest.raises(TypeError):
        intent.arguments["target"] = "other"  # type: ignore[index]


def test_intent_is_frozen():
    intent = Intent("open_application", {"target": "notepad"})
    with pytest.raises(Exception):
        intent.action_name = "set_volume"  # type: ignore[misc]


@pytest.mark.parametrize("value", ["notepad", "Google Chrome", "vs-code", "app.v2"])
def test_app_target_accepts_names(value):
    assert validate_app_target(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "C:\\Windows\\System32",
        "../etc/passwd",
        "/bin/sh",
        "..",
        "folder/../secret",
        "a" * 100,
    ],
)
def test_app_target_rejects_paths_and_junk(value):
    assert validate_app_target(value) is None


def test_search_query_is_stripped_and_length_capped():
    assert validate_search_query("  cats  ") == "cats"
    assert validate_search_query("x" * 500) == "x" * 200
    assert validate_search_query("") is None
    assert validate_search_query("   ") is None


@pytest.mark.parametrize("value", ["plans", "My Plans", "work-2026", "notes.v2"])
def test_folder_name_accepts_simple_names(value):
    assert validate_folder_name(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "a/b",
        "a\\b",
        "..",
        "foo/../bar",
        "bad\x00name",
        "a" * 100,
    ],
)
def test_folder_name_rejects_separators_traversal_and_controls(value):
    assert validate_folder_name(value) is None


@pytest.mark.parametrize(
    "value,expected",
    [
        ("home", "home"),
        ("Desktop", "desktop"),
        ("  downloads ", "downloads"),
        ("my documents", "documents"),
        ("the desktop", "desktop"),
    ],
)
def test_resolve_safe_root_accepts_known_locations(value, expected):
    assert resolve_safe_root(value) == expected


@pytest.mark.parametrize(
    "value",
    ["C:\\Windows", "/etc", "../../etc", "temp", "system32", "", "program files"],
)
def test_resolve_safe_root_rejects_everything_else(value):
    assert resolve_safe_root(value) is None
