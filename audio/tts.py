"""Text-to-speech output.

:class:`Pyttsx3TextToSpeech` uses the local Windows SAPI5 voices through
``pyttsx3``. The speech engine is created lazily, on the thread that first calls
:meth:`say`, which is important because the COM-based engine must be used from a
single thread (the UI runs it on a dedicated worker thread).

Speech failures are swallowed on purpose: an audio-output problem must never
interrupt or crash the assistant. Nothing here talks to the network.
"""

from __future__ import annotations

from typing import Protocol

from config import settings


class TextToSpeech(Protocol):
    """Anything that can speak a line of text."""

    def say(self, text: str) -> None:
        """Speak ``text``. Must not raise on failure."""


class NullTextToSpeech:
    """A silent implementation used when speech is disabled or unavailable."""

    def say(self, text: str) -> None:
        return None


class Pyttsx3TextToSpeech:
    """Speaks text with the local Windows voice via ``pyttsx3``."""

    def __init__(
        self,
        *,
        rate: int | None = None,
        volume: float | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._rate = settings.TTS_RATE if rate is None else rate
        self._volume = settings.TTS_VOLUME if volume is None else volume
        self._enabled = settings.TTS_ENABLED if enabled is None else enabled
        self._engine = None  # created lazily on first say()

    def say(self, text: str) -> None:
        if not self._enabled or not text or not text.strip():
            return
        engine = self._get_engine()
        if engine is None:
            return
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception:  # pragma: no cover - depends on audio device
            # Never let speech output break the assistant.
            return

    def shutdown(self) -> None:
        """Stop and release the speech engine on the thread that owns it.

        Must be called on the same thread that created the engine, before that
        thread exits, otherwise the underlying COM objects can crash the process
        during interpreter shutdown.
        """
        engine = self._engine
        self._engine = None
        if engine is None:
            return
        try:
            engine.stop()
        except Exception:  # pragma: no cover - best-effort cleanup
            pass
        del engine

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        try:
            import pyttsx3  # type: ignore[import-not-found]
        except Exception:  # pragma: no cover - optional dependency
            return None
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", self._rate)
            engine.setProperty("volume", self._volume)
        except Exception:  # pragma: no cover - depends on COM/SAPI
            return None
        self._engine = engine
        return engine
