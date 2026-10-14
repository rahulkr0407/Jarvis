"""Tests for launching an allowlisted application.

`subprocess.Popen` is always mocked, so these tests never start a real program.
"""

from __future__ import annotations

import pytest

from actions.base import ActionResult, AppNotAllowedError
from actions.open_application import open_application
from tests.fakes import make_action_context


class FakeProcess:
    pid = 4321


def test_allowlisted_application_launches_with_explicit_argv(tmp_path, monkeypatch):
    exe = tmp_path / "notepad.exe"
    exe.write_text("", encoding="utf-8")
    context = make_action_context(
        tmp_path, application_allowlist={"notepad": (str(exe),)}
    )
    calls: list[tuple] = []

    def fake_popen(argv, **kwargs):
        calls.append((list(argv), kwargs))
        return FakeProcess()

    monkeypatch.setattr("actions.open_application.subprocess.Popen", fake_popen)

    result = open_application(context, {"target": "notepad"})

    assert isinstance(result, ActionResult)
    assert result.succeeded is True
    assert "4321" in result.detail
    assert calls == [([str(exe)], {"shell": False, "close_fds": True})]


def test_executable_extension_is_normalized(tmp_path, monkeypatch):
    exe = tmp_path / "notepad.exe"
    exe.write_text("", encoding="utf-8")
    context = make_action_context(
        tmp_path, application_allowlist={"notepad": (str(exe),)}
    )
    monkeypatch.setattr(
        "actions.open_application.subprocess.Popen",
        lambda argv, **kwargs: FakeProcess(),
    )
    assert open_application(context, {"target": "notepad.exe"}).succeeded is True


def test_non_allowlisted_application_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "actions.open_application.subprocess.Popen",
        lambda *a, **k: pytest.fail("must not launch"),
    )
    context = make_action_context(tmp_path)
    with pytest.raises(AppNotAllowedError):
        open_application(context, {"target": "powershell"})


def test_dry_run_never_launches(tmp_path, monkeypatch):
    exe = tmp_path / "notepad.exe"
    exe.write_text("", encoding="utf-8")
    context = make_action_context(
        tmp_path, application_allowlist={"notepad": (str(exe),)}, dry_run=True
    )
    monkeypatch.setattr(
        "actions.open_application.subprocess.Popen",
        lambda *a, **k: pytest.fail("dry run must not launch"),
    )
    result = open_application(context, {"target": "notepad"})
    assert result.succeeded is True
    assert "DRY-RUN" in result.detail


def test_bare_name_is_resolved_from_path(tmp_path, monkeypatch):
    fake = tmp_path / "notepad.exe"
    fake.write_text("", encoding="utf-8")
    context = make_action_context(
        tmp_path, application_allowlist={"notepad": ("notepad.exe",)}
    )
    monkeypatch.setattr(
        "actions.open_application.shutil.which", lambda name: str(fake)
    )
    monkeypatch.setattr(
        "actions.open_application.subprocess.Popen",
        lambda argv, **kwargs: FakeProcess(),
    )
    assert open_application(context, {"target": "notepad"}).succeeded is True


def test_missing_executable_is_reported(tmp_path, monkeypatch):
    context = make_action_context(
        tmp_path, application_allowlist={"notepad": ("definitely_absent_binary",)}
    )
    monkeypatch.setattr(
        "actions.open_application.shutil.which", lambda name: None
    )
    with pytest.raises(AppNotAllowedError):
        open_application(context, {"target": "notepad"})
