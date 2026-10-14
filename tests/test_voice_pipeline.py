"""Tests for the voice pipeline (record -> transcribe -> route).

No microphone, speech model, or audio hardware is required: the recorder and the
recognizer are fakes.
"""

from __future__ import annotations

import importlib

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
