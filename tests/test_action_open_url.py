"""Tests for opening an approved URL (scheme validation + default browser)."""

from __future__ import annotations

import pytest

from actions.base import ActionResult, UrlNotAllowedError
from actions.open_url import normalize_and_validate_url, open_url
from tests.fakes import make_action_context


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://example.com", "https://example.com"),
        ("http://example.com", "http://example.com"),
        ("https://example.com/path?q=1", "https://example.com/path?q=1"),
        ("example.com", "https://example.com"),
        ("www.example.com", "https://www.example.com"),
    ],
)
def test_valid_urls_are_accepted(raw, expected):
    assert normalize_and_validate_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "javascript:alert(1)",
        "file:///C:/Windows/System32",
        "data:text/html,<script>",
        "ftp://example.com",
        "not a url",
        "https://user:pass@example.com",
    ],
)
def test_unsafe_urls_are_refused(raw):
    with pytest.raises(UrlNotAllowedError):
        normalize_and_validate_url(raw)


def test_open_url_calls_browser(tmp_path, monkeypatch):
    context = make_action_context(tmp_path)
    opened: list = []
    monkeypatch.setattr(
        "actions.open_url.webbrowser.open",
        lambda url, new=0: opened.append((url, new)),
    )
    result = open_url(context, {"url": "https://example.com/page?x=1"})
    assert result.succeeded is True
    assert opened == [("https://example.com/page?x=1", 2)]
    assert "example.com" in result.detail
    assert "x=1" not in result.detail  # query is not echoed in the result


def test_open_url_dry_run_never_opens(tmp_path, monkeypatch):
    context = make_action_context(tmp_path, dry_run=True)
    monkeypatch.setattr(
        "actions.open_url.webbrowser.open",
        lambda *a, **k: pytest.fail("dry run must not open a browser"),
    )
    result = open_url(context, {"url": "https://example.com"})
    assert result.succeeded is True
    assert "DRY-RUN" in result.detail


def test_open_url_rejects_bad_scheme(tmp_path):
    context = make_action_context(tmp_path)
    with pytest.raises(UrlNotAllowedError):
        open_url(context, {"url": "javascript:alert(1)"})
