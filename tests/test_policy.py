"""Tests for the deny-by-default action policy."""

from __future__ import annotations

import pytest

from config import settings
from security.actions import ActionRegistry, ActionSpec
from security.policy import ActionPolicy, PolicyViolation, build_default_policy


def test_default_policy_allows_every_configured_action():
    policy = build_default_policy()
    for name in settings.ALLOWED_ACTIONS:
        assert policy.is_allowed(name)


def test_default_policy_denies_unknown_actions():
    policy = build_default_policy()
    assert not policy.is_allowed("format_c_drive")
    assert not policy.is_allowed("run_shell")
    assert not policy.is_allowed("")


def test_empty_registry_denies_everything():
    policy = ActionPolicy(ActionRegistry())
    assert policy.allowed_actions() == ()
    assert not policy.is_allowed("open_application")


def test_require_allowed_raises_and_carries_action_name():
    policy = build_default_policy()
    with pytest.raises(PolicyViolation) as info:
        policy.require_allowed("delete_everything")
    assert info.value.action_name == "delete_everything"


def test_require_allowed_is_silent_for_known_action():
    policy = build_default_policy()
    policy.require_allowed(settings.ALLOWED_ACTIONS[0])


def test_registry_is_exact_match():
    registry = ActionRegistry([ActionSpec(name="open_application", description="x")])
    assert registry.is_registered("open_application")
    assert not registry.is_registered("Open_Application")
    assert not registry.is_registered("open_application ")
