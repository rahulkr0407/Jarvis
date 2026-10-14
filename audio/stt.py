"""Offline speech-to-text.

:class:`VoskSpeechToText` wraps the Vosk engine. Both ``vosk`` and the model are
loaded lazily, on first use, so constructing this class is cheap and never
blocks the UI. If the model directory is missing the caller receives a clear
:class:`~audio.errors.ModelNotFoundError`.

The public surface is a tiny :class:`SpeechToText` protocol so tests and future
engines can be swapped in without touching the pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from audio.errors import ModelNotFoundError, TranscriptionError
from config import settings


class SpeechToText(Protocol):
    """Anything that can turn raw PCM into text."""

    sample_rate: int

    def transcribe(self, pcm: bytes) -> str:
        """Return the recognized text for a buffer of 16-bit mono PCM."""


class VoskSpeechToText:
    """Vosk-backed, fully offline recognizer."""

    def __init__(
        self,
        model_path: str | Path | None = None,
        *,
        sample_rate: int | None = None,
    ) -> None:
        self.sample_rate = sample_rate or settings.VOSK_SAMPLE_RATE
        self._model_path = (
            Path(model_path) if model_path is not None else settings.resolve_model_path()
        )
        self._model = None  # loaded on first transcribe()

    @property
    def model_path(self) -> Path:
        """Location the model is expected to live in."""
        return self._model_path

    def transcribe(self, pcm: bytes) -> str:
        """Recognize one utterance. Empty PCM yields an empty string."""
        if not pcm:
            return ""
        model = self._load_model()
        try:
            from vosk import KaldiRecognizer  # type: ignore[import-not-found]

            recognizer = KaldiRecognizer(model, self.sample_rate)
            recognizer.AcceptWaveform(pcm)
            result = json.loads(recognizer.FinalResult())
        except TranscriptionError:
            raise
        except Exception as exc:  # pragma: no cover - depends on vosk internals
            raise TranscriptionError(f"Transcription failed: {exc}") from exc
        return str(result.get("text") or "").strip()

    def _load_model(self):
        if self._model is not None:
            return self._model
        if not self._model_path.exists():
            raise ModelNotFoundError(
                f"Vosk model not found at '{self._model_path}'. Download "
                "'vosk-model-small-en-us-0.15' and extract it there. See "
                "README.md for the exact steps."
            )
        try:
            from vosk import Model  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover - depends on environment
            raise TranscriptionError(
                "Vosk is not installed. Install the voice extras: "
                'pip install -e ".[voice]"'
            ) from exc
        try:
            self._model = Model(str(self._model_path))
        except Exception as exc:  # pragma: no cover - depends on model files
            raise TranscriptionError(f"Could not load the Vosk model: {exc}") from exc
        return self._model
