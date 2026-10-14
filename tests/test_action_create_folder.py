"""Tests for creating a folder inside a permitted location."""

from __future__ import annotations

import pytest

from actions.base import ActionError, PathNotPermittedError
from actions.create_folder import create_folder
from tests.fakes import make_action_context


def test_creates_folder_in_permitted_location(tmp_path):
    context = make_action_context(tmp_path)
    result = create_folder(context, {"name": "plans", "location": "documents"})
    assert result.succeeded is True
    assert (context.folder_map["documents"] / "plans").is_dir()


def test_existing_folder_reports_not_created(tmp_path):
    context = make_action_context(tmp_path)
    create_folder(context, {"name": "plans", "location": "documents"})
    second = create_folder(context, {"name": "plans", "location": "documents"})
    assert second.succeeded is False
    assert "already exists" in second.detail


def test_traversal_name_is_refused(tmp_path):
    context = make_action_context(tmp_path)
    with pytest.raises(ActionError):
        create_folder(context, {"name": "../escape", "location": "documents"})
    assert not (tmp_path / "escape").exists()


def test_separator_name_is_refused(tmp_path):
    context = make_action_context(tmp_path)
    with pytest.raises(ActionError):
        create_folder(context, {"name": "a/b", "location": "documents"})


def test_unpermitted_location_is_refused(tmp_path):
    context = make_action_context(tmp_path)
    with pytest.raises(PathNotPermittedError):
        create_folder(context, {"name": "plans", "location": "C:\\Windows"})


def test_dry_run_creates_nothing(tmp_path):
    context = make_action_context(tmp_path, dry_run=True)
    result = create_folder(context, {"name": "plans", "location": "documents"})
    assert result.succeeded is True
    assert "DRY-RUN" in result.detail
    assert not (context.folder_map["documents"] / "plans").exists()


def test_file_with_same_name_is_reported(tmp_path):
    context = make_action_context(tmp_path)
    docs = context.folder_map["documents"]
    docs.mkdir(parents=True)
    (docs / "plans").write_text("not a folder", encoding="utf-8")
    with pytest.raises(ActionError):
        create_folder(context, {"name": "plans", "location": "documents"})
