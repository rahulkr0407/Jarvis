"""Tests for opening a permitted, non-executable file.

`os.startfile` is always mocked, so no real file is ever opened.
"""

from __future__ import annotations

import pytest

from actions.base import ActionError, FileTypeNotAllowedError, PathNotPermittedError
from actions.open_file import open_file
from tests.fakes import make_action_context


def _patch_opener(monkeypatch, opened):
    monkeypatch.setattr(
        "actions.open_file._open_with_default_app",
        lambda path: opened.append(path),
    )


def test_opens_safe_file_by_name_and_location(tmp_path, monkeypatch):
    context = make_action_context(tmp_path)
    docs = context.folder_map["documents"]
    docs.mkdir(parents=True)
    (docs / "notes.txt").write_text("hi", encoding="utf-8")
    opened: list = []
    _patch_opener(monkeypatch, opened)

    result = open_file(context, {"name": "notes.txt", "location": "documents"})
    assert result.succeeded is True
    assert opened == [(docs / "notes.txt").resolve()]


def test_opens_file_by_path(tmp_path, monkeypatch):
    context = make_action_context(tmp_path)
    docs = context.folder_map["documents"]
    docs.mkdir(parents=True)
    target = docs / "notes.md"
    target.write_text("hi", encoding="utf-8")
    opened: list = []
    _patch_opener(monkeypatch, opened)

    result = open_file(context, {"path": str(target)})
    assert result.succeeded is True
    assert opened == [target.resolve()]


def test_executable_extension_is_refused(tmp_path, monkeypatch):
    context = make_action_context(tmp_path)
    docs = context.folder_map["documents"]
    docs.mkdir(parents=True)
    (docs / "evil.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "actions.open_file._open_with_default_app",
        lambda *a, **k: pytest.fail("must not open"),
    )
    with pytest.raises(FileTypeNotAllowedError):
        open_file(context, {"name": "evil.exe", "location": "documents"})


def test_path_outside_workspace_is_refused(tmp_path, monkeypatch):
    context = make_action_context(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(PathNotPermittedError):
        open_file(context, {"path": str(outside)})


def test_missing_file_is_reported(tmp_path):
    context = make_action_context(tmp_path)
    context.folder_map["documents"].mkdir(parents=True)
    with pytest.raises(ActionError):
        open_file(context, {"name": "absent.txt", "location": "documents"})


def test_dry_run_does_not_open(tmp_path, monkeypatch):
    context = make_action_context(tmp_path, dry_run=True)
    docs = context.folder_map["documents"]
    docs.mkdir(parents=True)
    (docs / "notes.txt").write_text("hi", encoding="utf-8")
    monkeypatch.setattr(
        "actions.open_file._open_with_default_app",
        lambda *a, **k: pytest.fail("dry run must not open"),
    )
    result = open_file(context, {"name": "notes.txt", "location": "documents"})
    assert result.succeeded is True
    assert "DRY-RUN" in result.detail
