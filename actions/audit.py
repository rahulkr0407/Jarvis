"""Audit logging for executed actions — without ever storing secrets.

Every action that runs through the executor is recorded as one JSON line. The
log is deliberately defensive:

* Argument values are scrubbed before they are written. URLs keep only their
  scheme and host (path, query, fragment, and any embedded credentials are
  dropped), and any key that looks sensitive (password, token, secret, ...) is
  replaced with ``"[redacted]"``.
* Writing is best-effort. A missing directory, a full disk, or a permissions
  error must never break the assistant, so failures are swallowed.
* The file is rotated so it cannot grow without bound: once it would exceed
  ``max_bytes`` it is renamed to ``<name>.1`` (and older backups shifted up),
  keeping at most ``backup_count`` old files.

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

from config import settings

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
    """Appends JSON-line audit records to a rotating file, best-effort."""

    def __init__(
        self,
        path: Path | str,
        *,
        clock=time.time,
        max_bytes: int = settings.AUDIT_LOG_MAX_BYTES,
        backup_count: int = settings.AUDIT_LOG_BACKUP_COUNT,
    ) -> None:
        self._path = Path(path)
        self._clock = clock
        self._max_bytes = max(0, int(max_bytes))
        self._backup_count = max(0, int(backup_count))

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
            self._rotate_if_needed(len(line) + 1)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:
            # Auditing must never be able to break an action or crash the app.
            pass

    def _rotate_if_needed(self, incoming: int) -> None:
        """Shift backups and start a fresh file when the limit would be hit."""
        if self._max_bytes <= 0 or self._backup_count <= 0:
            return
        try:
            if not self._path.exists():
                return
            if self._path.stat().st_size + incoming <= self._max_bytes:
                return
        except OSError:
            return

        # Drop the oldest backup, then shift .N -> .N+1, and finally current -> .1.
        try:
            oldest = self._path.with_name(f"{self._path.name}.{self._backup_count}")
            if oldest.exists():
                oldest.unlink()
            for index in range(self._backup_count - 1, 0, -1):
                source = self._path.with_name(f"{self._path.name}.{index}")
                if source.exists():
                    source.replace(
                        self._path.with_name(f"{self._path.name}.{index + 1}")
                    )
            self._path.replace(self._path.with_name(f"{self._path.name}.1"))
        except OSError:
            # Rotation is best-effort; a failure must not stop the write.
            pass
