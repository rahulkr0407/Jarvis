"""Test doubles for the audio layer.

These let the pipeline and assistant be tested with no microphone, no speech
model, and no audio hardware.
"""

from __future__ import annotations

from array import array


class FakeClock:
    """A controllable clock for deterministic timing tests."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, delta: float) -> None:
        self.now += delta


def pcm_block(value: int, frames: int = 1000) -> bytes:
    """A block of 16-bit mono samples all equal to ``value``."""
    return array("h", [value] * frames).tobytes()


def loud_block(frames: int = 1000) -> bytes:
    """Samples well above the silence threshold."""
    return pcm_block(4000, frames)


def silent_block(frames: int = 1000) -> bytes:
    """Silence (all zero samples)."""
    return pcm_block(0, frames)


class FakeRecorder:
    """Yields preset PCM blocks; optionally advances a clock and/or raises."""

    def __init__(self, blocks=None, *, error=None, clock=None, block_seconds: float = 0.5):
        self._blocks = list(blocks or [])
        self._error = error
        self._clock = clock
        self._block_seconds = block_seconds
        self.calls = 0

    def stream_blocks(self, *, max_seconds, should_stop=None):
        should_stop = should_stop or (lambda: False)
        for block in self._blocks:
            if should_stop():
                return
            if self._clock is not None:
                self._clock.advance(self._block_seconds)
            self.calls += 1
            yield block
        if self._error is not None:
            raise self._error


class FakeSTT:
    """Returns a fixed transcript and/or raises a fixed error."""

    sample_rate = 16000

    def __init__(self, text: str = "", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.received: bytes | None = None
        self.calls = 0

    def transcribe(self, pcm: bytes) -> str:
        self.calls += 1
        self.received = pcm
        if self.error is not None:
            raise self.error
        return self.text


class FakeTTS:
    """Records spoken lines instead of speaking them."""

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def say(self, text: str) -> None:
        self.spoken.append(text)
