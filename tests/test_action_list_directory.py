"""Tests for reading a permitted directory's contents."""

from __future__ import annotations

import pytest

from actions.base import ActionError, PathNotPermittedError
from actions.list_directory import list_directory
from tests.fakes import make_action_context


def test_lists_entries_for_a_permitted_location(tmp_path):
    context = make_action_context(tmp_path)
    docs = context.folder_map["documents"]
    docs.mkdir(parents=True)
    (docs / "a.txt").write_text("a", encoding="utf-8")
    (docs / "b.txt").write_text("b", encoding="utf-8")
    (docs / "sub").mkdir()

    result = list_directory(context, {"location": "documents"})
    assert result.succeeded is True
    assert "3 entries" in result.detail
    assert "a.txt" in result.detail
    assert "sub/" in result.detail


def test_empty_directory(tmp_path):
    context = make_action_context(tmp_path)
    context.folder_map["documents"].mkdir(parents=True)
    result = list_directory(context, {"location": "documents"})
    assert result.succeeded is True
    assert "empty" in result.detail


def test_missing_directory_is_reported(tmp_path):
    context = make_action_context(tmp_path)
    with pytest.raises(ActionError):
        list_directory(context, {"location": "documents"})


def test_unpermitted_location_is_refused(tmp_path):
    context = make_action_context(tmp_path)
    with pytest.raises(PathNotPermittedError):
        list_directory(context, {"location": "C:\\Windows"})


def test_entries_are_capped(tmp_path):
    context = make_action_context(tmp_path, max_directory_entries=2)
    docs = context.folder_map["documents"]
    docs.mkdir(parents=True)
    for index in range(5):
        (docs / f"file{index}.txt").write_text("x", encoding="utf-8")

    result = list_directory(context, {"location": "documents"})
    assert "5 entries" in result.detail
    assert "showing first 2" in result.detail


def test_dry_run_does_not_read(tmp_path):
    context = make_action_context(tmp_path, dry_run=True)
    context.folder_map["documents"].mkdir(parents=True)
    result = list_directory(context, {"location": "documents"})
    assert result.succeeded is True
    assert "DRY-RUN" in result.detail
