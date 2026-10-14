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

:func:`setup_logging` is idempotent: calling it more than once replaces the
handlers it previously installed rather than stacking duplicates.
"""

from __future__ import annotations

import logging
import os
import re
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
        stream_handler = logging.StreamHandler()
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
