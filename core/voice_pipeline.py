"""Capture one utterance and turn it into text — off the UI thread.

:class:`VoiceCommandPipeline` is the only place recording, speech detection, and
transcription are stitched together. It is **Qt-free** and does **not** touch
the controller or the state machine; it simply returns a
:class:`ListenResult`. The GUI thread decides what to do with that result.

Design notes:

* One utterance per call. Recording always ends afterwards, whether by speech
  ending, silence, the hard time limit, cancellation, or an error.
* Speech detection uses a crude RMS energy threshold, which is enough to tell
  "someone is talking" from "the room is quiet" without extra dependencies.
* Every failure mode (mic, no speech, transcription) is mapped to a status so
  the UI can show an honest message instead of crashing.
"""

from __future__ import annotations

import logging
import math
import time
from array import array
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from audio.errors import MicrophoneError, TranscriptionError
from config import settings
from core.command_router import CommandRouter, Intent

logger = logging.getLogger(__name__)

# Receives in-progress text (e.g. partial recognition). Optional; may be unused.
PartialCallback = Callable[[str], None]


class ListenStatus(str, Enum):
    """Outcome of a single listen attempt."""

    OK = "OK"
    NO_SPEECH = "NO_SPEECH"
    MICROPHONE_ERROR = "MICROPHONE_ERROR"
    TRANSCRIPTION_ERROR = "TRANSCRIPTION_ERROR"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class ListenResult:
    """The honest result of one listen/transcribe cycle."""

    status: ListenStatus
    transcript: str = ""
    intent: Intent | None = None
    message: str = ""


def _rms(block: bytes) -> float:
    """Root-mean-square amplitude of a block of 16-bit samples."""
    samples = array("h")
    samples.frombytes(block)
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


def _peak(block: bytes) -> int:
    """Peak absolute amplitude of a block of 16-bit samples."""
    samples = array("h")
    samples.frombytes(block)
    if not samples:
        return 0
    return max(max(samples), -min(samples))


class VoiceCommandPipeline:
    """Records one utterance and transcribes it into an optional Intent."""

    def __init__(
        self,
        recorder,
        stt,
        router: CommandRouter | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_seconds: float | None = None,
        silence_timeout: float | None = None,
        no_speech_timeout: float | None = None,
        rms_threshold: int | None = None,
        on_partial: PartialCallback | None = None,
    ) -> None:
        self._recorder = recorder
        self._stt = stt
        self._router = router or CommandRouter()
        self._clock = clock
        self._max_seconds = (
            settings.RECORD_MAX_SECONDS if max_seconds is None else max_seconds
        )
        self._silence_timeout = (
            settings.SILENCE_TIMEOUT_SECONDS
            if silence_timeout is None
            else silence_timeout
        )
        self._no_speech_timeout = (
            settings.NO_SPEECH_TIMEOUT_SECONDS
            if no_speech_timeout is None
            else no_speech_timeout
        )
        self._rms_threshold = (
            settings.SILENCE_RMS_THRESHOLD if rms_threshold is None else rms_threshold
        )
        self._on_partial = on_partial

    def listen_once(self, should_stop: Callable[[], bool] | None = None) -> ListenResult:
        """Record one utterance, transcribe it, and route it. Never raises."""
        should_stop = should_stop or (lambda: False)
        collected: list[bytes] = []
        start = self._clock()
        last_voice = start
        speech_started = False
        blocks = 0
        max_rms = 0.0
        max_peak = 0
        noise_floor = 0.0

        def finish(result: ListenResult) -> ListenResult:
            # Diagnostics only: status, levels, and transcript *length*. The
            # recognized text itself is never logged (privacy).
            logger.info(
                "Listen complete: status=%s blocks=%d peak=%d max_rms=%.1f "
                "noise_floor=%.1f speech_started=%s transcript_len=%d",
                result.status.value,
                blocks,
                max_peak,
                max_rms,
                noise_floor,
                speech_started,
                len(result.transcript or ""),
            )
            return result

        try:
            for block in self._recorder.stream_blocks(
                max_seconds=self._max_seconds, should_stop=should_stop
            ):
                if should_stop():
                    return finish(
                        ListenResult(ListenStatus.CANCELLED, message="Cancelled.")
                    )
                collected.append(block)
                rms = _rms(block)
                peak = _peak(block)
                if blocks == 0:
                    noise_floor = rms
                if rms > max_rms:
                    max_rms = rms
                if peak > max_peak:
                    max_peak = peak
                now = self._clock()
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "block %d frames=%d rms=%.1f peak=%d speech_started=%s "
                        "elapsed=%.3f",
                        blocks,
                        len(block) // 2,
                        rms,
                        peak,
                        speech_started,
                        now - start,
                    )
                blocks += 1
                if rms >= self._rms_threshold:
                    speech_started = True
                    last_voice = now
                elif speech_started and (now - last_voice) >= self._silence_timeout:
                    break
                elif not speech_started and (now - start) >= self._no_speech_timeout:
                    return finish(
                        ListenResult(
                            ListenStatus.NO_SPEECH, message="No speech detected."
                        )
                    )
        except MicrophoneError as exc:
            return finish(
                ListenResult(ListenStatus.MICROPHONE_ERROR, message=str(exc))
            )

        if should_stop():
            return finish(ListenResult(ListenStatus.CANCELLED, message="Cancelled."))
        if not speech_started:
            return finish(
                ListenResult(ListenStatus.NO_SPEECH, message="No speech detected.")
            )

        try:
            transcript = self._stt.transcribe(b"".join(collected))
        except TranscriptionError as exc:
            return finish(
                ListenResult(ListenStatus.TRANSCRIPTION_ERROR, message=str(exc))
            )

        transcript = (transcript or "").strip()
        if not transcript:
            return finish(
                ListenResult(ListenStatus.NO_SPEECH, message="No speech recognized.")
            )

        intent = self._router.route(transcript)
        return finish(
            ListenResult(ListenStatus.OK, transcript=transcript, intent=intent)
        )
