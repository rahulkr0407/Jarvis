"""Application logging with secret redaction and bounded retention.

This is deliberately separate from the *audit* log (:mod:`actions.audit`): the
audit log records action attempts as structured JSON, while this module provides
ordinary diagnostic logging for the whole app.

Two safety properties matter here, and both are enforced by
:class:`RedactingFilter`, which every handler passes through:

* **Secrets never reach the log.** The filter rewrites the formatted message to
  remove anything that looks like an API key, bearer token, ``password=...``-style
  pair, or credentials embedded in a URL. Any configured secret value is also
  replaced verbatim (longest first), so a key that does not match a generic
  pattern is still removed.
* **The log cannot grow without bound.** A :class:`~logging.handlers.RotatingFileHandler`
  caps the file size and keeps a fixed number of backups (see the ``*_MAX_BYTES``
  and ``*_BACKUP_COUNT`` settings in :mod:`config.settings`).

The optional console handler is defensive on Windows: if ``sys.stderr`` is
absent (a windowed/frozen build) it is skipped entirely, and if the console
cannot encode a character the record is still written using ``\\uXXXX``
escapes. This avoids the ``--- Logging error ---`` spam that a failing stream
handler otherwise produces, without muting any other logging error.

:func:`setup_logging` is idempotent: calling it more than once replaces the
handlers it previously installed rather than stacking duplicates.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import Iterable
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import settings

#: Mark attribute put on handlers this module installs, so re-configuring is safe.
_HANDLER_TAG = "_jarvis_handler"

#: Environment variables whose values must never appear in a log line.
_SECRET_ENV_VARS = ("JARVIS_LLM_API_KEY", "OPENAI_API_KEY")

_BEARER = re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._\-]{4,})")
_SECRET_KV = re.compile(
    r"(?i)\b(password|passwd|token|secret|api[_-]?key|credential|authorization)"
    r"(\s*[:=]\s*)"
    r"(\"[^\"]*\"|'[^']*'|[^\s,;\"']+)"
)
_URL_USERINFO = re.compile(
    r"([a-zA-Z][a-zA-Z0-9+.\-]*://)([^/@\s:]+)(?::[^/@\s]*)?@"
)

_REDACTED = "[redacted]"


def _redact_secret_pair(match: re.Match[str]) -> str:
    """Redact the value of a ``key=value`` pair, preserving key and quotes."""
    key, separator, value = match.group(1), match.group(2), match.group(3)
    # A bare "Bearer" token is handled by _BEARER; don't redact the scheme word.
    if value.lower() in {"bearer"} or value == _REDACTED:
        return match.group(0)
    if value[:1] in {'"', "'"}:
        quote = value[0]
        return f"{key}{separator}{quote}{_REDACTED}{quote}"
    return f"{key}{separator}{_REDACTED}"


def collect_secrets(env: dict | None = None) -> tuple[str, ...]:
    """Return the secret values to scrub, taken from the environment."""
    source = os.environ if env is None else env
    values = []
    for name in _SECRET_ENV_VARS:
        value = (source.get(name) or "").strip()
        if value:
            values.append(value)
    return tuple(values)


def redact_text(text: str, secrets: Iterable[str] = ()) -> str:
    """Return ``text`` with credentials removed, safe to log."""
    if not text:
        return text
    # Replace exact configured secrets first. Longest first so a shorter secret
    # that is a substring of a longer one cannot leave a fragment behind.
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        text = text.replace(secret, _REDACTED)
    text = _BEARER.sub(r"\1" + _REDACTED, text)
    text = _SECRET_KV.sub(_redact_secret_pair, text)
    text = _URL_USERINFO.sub(r"\1" + _REDACTED + "@", text)
    return text


class RedactingFilter(logging.Filter):
    """A logging filter that rewrites each record with :func:`redact_text`.

    The whole formatted message is redacted before handlers see it, so secrets
    cannot leak through the message, its lazy ``%``-style arguments, or a
    traceback text attached to the record.
    """

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = tuple(secrets)

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = redact_text(message, self._secrets)
        if redacted != message:
            # Replace the args-resolved message and drop the raw arguments so
            # they cannot be formatted again downstream.
            record.msg = redacted
            record.args = ()
        if record.exc_text:
            record.exc_text = redact_text(record.exc_text, self._secrets)
        return True


def _resolve_log_path(path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = settings.PROJECT_ROOT / resolved
    return resolved


def _remove_old_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_TAG, False):
            logger.removeHandler(handler)
            handler.close()


class _LenientConsoleStream:
    """Wrap a text stream so an unencodable character cannot break logging.

    The Windows console can use a legacy code page that cannot represent every
    character in a log line. Without this, ``StreamHandler.emit`` raises
    ``UnicodeEncodeError`` and the logging module prints ``--- Logging error ---``
    and silently drops the record. Here only ``UnicodeEncodeError`` is handled:
    the record is written with ``backslashreplace`` escapes so the diagnostic is
    preserved (e.g. ``\\u2192``) instead of being lost. Every other exception is
    left untouched and still reported by the logging module as before.
    """

    def __init__(self, stream) -> None:
        self._stream = stream

    def write(self, text: str) -> int:
        try:
            return self._stream.write(text)
        except UnicodeEncodeError:
            encoding = getattr(self._stream, "encoding", None) or "utf-8"
            escaped = text.encode(encoding, "backslashreplace").decode(
                encoding, "replace"
            )
            return self._stream.write(escaped)

    def flush(self) -> None:
        flush = getattr(self._stream, "flush", None)
        if flush is not None:
            flush()

    def isatty(self) -> bool:
        isatty = getattr(self._stream, "isatty", None)
        return bool(isatty()) if isatty is not None else False

    def __getattr__(self, name):
        # Delegate anything else (e.g. ``encoding``) to the wrapped stream.
        return getattr(self._stream, name)


def _console_stream():
    """Return a safe console stream, or ``None`` when there is no console.

    ``logging.StreamHandler`` binds ``sys.stderr`` when it is constructed, which
    may be ``None`` in a windowed/frozen build. Returning ``None`` signals the
    caller to skip the console handler entirely rather than install one whose
    every ``emit`` would fail.
    """
    stream = sys.stderr
    if stream is None:
        return None
    return _LenientConsoleStream(stream)


def setup_logging(
    *,
    log_path: str | Path | None = None,
    level: str | int | None = None,
    max_bytes: int | None = None,
    backup_count: int | None = None,
    secrets: Iterable[str] | None = None,
    stream: bool = True,
) -> logging.Logger:
    """Configure the root logger with a redacting, rotating file handler.

    Best-effort: if the log directory cannot be created the file handler is
    skipped, but the app still runs. Returns the configured root logger.
    """
    logger = logging.getLogger()
    logger.setLevel(level if level is not None else settings.LOG_LEVEL)

    secret_values = (
        collect_secrets() if secrets is None else tuple(secrets)
    )
    redactor = RedactingFilter(secret_values)

    _remove_old_handlers(logger)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    if stream:
        console = _console_stream()
        if console is not None:
            stream_handler = logging.StreamHandler(console)
            stream_handler.setFormatter(formatter)
            stream_handler.addFilter(redactor)
            setattr(stream_handler, _HANDLER_TAG, True)
            logger.addHandler(stream_handler)

    path = _resolve_log_path(log_path or settings.LOG_PATH)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            path,
            maxBytes=max_bytes if max_bytes is not None else settings.LOG_MAX_BYTES,
            backupCount=(
                backup_count
                if backup_count is not None
                else settings.LOG_BACKUP_COUNT
            ),
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(redactor)
        setattr(file_handler, _HANDLER_TAG, True)
        logger.addHandler(file_handler)
    except Exception:
        # Logging is never allowed to stop the app from starting.
        pass

    return logger
