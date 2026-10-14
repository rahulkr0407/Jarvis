"""Tests for the allowlist-only command router."""

from __future__ import annotations

import pytest

from core.command_router import CommandRouter


def test_open_variants_route_to_open_application():
    router = CommandRouter()
    for phrase in ("open notepad", "launch notepad", "start notepad"):
        intent = router.route(phrase)
        assert intent is not None
        assert intent.action_name == "open_application"
        assert intent.arguments["target"] == "notepad"


def test_volume_is_clamped_to_0_100():
    router = CommandRouter()
    assert router.route("set volume to 150").arguments["level"] == 100
    assert router.route("volume 0").arguments["level"] == 0
    assert router.route("volume 42").arguments["level"] == 42


def test_search_variants():
    router = CommandRouter()
    for phrase in ("search for quantum physics", "google quantum physics", "look up quantum physics"):
        intent = router.route(phrase)
        assert intent is not None
        assert intent.action_name == "search_web"
        assert intent.arguments["query"] == "quantum physics"


def test_search_query_is_length_capped():
    router = CommandRouter()
    intent = router.route("search " + "x" * 500)
    assert intent is not None
    assert len(intent.arguments["query"]) == 200


@pytest.mark.parametrize(
    "phrase",
    [
        "hello there",
        "do my homework",
        "delete system32",
        "run format c:",
        "shutdown the computer",
    ],
)
def test_unrecognized_text_is_not_routed(phrase):
    assert CommandRouter().route(phrase) is None


def test_empty_and_whitespace_are_not_routed():
    router = CommandRouter()
    assert router.route("") is None
    assert router.route("     ") is None


def test_non_allowlisted_action_is_refused():
    router = CommandRouter(allowed_actions=())
    assert router.route("open notepad") is None
    assert router.route("set volume 20") is None


def test_app_target_rejects_paths_and_separators():
    router = CommandRouter()
    assert router.route("open C:\\Windows\\System32") is None
    assert router.route("open ../etc/passwd") is None
    assert router.route("open /bin/sh") is None


def test_routing_is_case_and_spacing_insensitive():
    intent = CommandRouter().route("  OPEN    NotePad  ")
    assert intent is not None
    assert intent.arguments["target"] == "notepad"


# --------------------------------------------------------------------------- #
# Phase 3 intents
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "phrase",
    [
        "what time is it",
        "what's the time",
        "what is the time now",
        "tell me the time",
        "current time",
        "time",
    ],
)
def test_time_variants_route_to_tell_time(phrase):
    intent = CommandRouter().route(phrase)
    assert intent is not None
    assert intent.action_name == "tell_time"
    assert dict(intent.arguments) == {}


def test_list_directory_defaults_to_home():
    intent = CommandRouter().route("list files")
    assert intent is not None
    assert intent.action_name == "list_directory"
    assert intent.arguments["location"] == "home"


@pytest.mark.parametrize(
    "phrase,location",
    [
        ("list files in downloads", "downloads"),
        ("show the folder in documents", "documents"),
        ("what's in my desktop", "desktop"),
        ("list directory", "home"),
    ],
)
def test_list_directory_with_location(phrase, location):
    intent = CommandRouter().route(phrase)
    assert intent is not None
    assert intent.action_name == "list_directory"
    assert intent.arguments["location"] == location


@pytest.mark.parametrize(
    "phrase",
    [
        "list files in C:\\Windows",
        "show files in /etc",
        "what's in ../../secrets",
        "list files in somewhere",
    ],
)
def test_list_directory_rejects_unsafe_location(phrase):
    assert CommandRouter().route(phrase) is None


def test_create_folder_default_location():
    intent = CommandRouter().route("create folder plans")
    assert intent is not None
    assert intent.action_name == "create_folder"
    assert intent.arguments["name"] == "plans"
    assert intent.arguments["location"] == "home"


@pytest.mark.parametrize(
    "phrase,name,location",
    [
        ("create a folder called plans in documents", "plans", "documents"),
        ("make folder work-2026 in desktop", "work-2026", "desktop"),
        ("new directory notes under downloads", "notes", "downloads"),
    ],
)
def test_create_folder_with_location(phrase, name, location):
    intent = CommandRouter().route(phrase)
    assert intent is not None
    assert intent.action_name == "create_folder"
    assert intent.arguments["name"] == name
    assert intent.arguments["location"] == location


