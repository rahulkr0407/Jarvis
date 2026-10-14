"""Hardware-independent tests for microphone capture and diagnostics.

No device is opened: ``sounddevice`` is replaced by a tiny fake, so the capture
loop, PCM handling, stream configuration, and diagnostic logging can all be
exercised deterministically.
"""

from __future__ import annotations

import logging
from array import array
from collections.abc import Callable

from audio.microphone import MicrophoneRecorder


class _FakeStream:
    """A context-managed stream that always returns the same block."""

    def __init__(self, block: bytes) -> None:
        self._block = block
        self.stopped = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, frames):
        return self._block, False

    def stop(self) -> None:
        self.stopped = True


class _FakeSoundDevice:
    """Minimal stand-in for the ``sounddevice`` module."""

    def __init__(self, block: bytes) -> None:
        self._block = block
        self.open_kwargs: dict | None = None
        self.stream: _FakeStream | None = None

    def query_devices(self, device=None, kind=None):
        return {"name": "Fake Microphone", "index": 7}

    def RawInputStream(self, **kwargs):
        self.open_kwargs = kwargs
        self.stream = _FakeStream(self._block)
        return self.stream


def _recorder_with(fake: _FakeSoundDevice) -> MicrophoneRecorder:
    recorder = MicrophoneRecorder(block_frames=8)
    recorder._import_sounddevice = lambda: fake  # type: ignore[method-assign]
    return recorder


def _stop_after_one() -> Callable[[], bool]:
    calls = {"n": 0}

    def stop() -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    return stop


def test_device_is_logged_on_open(caplog):
    block = array("h", [1000] * 8).tobytes()
    recorder = _recorder_with(_FakeSoundDevice(block))

    with caplog.at_level(logging.INFO, logger="audio.microphone"):
        list(recorder.stream_blocks(max_seconds=1.0, should_stop=_stop_after_one()))

    messages = [
        r.getMessage() for r in caplog.records if r.name == "audio.microphone"
    ]
    assert any("Fake Microphone" in m for m in messages)
    assert any("samplerate=16000" in m for m in messages)


def test_stream_blocks_yields_int16_mono_pcm():
    block = array("h", [1000] * 8).tobytes()
    fake = _FakeSoundDevice(block)
    recorder = _recorder_with(fake)

    out = list(recorder.stream_blocks(max_seconds=1.0, should_stop=_stop_after_one()))

    assert out == [block]
    assert fake.open_kwargs is not None
    assert fake.open_kwargs["dtype"] == "int16"
    assert fake.open_kwargs["channels"] == 1
    assert fake.open_kwargs["samplerate"] == 16000
    # The stream is always released, even on a clean single-block capture.
    assert fake.stream is not None and fake.stream.stopped
