"""Integration tests: controller + real action registry.

These exercise the full path (propose -> approve -> execute) with the real
executor, but with a sandbox workspace and ``dry_run`` or mocked OS calls, so
nothing real is launched and no user files are touched.
"""

from __future__ import annotations

import pytest

from actions.base import ActionResult, build_action_context
from actions.registry import build_executor
from core.controller import (
    AssistantController,
    NoPendingApprovalError,
)
from core.states import AssistantState
from security.policy import build_default_policy
from tests.fakes import make_action_context


def make_controller(context) -> AssistantController:
    return AssistantController(
        build_default_policy(), executor=build_executor(context)
    )


def test_approved_dry_run_action_reports_success(tmp_path):
    context = make_action_context(tmp_path, dry_run=True)
    controller = make_controller(context)
    controller.activate()
    controller.propose_action("open_url", {"url": "https://example.com"})
    outcome = controller.approve()
    assert outcome.succeeded is True
    assert "DRY-RUN" in outcome.detail
    assert controller.state is AssistantState.IDLE


def test_approved_real_create_folder_creates_it_in_workspace(tmp_path):
    context = make_action_context(tmp_path)
    controller = make_controller(context)
    controller.activate()
    controller.propose_action(
        "create_folder", {"name": "plans", "location": "documents"}
    )
    outcome = controller.approve()
    assert outcome.succeeded is True
    assert (context.folder_map["documents"] / "plans").is_dir()


def test_cancel_prevents_a_pending_create_folder(tmp_path):
    context = make_action_context(tmp_path)
    controller = make_controller(context)
    controller.activate()
    controller.propose_action(
        "create_folder", {"name": "plans", "location": "documents"}
    )
    controller.cancel()
    with pytest.raises(NoPendingApprovalError):
        controller.approve()
    assert not (context.folder_map["documents"] / "plans").exists()


def test_unsafe_action_is_reported_not_crashed(tmp_path):
    context = make_action_context(tmp_path)
    controller = make_controller(context)
    controller.activate()
    controller.propose_action(
        "create_folder", {"name": "../escape", "location": "documents"}
    )
    outcome = controller.approve()
    assert outcome.started is True
    assert outcome.succeeded is False
    assert not (tmp_path / "escape").exists()


def test_controller_honors_a_failed_action_result(tmp_path):
    def executor(action_name, arguments):
        return ActionResult(False, "no go")

    controller = AssistantController(build_default_policy(), executor=executor)
    controller.activate()
    controller.propose_action("open_url", {"url": "https://example.com"})
    outcome = controller.approve()
    assert outcome.succeeded is False
    assert outcome.detail == "no go"


def test_controller_success_detail_from_result(tmp_path):
    def executor(action_name, arguments):
        return ActionResult(True, "did the thing")

    controller = AssistantController(build_default_policy(), executor=executor)
    controller.activate()
    controller.propose_action("open_url", {"url": "https://example.com"})
    outcome = controller.approve()
    assert outcome.succeeded is True
    assert outcome.detail == "did the thing"


def test_default_context_is_sandboxed():
    # The default context must never point at a real user folder.
    context = build_action_context(dry_run=True)
    for path in context.permitted_directories:
        assert "workspace" in str(path).lower()