@pytest.mark.parametrize(
    "phrase",
    [
        "create folder foo/../bar",
        "create folder foo\\bar",
        "create folder ..",
        "create folder plans in C:\\Windows",
        "create folder plans in ../../etc",
    ],
)
def test_create_folder_rejects_unsafe_name_or_location(phrase):
    assert CommandRouter().route(phrase) is None


@pytest.mark.parametrize(
    "phrase", ["cancel", "cancel that", "never mind", "stop", "abort", "forget it"]
)
def test_cancel_variants_route_to_cancel_command(phrase):
    intent = CommandRouter().route(phrase)
    assert intent is not None
    assert intent.action_name == "cancel_command"
    assert dict(intent.arguments) == {}


def test_cancel_is_not_gated_by_the_action_allowlist():
    # Cancel is a control command, not an action, so it survives an empty
    # allowlist; the proposal actions do not.
    router = CommandRouter(allowed_actions=())
    assert router.route("stop") is not None
    assert router.route("what time is it") is None
    assert router.route("list files") is None
    assert router.route("create folder plans") is None


@pytest.mark.parametrize(
    "phrase",
    [
        "open notepad && del *",
        "open notepad; shutdown /s",
        "create folder x | format c:",
        "open C:\\Windows\\System32\\cmd.exe",
    ],
)
def test_shell_metacharacters_never_pass(phrase):
    # At most a bounded, safe intent; never a raw command, and anything with a
    # separator or shell metacharacter is refused outright.
    intent = CommandRouter().route(phrase)
    assert intent is None or intent.action_name in {
        "open_application",
        "open_url",
        "open_file",
        "search_web",
        "tell_time",
        "list_directory",
        "create_folder",
        "cancel_command",
    }
    if intent is not None:
        for value in intent.arguments.values():
            assert ";" not in str(value)
            assert "&" not in str(value)
            assert "|" not in str(value)


# --------------------------------------------------------------------------- #
# Phase 4 intents
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "phrase,url",
    [
        ("open https://example.com", "https://example.com"),
        ("go to http://example.com/page", "http://example.com/page"),
        ("visit www.example.com", "www.example.com"),
        ("go to example.com", "example.com"),
    ],
)
def test_open_url_variants(phrase, url):
    intent = CommandRouter().route(phrase)
    assert intent is not None
    assert intent.action_name == "open_url"
    assert intent.arguments["url"] == url


def test_open_url_is_distinct_from_open_application():
    assert CommandRouter().route("open notepad").action_name == "open_application"
    assert CommandRouter().route("open https://example.com").action_name == "open_url"


@pytest.mark.parametrize(
    "phrase,name,location",
    [
        ("open file notes.txt", "notes.txt", "home"),
        ("open notes.txt", "notes.txt", "home"),
        ("open report.md in documents", "report.md", "documents"),
        ("view image.png in desktop", "image.png", "desktop"),
    ],
)
def test_open_file_variants(phrase, name, location):
    intent = CommandRouter().route(phrase)
    assert intent is not None
    assert intent.action_name == "open_file"
    assert intent.arguments["name"] == name
    assert intent.arguments["location"] == location


@pytest.mark.parametrize(
    "phrase",
    ["open evil.exe", "open file payload.bat", "open script.ps1"],
)
def test_open_file_rejects_unsafe_extensions(phrase):
    # A dangerous extension must not even produce a proposal.
    assert CommandRouter().route(phrase) is None


def test_non_allowlisted_application_is_not_proposed():
    router = CommandRouter()
    assert router.route("open powershell") is None
    assert router.route("open cmd") is None


def test_custom_application_allowlist_is_respected():
    router = CommandRouter(application_allowlist={"customapp": ("customapp.exe",)})
    intent = router.route("open customapp")
    assert intent is not None
    assert intent.arguments["target"] == "customapp"
    assert router.route("open notepad") is None


def test_open_application_allowed_by_default_allowlist():
    intent = CommandRouter().route("launch notepad")
    assert intent is not None
    assert intent.action_name == "open_application"

