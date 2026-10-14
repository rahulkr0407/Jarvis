"""Qt worker objects that keep blocking work off the GUI thread.

Two concerns are moved to dedicated ``QThread``s:

* :class:`ListenWorker` runs one ``VoiceCommandPipeline.listen_once`` cycle —
  microphone capture and transcription are blocking and must not freeze the UI.
* :class:`SpeakWorker` runs text-to-speech, which also blocks while a phrase is
  being spoken.

Both are plain ``QObject``s moved to a thread; results come back to the GUI via
Qt signals, which are delivered on the GUI thread automatically. Nothing here
touches the controller: the controller is only ever mutated on the GUI thread.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot


class ListenWorker(QObject):
    """Runs one listen/transcribe cycle and emits the result."""

    finished = Signal(object)  # payload: core.voice_pipeline.ListenResult

    def __init__(self, pipeline) -> None:
        super().__init__()
        self._pipeline = pipeline
        self._stop = False

    def stop(self) -> None:
        """Ask the running capture to stop as soon as possible."""
        self._stop = True

    @Slot()
    def run(self) -> None:
        # Imported here to avoid a hard dependency on the audio stack at import.
        from core.voice_pipeline import ListenResult, ListenStatus

        try:
            result = self._pipeline.listen_once(should_stop=lambda: self._stop)
        except Exception as exc:  # pragma: no cover - defensive catch-all
            result = ListenResult(
                ListenStatus.TRANSCRIPTION_ERROR,
                message=f"Unexpected audio error: {exc}",
            )
        self.finished.emit(result)


class SpeakWorker(QObject):
    """Speaks text on its own thread so the UI never blocks on audio output.

    The speech engine is COM-based on Windows, so this worker initializes COM on
    its own thread when it starts and releases the engine (and COM) with
    :meth:`shutdown` before the thread exits. Skipping that cleanup is what makes
    pyttsx3 crash the process at shutdown.
    """

    def __init__(self, tts) -> None:
        super().__init__()
        self._tts = tts
        self._com_initialized = False

    @Slot()
    def start(self) -> None:
        """Initialize the COM apartment for this thread (Windows only)."""
        try:
            import pythoncom  # type: ignore[import-not-found]

            pythoncom.CoInitialize()
            self._com_initialized = True
        except Exception:  # pragma: no cover - non-Windows or missing pywin32
            self._com_initialized = False

    @Slot(str)
    def say(self, text: str) -> None:
        if not self._com_initialized:
            self.start()
        try:
            self._tts.say(text)
        except Exception:  # pragma: no cover - speech must never crash
            pass

    @Slot()
    def shutdown(self) -> None:
        """Release the engine, then the COM apartment, on this thread."""
        try:
            shutdown = getattr(self._tts, "shutdown", None)
            if shutdown is not None:
                shutdown()
        except Exception:  # pragma: no cover - best-effort cleanup
            pass
        if self._com_initialized:
            try:
                import pythoncom  # type: ignore[import-not-found]

                pythoncom.CoUninitialize()
            except Exception:  # pragma: no cover
                pass
            self._com_initialized = False
