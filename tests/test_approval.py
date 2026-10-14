"""Tests for approval requests: exact binding, freezing, expiry, uniqueness."""

from __future__ import annotations

import pytest

from security.approval import create_approval, fingerprint


def test_fingerprint_is_stable_for_equal_input():
    assert fingerprint("open_application", {"target": "notepad"}) == fingerprint(
        "open_application", {"target": "notepad"}
    )


def test_fingerprint_changes_when_action_changes():
    a = fingerprint("open_application", {"target": "notepad"})
    b = fingerprint("set_volume", {"target": "notepad"})
    assert a != b


def test_fingerprint_changes_when_argument_value_changes():
    a = fingerprint("set_volume", {"level": 10})
    b = fingerprint("set_volume", {"level": 11})
    assert a != b


def test_fingerprint_is_order_independent_for_keys():
    a = fingerprint("x", {"a": 1, "b": 2})
    b = fingerprint("x", {"b": 2, "a": 1})
    assert a == b


def test_create_approval_freezes_arguments():
    original = {"target": "notepad"}
    approval = create_approval("open_application", original, now=0.0, ttl=30.0)
    original["target"] = "malware.exe"
    assert approval.arguments["target"] == "notepad"
    with pytest.raises(TypeError):
        approval.arguments["target"] = "malware.exe"  # read-only mapping


def test_create_approval_sets_deadline():
    approval = create_approval("open_application", {}, now=100.0, ttl=30.0)
    assert approval.created_at == 100.0
    assert approval.expires_at == 130.0
    assert not approval.is_expired(129.9)
    assert approval.is_expired(130.0)


def test_tokens_are_unique_and_nonempty():
    first = create_approval("open_application", {}, now=0.0, ttl=30.0)
    second = create_approval("open_application", {}, now=0.0, ttl=30.0)
    assert first.token and second.token
    assert first.token != second.token


def test_stored_fingerprint_matches_recomputation():
    approval = create_approval(
        "set_volume", {"level": 50}, now=0.0, ttl=30.0
    )
    assert approval.fingerprint == fingerprint("set_volume", {"level": 50})
