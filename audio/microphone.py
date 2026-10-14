"""Microphone capture: exactly one utterance per activation.

:class:`MicrophoneRecorder` exposes :meth:`MicrophoneRecorder.stream_blocks`, a
generator of raw 16-bit mono PCM blocks. Callers consume it and stop early by
returning from their loop; the recorder also stops on a ``should_stop`` flag and
on a hard time limit. The stream is always closed in a ``finally`` block, so the
device is released even if the consumer raises or cancels.

``sounddevice`` is imported lazily. If it is missing, a clear
:class:`~audio.errors.MicrophoneError` is raised instead of an ImportError.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator

from audio.errors import MicrophoneError
from config import settings

logger = logging.getLogger(__name__)


class MicrophoneRecorder:
    """Captures short, one-shot audio recordings from the default microphone."""

    def __init__(
        self,
        *,
        samplerate: int | None = None,
        block_frames: int | None = None,
        device: int | str | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._samplerate = samplerate or settings.VOSK_SAMPLE_RATE
        self._block_frames = block_frames or settings.AUDIO_BLOCK_FRAMES
        self._device = device
        self._clock = clock

    @property
    def samplerate(self) -> int:
        """Sample rate of the recorded audio, in Hz."""
        return self._samplerate

    @staticmethod
    def _import_sounddevice():
        try:
            import sounddevice  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover - depends on environment
            raise MicrophoneError(
                "Audio capture is unavailable because 'sounddevice' is not "
                'installed. Install the voice extras: pip install -e ".[voice]"'
            ) from exc
        return sounddevice

    def stream_blocks(
        self,
        *,
        max_seconds: float,
        should_stop: Callable[[], bool] | None = None,
    ) -> Iterator[bytes]:
        """Yield raw PCM blocks until stopped, silent, timed out, or the mic fails.

        Args:
            max_seconds: Hard upper bound on capture duration.
            should_stop: Optional callback polled between blocks. When it returns
                ``True`` capture stops promptly.
        """
        should_stop = should_stop or (lambda: False)
        sounddevice = self._import_sounddevice()
        logger.debug("Opening microphone for one utterance")

        start = self._clock()
        try:
            stream = sounddevice.RawInputStream(
                samplerate=self._samplerate,
                blocksize=self._block_frames,
                dtype="int16",
                channels=1,
                device=self._device,
            )
        except Exception as exc:  # pragma: no cover - depends on hardware
            raise MicrophoneError(f"Could not open the microphone: {exc}") from exc

        with stream:
            try:
                while True:
                    if should_stop():
                        return
                    if self._clock() - start >= max_seconds:
                        return
                    try:
                        data, _overflowed = stream.read(self._block_frames)
                    except Exception as exc:  # pragma: no cover - hardware
                        raise MicrophoneError(
                            f"Microphone read failed: {exc}"
                        ) from exc
                    yield bytes(data)
            finally:
                try:
                    stream.stop()
                except Exception:  # pragma: no cover - best-effort cleanup
                    pass
