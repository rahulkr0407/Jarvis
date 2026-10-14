"""Tests for the action dispatcher: dispatch, timeouts, audit, dry-run."""

from __future__ import annotations

import time

import pytest

from actions.base import ActionResult
from actions.registry import ACTION_HANDLERS, build_executor
from actions.audit import redact_arguments
from core.controller import ActionNotImplementedError
from tests.fakes import make_action_context


def test_dispatches_open_url(tmp_path, monkeypatch):
    context = make_action_context(tmp_path, dry_run=True)
    executor = build_executor(context)
    result = executor("open_url", {"url": "https://example.com"})
    assert isinstance(result, ActionResult)
    assert result.succeeded is True
    assert "DRY-RUN" in result.detail


def test_unknown_action_raises_not_implemented(tmp_path):
    context = make_action_context(tmp_path)
    executor = build_executor(context)
    with pytest.raises(ActionNotImplementedError):
        executor("format_c_drive", {})


def test_allowlisted_but_unimplemented_action_raises(tmp_path):
    context = make_action_context(tmp_path)
    executor = build_executor(context)
    with pytest.raises(ActionNotImplementedError):
        executor("set_volume", {"level": 10})


def test_action_error_becomes_failed_result(tmp_path, monkeypatch):
    context = make_action_context(tmp_path)
    executor = build_executor(context)
    result = executor("open_url", {"url": "javascript:alert(1)"})
    assert result.succeeded is False
    assert "scheme" in result.detail.lower()


def test_successful_action_is_audited(tmp_path, monkeypatch):
    from tests.fakes import RecordingAuditLogger

    audit = RecordingAuditLogger()
    context = make_action_context(tmp_path, dry_run=True, audit=audit)
    executor = build_executor(context)
    executor("open_url", {"url": "https://example.com"})
    assert len(audit.records) == 1
    record = audit.records[0]
    assert record["action"] == "open_url"
    assert record["succeeded"] is True
    assert record["dry_run"] is True


def test_timeout_returns_clear_failure(tmp_path, monkeypatch):
    context = make_action_context(tmp_path, timeout_seconds=0.05)
    executor = build_executor(context)

    def slow(context, arguments):
        time.sleep(0.5)
        return ActionResult(True, "too late")

    monkeypatch.setitem(ACTION_HANDLERS, "open_url", slow)
    result = executor("open_url", {"url": "https://example.com"})
    assert result.succeeded is False
    assert "time limit" in result.detail


def test_audit_redacts_url_queries_and_secret_keys():
    cleaned = redact_arguments(
        {"url": "https://example.com/path?token=abc123", "password": "hunter2"}
    )
    assert cleaned["url"] == "https://example.com"
    assert cleaned["password"] == "[redacted]"
    assert "abc123" not in str(cleaned)
    assert "hunter2" not in str(cleaned)
