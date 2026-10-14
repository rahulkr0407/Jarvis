"""Tests for the worker that runs one listen cycle off the GUI thread.

No audio hardware and no event loop: the pipeline is a fake and ``run`` is called
directly, so the signal fires synchronously and any exception handling is
observed deterministically.
"""

from __future__ import annotations

import logging

from audio.errors import MicrophoneError
from core.voice_pipeline import ListenResult, ListenStatus
from ui.workers import ListenWorker


class _RecordingPipeline:
    def __init__(self, result: ListenResult) -> None:
        self._result = result
        self.calls = 0

    def listen_once(self, should_stop=None) -> ListenResult:
        self.calls += 1
        return self._result


class _RaisingPipeline:
    def listen_once(self, should_stop=None) -> ListenResult:
        raise MicrophoneError("boom")


def test_run_emits_the_pipeline_result():
    result = ListenResult(ListenStatus.NO_SPEECH, message="none")
    worker = ListenWorker(_RecordingPipeline(result))
    seen: list = []
    worker.finished.connect(seen.append)

    worker.run()

    assert seen == [result]


def test_unexpected_exception_is_logged_and_mapped(caplog):
    worker = ListenWorker(_RaisingPipeline())
    seen: list = []
    worker.finished.connect(seen.append)

    with caplog.at_level(logging.ERROR, logger="ui.workers"):
        worker.run()

    assert seen and seen[0].status is ListenStatus.TRANSCRIPTION_ERROR
    assert any(
        r.name == "ui.workers" and r.levelno == logging.ERROR for r in caplog.records
    )
