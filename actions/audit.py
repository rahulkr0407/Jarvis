"""Audit logging for executed actions — without ever storing secrets.

Every action that runs through the executor is recorded as one JSON line. The
log is deliberately defensive:

* Argument values are scrubbed before they are written. URLs keep only their
  scheme and host (path, query, fragment, and any embedded credentials are
  dropped), and any key that looks sensitive (password, token, secret, ...) is
  replaced with ``"[redacted]"``.
* Writing is best-effort. A missing directory, a full disk, or a permissions
  error must never break the assistant, so failures are swallowed.

:class:`NullAuditLogger` is a no-op used by tests and by dry runs where no file
should be touched.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

#: Substrings that mark an argument key as sensitive. Matching is case-folded.
_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "token",
    "secret",
    "apikey",
    "api_key",
    "credential",
)

#: Argument keys whose values are URLs and should be reduced to scheme + host.
_URL_KEYS = ("url", "uri", "link")


def _scrub_url(value: str) -> str:
    """Reduce a URL to ``scheme://host`` so secrets in it are never logged."""
    try:
        parts = urlsplit(value)
    except ValueError:
        return "[unparseable-url]"
    host = parts.hostname or ""
    if not parts.scheme or not host:
        return "[unparseable-url]"
    return f"{parts.scheme}://{host}"


def redact_arguments(arguments: Mapping[str, object]) -> dict[str, object]:
    """Return a copy of ``arguments`` safe to persist in an audit log."""
    cleaned: dict[str, object] = {}
    for key, value in dict(arguments).items():
        lowered = str(key).lower()
        if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
            cleaned[str(key)] = "[redacted]"
        elif (
            lowered in _URL_KEYS
            and isinstance(value, str)
            and "://" in value
        ):
            cleaned[str(key)] = _scrub_url(value)
        else:
            cleaned[key] = value
    return cleaned


class AuditLogger(Protocol):
    """The minimal audit interface the action layer depends on."""

    def record(
        self,
        action_name: str,
        arguments: Mapping[str, object],
        *,
        succeeded: bool,
        detail: str,
        dry_run: bool,
    ) -> None:
        """Persist one audit record. Must never raise."""


class NullAuditLogger:
    """An audit logger that records nothing (used by tests and dry runs)."""

    def record(
        self,
        action_name: str,
        arguments: Mapping[str, object],
        *,
        succeeded: bool,
        detail: str,
        dry_run: bool,
    ) -> None:
        return None


class FileAuditLogger:
    """Appends JSON-line audit records to a file, best-effort."""

    def __init__(self, path: Path | str, *, clock=time.time) -> None:
        self._path = Path(path)
        self._clock = clock

    @property
    def path(self) -> Path:
        """The file records are written to."""
        return self._path

    def record(
        self,
        action_name: str,
        arguments: Mapping[str, object],
        *,
        succeeded: bool,
        detail: str,
        dry_run: bool,
    ) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "time": self._clock(),
                "action": action_name,
                "arguments": redact_arguments(arguments),
                "succeeded": bool(succeeded),
                "detail": detail,
                "dry_run": bool(dry_run),
            }
            line = json.dumps(entry, default=str, sort_keys=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:
            # Auditing must never be able to break an action or crash the app.
            pass
