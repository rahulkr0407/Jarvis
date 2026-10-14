"""Tests for the voice pipeline (record -> transcribe -> route).

No microphone, speech model, or audio hardware is required: the recorder and the
recognizer are fakes.
"""

from __future__ import annotations

import importlib
import logging

from audio.errors import MicrophoneError, TranscriptionError
from core.voice_pipeline import ListenStatus, VoiceCommandPipeline
from tests.fakes import FakeClock, FakeRecorder, FakeSTT, loud_block, silent_block


def make_pipeline(recorder, stt, clock, **kwargs) -> VoiceCommandPipeline:
    return VoiceCommandPipeline(recorder, stt, clock=clock, **kwargs)


def test_success_returns_transcript_and_intent():
    clock = FakeClock()
    recorder = FakeRecorder([loud_block(), loud_block(), *([silent_block()] * 5)], clock=clock)
    result = make_pipeline(recorder, FakeSTT("open notepad"), clock).listen_once()
    assert result.status is ListenStatus.OK
    assert result.transcript == "open notepad"
    assert result.intent is not None
    assert result.intent.action_name == "open_application"
    assert result.intent.arguments["target"] == "notepad"


def test_recognized_but_unroutable_text_has_no_intent():
    clock = FakeClock()
    recorder = FakeRecorder([loud_block(), loud_block(), *([silent_block()] * 5)], clock=clock)
    result = make_pipeline(recorder, FakeSTT("please delete everything"), clock).listen_once()
    assert result.status is ListenStatus.OK
    assert result.transcript == "please delete everything"
    assert result.intent is None


def test_no_speech_timeout_returns_no_speech():
    clock = FakeClock()
    recorder = FakeRecorder([silent_block() for _ in range(10)], clock=clock)
    result = make_pipeline(
        recorder, FakeSTT("unused"), clock, no_speech_timeout=1.0
    ).listen_once()
    assert result.status is ListenStatus.NO_SPEECH


def test_empty_transcript_is_treated_as_no_speech():
    clock = FakeClock()
    recorder = FakeRecorder([loud_block(), loud_block()], clock=clock)
    result = make_pipeline(recorder, FakeSTT(""), clock).listen_once()
    assert result.status is ListenStatus.NO_SPEECH


def test_microphone_error_is_reported():
    clock = FakeClock()
    recorder = FakeRecorder([], error=MicrophoneError("no microphone"))
    result = make_pipeline(recorder, FakeSTT("x"), clock).listen_once()
    assert result.status is ListenStatus.MICROPHONE_ERROR
    assert "no microphone" in result.message


def test_transcription_error_is_reported():
    clock = FakeClock()
    recorder = FakeRecorder([loud_block(), loud_block()], clock=clock)
    stt = FakeSTT(error=TranscriptionError("bad model"))
    result = make_pipeline(recorder, stt, clock).listen_once()
    assert result.status is ListenStatus.TRANSCRIPTION_ERROR
    assert "bad model" in result.message


def test_cancelled_before_any_audio():
    clock = FakeClock()
    recorder = FakeRecorder([loud_block()], clock=clock)
    result = make_pipeline(recorder, FakeSTT("x"), clock).listen_once(
        should_stop=lambda: True
    )
    assert result.status is ListenStatus.CANCELLED


def test_cancelled_mid_capture():
    clock = FakeClock()
    recorder = FakeRecorder([loud_block(), loud_block(), loud_block()], clock=clock)
    result = make_pipeline(recorder, FakeSTT("x"), clock).listen_once(
        should_stop=lambda: recorder.calls >= 1
    )
    assert result.status is ListenStatus.CANCELLED
    assert recorder.calls == 1  # capture stopped promptly


def test_transcription_uses_the_captured_audio():
    clock = FakeClock()
    recorder = FakeRecorder([loud_block(frames=500), loud_block(frames=500)], clock=clock)
    stt = FakeSTT("open notepad")
    make_pipeline(recorder, stt, clock).listen_once()
    assert stt.received is not None
    assert len(stt.received) == 500 * 2 * 2  # 2 blocks * 500 frames * 2 bytes


def test_audio_modules_import_without_voice_dependencies():
    # Importing the audio layer must never require sounddevice/vosk/pyttsx3.
    for module in ("audio.microphone", "audio.stt", "audio.tts"):
        importlib.import_module(module)


# --------------------------------------------------------------------------- #
# Diagnostic logging (observability only; no behavior change)
# --------------------------------------------------------------------------- #
def _pipeline_records(caplog):
    return [r for r in caplog.records if r.name == "core.voice_pipeline"]


def test_completion_summary_is_logged(caplog):
    clock = FakeClock()
    recorder = FakeRecorder([loud_block(), *([silent_block()] * 5)], clock=clock)
    with caplog.at_level(logging.INFO, logger="core.voice_pipeline"):
        result = make_pipeline(recorder, FakeSTT("open notepad"), clock).listen_once()
    assert result.status is ListenStatus.OK
    summaries = [r.getMessage() for r in _pipeline_records(caplog)]
    assert any("status=OK" in m and "transcript_len=12" in m for m in summaries)


def test_transcript_text_is_never_logged(caplog):
    clock = FakeClock()
    recorder = FakeRecorder([loud_block(), *([silent_block()] * 5)], clock=clock)
    secret = "secret phrase 123"
    with caplog.at_level(logging.DEBUG, logger="core.voice_pipeline"):
        result = make_pipeline(recorder, FakeSTT(secret), clock).listen_once()
    assert result.transcript == secret
    for record in _pipeline_records(caplog):
        assert secret not in record.getMessage()


def test_no_speech_summary_is_logged(caplog):
    clock = FakeClock()
    recorder = FakeRecorder([silent_block() for _ in range(20)], clock=clock)
    with caplog.at_level(logging.INFO, logger="core.voice_pipeline"):
        result = make_pipeline(
            recorder, FakeSTT("unused"), clock, no_speech_timeout=1.0
        ).listen_once()
    assert result.status is ListenStatus.NO_SPEECH
    assert any("status=NO_SPEECH" in r.getMessage() for r in _pipeline_records(caplog))


def test_per_block_diagnostics_only_at_debug(caplog):
    clock = FakeClock()
    recorder = FakeRecorder([loud_block(), silent_block()], clock=clock)
    with caplog.at_level(logging.DEBUG, logger="core.voice_pipeline"):
        make_pipeline(recorder, FakeSTT("x"), clock).listen_once()
    assert any(
        r.levelno == logging.DEBUG and "block 0" in r.getMessage()
        for r in _pipeline_records(caplog)
    )


def test_no_per_block_logs_at_info(caplog):
    clock = FakeClock()
    recorder = FakeRecorder([loud_block(), silent_block()], clock=clock)
    with caplog.at_level(logging.INFO, logger="core.voice_pipeline"):
        make_pipeline(recorder, FakeSTT("x"), clock).listen_once()
    assert not any(r.levelno == logging.DEBUG for r in _pipeline_records(caplog))
