"""Tests for secret-redacted, size-bounded application logging."""

from __future__ import annotations

import io
import logging
import types
from logging.handlers import RotatingFileHandler

import logging_setup
from logging_setup import (
    RedactingFilter,
    collect_secrets,
    redact_text,
    setup_logging,
)

_TAG = logging_setup._HANDLER_TAG


def _cleanup_root() -> None:
    """Remove handlers installed by setup_logging so tests do not leak state."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _TAG, False):
            root.removeHandler(handler)
            handler.close()


# --------------------------------------------------------------------------- #
# redact_text
# --------------------------------------------------------------------------- #
def test_redacts_a_configured_secret_verbatim():
    text = "using key sk-super-secret-value now"
    assert "sk-super-secret-value" not in redact_text(
        text, secrets=("sk-super-secret-value",)
    )
    assert "[redacted]" in redact_text(text, secrets=("sk-super-secret-value",))


def test_redacts_bearer_tokens():
    out = redact_text("Authorization: Bearer abc123DEF456")
    assert "abc123DEF456" not in out
    assert "Bearer [redacted]" in out


def test_redacts_key_value_secrets():
    out = redact_text('config password="hunter2" token: xyz')
    assert "hunter2" not in out
    assert "xyz" not in out
    assert "[redacted]" in out
    assert "password=" in out


def test_redacts_url_userinfo():
    out = redact_text("GET https://alice:s3cr3t@example.com/path")
    assert "s3cr3t" not in out
    assert "alice" not in out
    assert "https://[redacted]@example.com/path" in out


def test_redaction_is_a_noop_without_secrets():
    text = "nothing sensitive here"
    assert redact_text(text) == text


def test_the_longer_secret_is_replaced_first():
    # A short secret that is a substring of a longer one must not leave a tail.
    out = redact_text("value=ABCDEFGHIJ", secrets=("ABC", "ABCDEFGHIJ"))
    assert "ABCDEFGHIJ" not in out
    assert "DEFGHIJ" not in out


# --------------------------------------------------------------------------- #
# collect_secrets
# --------------------------------------------------------------------------- #
def test_collect_secrets_reads_known_environment_names():
    secrets = collect_secrets(
        {"JARVIS_LLM_API_KEY": "k1", "OPENAI_API_KEY": "k2", "OTHER": "ignored"}
    )
    assert "k1" in secrets
    assert "k2" in secrets
    assert "ignored" not in secrets


def test_collect_secrets_ignores_blank_values():
    assert collect_secrets({"JARVIS_LLM_API_KEY": "   "}) == ()


# --------------------------------------------------------------------------- #
# RedactingFilter
# --------------------------------------------------------------------------- #
class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def test_filter_redacts_records_before_handlers_see_them():
    handler = _CaptureHandler()
    handler.addFilter(RedactingFilter(secrets=("SECRETKEY",)))
    logger = logging.getLogger("jarvis.test.filter")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("connecting with SECRETKEY and Bearer tok123")
    finally:
        logger.removeHandler(handler)
    assert handler.messages
    assert "SECRETKEY" not in handler.messages[0]
    assert "tok123" not in handler.messages[0]


# --------------------------------------------------------------------------- #
# setup_logging: file output + redaction + rotation
# --------------------------------------------------------------------------- #
def test_setup_logging_writes_a_redacted_rotating_file(tmp_path):
    log_file = tmp_path / "jarvis.log"
    logger = setup_logging(
        log_path=log_file,
        level=logging.INFO,
        secrets=("SECRETKEY",),
        stream=False,
    )
    try:
        assert any(
            isinstance(h, RotatingFileHandler) and getattr(h, _TAG, False)
            for h in logger.handlers
        )
        logger.info("startup complete; key=SECRETKEY")
    finally:
        _cleanup_root()

    assert log_file.exists()
    contents = log_file.read_text(encoding="utf-8")
    assert "SECRETKEY" not in contents
    assert "startup complete" in contents


def test_setup_logging_is_idempotent(tmp_path):
    setup_logging(log_path=tmp_path / "a.log", stream=False)
    setup_logging(log_path=tmp_path / "a.log", stream=False)
    try:
        tagged = [
            h
            for h in logging.getLogger().handlers
            if getattr(h, _TAG, False)
        ]
        # Second call replaces the first call's handler rather than stacking.
        assert len(tagged) == 1
    finally:
        _cleanup_root()


def test_log_file_rotation_keeps_bounded_backups(tmp_path):
    log_file = tmp_path / "rotating.log"
    logger = setup_logging(
        log_path=log_file,
        level=logging.INFO,
        max_bytes=300,
        backup_count=2,
        stream=False,
    )
    try:
        for index in range(50):
            logger.info("line %d %s", index, "x" * 40)
    finally:
        _cleanup_root()

    assert log_file.exists()
    assert (tmp_path / "rotating.log.1").exists()
    assert (tmp_path / "rotating.log.2").exists()
    # Retention is bounded: no third backup is ever kept.
    assert not (tmp_path / "rotating.log.3").exists()
    # The active file never exceeds the configured ceiling.
    assert log_file.stat().st_size <= 300


# --------------------------------------------------------------------------- #
# Console handler safety (Windows encoding / windowed builds)
# --------------------------------------------------------------------------- #
def test_lenient_console_stream_escapes_unencodable_characters():
    buffer = io.BytesIO()
    strict = io.TextIOWrapper(buffer, encoding="cp1252", errors="strict")
    wrapper = logging_setup._LenientConsoleStream(strict)

    # Would raise UnicodeEncodeError on the raw stream; the wrapper must not.
    wrapper.write("arrow \u2192 here\n")
    wrapper.flush()
    assert b"arrow" in buffer.getvalue()
    assert b"\\u2192" in buffer.getvalue()


def test_console_stream_is_none_when_stderr_is_missing(monkeypatch):
    monkeypatch.setattr(logging_setup, "sys", types.SimpleNamespace(stderr=None))
    assert logging_setup._console_stream() is None


def test_setup_logging_skips_console_handler_when_stderr_is_missing(
    monkeypatch, tmp_path
):
    log_file = tmp_path / "console_missing.log"
    monkeypatch.setattr(logging_setup, "sys", types.SimpleNamespace(stderr=None))

    logger = setup_logging(log_path=log_file, level=logging.INFO, stream=True)
    try:
        # No console StreamHandler is installed when there is no stream to bind.
        assert not any(
            type(h) is logging.StreamHandler for h in logger.handlers
        )
        assert all(getattr(h, "stream", object()) is not None
                   for h in logger.handlers)
        # Logging still works (and reaches the file) instead of raising.
        logger.info("no console, still here")
    finally:
        _cleanup_root()

    assert "no console, still here" in log_file.read_text(encoding="utf-8")


def test_console_handler_survives_unencodable_output(monkeypatch, tmp_path):
    log_file = tmp_path / "console_encoding.log"
    buffer = io.BytesIO()
    strict = io.TextIOWrapper(buffer, encoding="cp1252", errors="strict")
    monkeypatch.setattr(logging_setup, "sys", types.SimpleNamespace(stderr=strict))

    logger = setup_logging(log_path=log_file, level=logging.INFO, stream=True)
    try:
        # \u2192 (rightwards arrow) is not representable in cp1252.
        logger.info("voice init arrow \u2192 done")
    finally:
        _cleanup_root()
    strict.flush()

    # The console kept the record using a backslash escape (no crash)...
    assert b"\\u2192" in buffer.getvalue()
    # ...and the UTF-8 file kept the real character.
    assert "voice init arrow \u2192 done" in log_file.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# JARVIS_LOG_LEVEL configuration
# --------------------------------------------------------------------------- #
def test_resolve_log_level_explicit_overrides_env(monkeypatch):
    monkeypatch.setenv("JARVIS_LOG_LEVEL", "DEBUG")
    assert logging_setup.resolve_log_level("WARNING") == "WARNING"


def test_resolve_log_level_reads_env_case_insensitively(monkeypatch):
    monkeypatch.setenv("JARVIS_LOG_LEVEL", "debug")
    assert logging_setup.resolve_log_level(None) == "DEBUG"


def test_resolve_log_level_accepts_a_number(monkeypatch):
    monkeypatch.setenv("JARVIS_LOG_LEVEL", "10")
    assert logging_setup.resolve_log_level(None) == 10


def test_resolve_log_level_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("JARVIS_LOG_LEVEL", raising=False)
    assert logging_setup.resolve_log_level(None) == logging_setup.settings.LOG_LEVEL


def test_resolve_log_level_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("JARVIS_LOG_LEVEL", "LOUD")
    assert logging_setup.resolve_log_level(None) == logging_setup.settings.LOG_LEVEL


def test_setup_logging_honors_env_level(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_LOG_LEVEL", "DEBUG")
    try:
        logger = setup_logging(log_path=tmp_path / "env_level.log", stream=False)
        assert logger.level == logging.DEBUG
    finally:
        _cleanup_root()


def test_setup_logging_warns_and_keeps_default_on_invalid_env(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_LOG_LEVEL", "LOUD")
    log_file = tmp_path / "bad_level.log"
    try:
        logger = setup_logging(log_path=log_file, stream=False)
        # Falls back to the default level rather than silencing logging.
        assert logger.level == logging.getLevelName(logging_setup.settings.LOG_LEVEL)
    finally:
        _cleanup_root()

    content = log_file.read_text(encoding="utf-8")
    assert "JARVIS_LOG_LEVEL" in content
    assert "LOUD" in content
