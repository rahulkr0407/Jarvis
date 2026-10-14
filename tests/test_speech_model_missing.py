"""Missing-configuration checks for the speech-to-text layer.

These verify the honest failure path when the Vosk model is not present. They do
not require Vosk to be importable or a model to be downloaded: the missing-path
check happens before any third-party import, so the result is deterministic.
"""

from __future__ import annotations

import pytest

from audio.errors import ModelNotFoundError, TranscriptionError
from audio.stt import VoskSpeechToText


def test_missing_model_raises_a_clear_error(tmp_path):
    recognizer = VoskSpeechToText(tmp_path / "does-not-exist", sample_rate=16000)
    with pytest.raises(ModelNotFoundError) as excinfo:
        recognizer.transcribe(b"\x00\x00" * 100)
    # The message must tell the user how to fix it.
    assert "not found" in str(excinfo.value).lower()
    assert "README" in str(excinfo.value)


def test_model_not_found_is_a_transcription_error():
    assert issubclass(ModelNotFoundError, TranscriptionError)


def test_empty_audio_never_loads_the_model(tmp_path):
    recognizer = VoskSpeechToText(tmp_path / "missing", sample_rate=16000)
    # Empty PCM short-circuits to "" without touching the (absent) model.
    assert recognizer.transcribe(b"") == ""


def test_model_path_property_reports_expected_location(tmp_path):
    target = tmp_path / "model-dir"
    recognizer = VoskSpeechToText(target, sample_rate=16000)
    assert recognizer.model_path == target
