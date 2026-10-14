"""Open an approved URL in the user's default browser.

Only ``http`` and ``https`` are allowed. The URL is parsed rather than trusted:

* A missing scheme is filled in with ``https`` **only** for something that looks
  like a bare host (``example.com``); anything else without a scheme is refused.
* Non-http(s) schemes — ``javascript:``, ``file:``, ``data:``, ``ftp:`` — are
  refused outright.
* URLs carrying embedded credentials (``https://user:pass@host``) are refused.

The browser is opened with :func:`webbrowser.open`, which never builds a shell
command string.
"""

from __future__ import annotations

import webbrowser
from collections.abc import Mapping
from urllib.parse import urlsplit

from actions.base import ActionResult, ActionContext, UrlNotAllowedError

_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _looks_like_host(text: str) -> bool:
    if any(ch in text for ch in " \t\r\n"):
        return False
    host = text.split("/", 1)[0]
    labels = host.split(".")
    if len(labels) < 2:
        return False
    return all(label for label in labels)


def normalize_and_validate_url(raw: str) -> str:
    """Return a safe absolute http(s) URL, or raise :class:`UrlNotAllowedError`."""
    text = (raw or "").strip()
    if not text:
        raise UrlNotAllowedError("No URL was provided.")

    parts = urlsplit(text)
    scheme = parts.scheme.lower()
    if not scheme:
        if _looks_like_host(text):
            text = "https://" + text
            parts = urlsplit(text)
            scheme = parts.scheme.lower()
        else:
            raise UrlNotAllowedError("That does not look like a web address.")

    if scheme not in _ALLOWED_SCHEMES:
        raise UrlNotAllowedError(
            f"URL scheme '{scheme}' is not allowed; use http or https."
        )
    if not parts.netloc:
        raise UrlNotAllowedError("The URL is missing a host.")
    if parts.username or parts.password:
        raise UrlNotAllowedError("URLs with embedded credentials are not allowed.")
    return text


def _display(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def open_url(
    context: ActionContext, arguments: Mapping[str, object]
) -> ActionResult:
    """Open an approved URL in the default browser."""
    safe_url = normalize_and_validate_url(str(arguments.get("url", "")))

    if context.dry_run:
        return ActionResult(True, f"DRY-RUN: would open {_display(safe_url)}.")

    webbrowser.open(safe_url, new=2)
    return ActionResult(True, f"Opened {_display(safe_url)} in the default browser.")
