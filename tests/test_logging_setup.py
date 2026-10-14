"""Tests for secret-redacted, size-bounded application logging."""

from __future__ import annotations

import logging
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
