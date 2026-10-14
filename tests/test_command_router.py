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
