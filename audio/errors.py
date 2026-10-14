"""Exceptions for the audio layer.

All failures are expressed as :class:`AudioError` subclasses so the pipeline can
map them to user-facing results without leaking third-party exception types.
"""

from __future__ import annotations


class AudioError(RuntimeError):
    """Base class for all audio-layer errors."""


class MicrophoneError(AudioError):
    """The microphone could not be opened or read."""


class NoSpeechError(AudioError):
    """No usable speech was captured."""


class TranscriptionError(AudioError):
    """Speech could not be transcribed."""


class ModelNotFoundError(TranscriptionError):
    """The speech-to-text model is missing on disk."""
