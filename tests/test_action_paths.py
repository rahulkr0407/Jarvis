"""Tests for path confinement (the guard against traversal and escapes)."""

from __future__ import annotations

import os

import pytest

from actions.base import PathNotPermittedError
from actions.paths import find_permitted_root, resolve_within


def test_relative_name_resolves_inside_root(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    resolved = resolve_within(root, "notes")
    assert resolved == (root / "notes").resolve()
    assert resolved.is_relative_to(root.resolve())


def test_nested_relative_path_resolves_inside_root(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    resolved = resolve_within(root, "a/b/c.txt")
    assert resolved.is_relative_to(root.resolve())


def test_parent_traversal_is_rejected(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    with pytest.raises(PathNotPermittedError):
        resolve_within(root, "../outside")


def test_absolute_path_outside_root_is_rejected(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(PathNotPermittedError):
        resolve_within(root, outside)


def test_absolute_path_inside_root_is_allowed(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    inside = root / "file.txt"
    assert resolve_within(root, inside) == inside.resolve()


def test_symlink_escape_is_rejected(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")
    link = root / "link.txt"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not permitted in this environment")

    with pytest.raises(PathNotPermittedError):
        resolve_within(root, "link.txt")


def test_find_permitted_root_accepts_member(tmp_path):
    root = tmp_path / "workspace"
    (root / "documents").mkdir(parents=True)
    found = find_permitted_root(root / "documents" / "x.txt", [root])
    assert found == (root / "documents" / "x.txt").resolve()


def test_find_permitted_root_rejects_outsider(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    with pytest.raises(PathNotPermittedError):
        find_permitted_root(tmp_path / "other.txt", [root])
