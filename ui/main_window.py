"""The JARVIS window (Phases 2–4: voice I/O, structured commands, actions).

It shows the assistant status, a transcript area, an explicit activation
control, a cancel/stop control, a typed-command box, an "Open File…" picker, and
the approval panel.

Safety-relevant UI rules honoured here:

* Nothing starts automatically. The only ways to begin listening are the
  Activate button or the ``Ctrl+Space`` shortcut. The microphone is opened
  **only** while listening, for a single utterance, and is closed immediately
  afterwards.
* Typed commands never touch the microphone; they reuse the same router and
  approval flow, which makes the app testable without audio hardware.
* The UI never claims success on its own. It renders the controller's real state
  and the executor's real outcome (implemented actions report what happened;
  anything else reports "not implemented").
* Cancel stops the audio worker and clears any pending proposal before it runs.
"""

from __future__ import annotations

from PySide6.QtCore import QMetaObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from actions.base import ActionContext, build_action_context
from actions.registry import build_executor
from audio.microphone import MicrophoneRecorder
from audio.stt import VoskSpeechToText
from audio.tts import Pyttsx3TextToSpeech
from config import settings
from core.assistant import VoiceAssistant
from core.command_router import CommandRouter
from core.controller import AssistantController, ExecutionOutcome
from core.states import AssistantState
from core.voice_pipeline import VoiceCommandPipeline
from security.policy import build_default_policy
from ui.workers import ListenWorker, SpeakWorker

# Friendly, one-line description for each state, shown under the status.
_STATE_DESCRIPTIONS = {
    AssistantState.IDLE: "Idle. Nothing is running. Activate to begin.",
    AssistantState.LISTENING: "Listening for one command, then the mic turns off.",
    AssistantState.AWAITING_APPROVAL: "A proposed action is waiting for your approval.",
    AssistantState.EXECUTING: "Running the approved action.",
}


class MainWindow(QMainWindow):
    """The main application window."""

    # Emitted (on the GUI thread) to hand text to the TTS worker thread.
    speak_requested = Signal(str)

    def __init__(
        self,
        controller: AssistantController | None = None,
        parent: QWidget | None = None,
        *,
        action_context: ActionContext | None = None,
    ) -> None:
        super().__init__(parent)
        if controller is None:
            self._action_context = action_context or build_action_context()
            controller = AssistantController(
                build_default_policy(),
                executor=build_executor(self._action_context),
            )
        else:
            # A controller was injected (tests); keep any context for the picker.
            self._action_context = action_context
        self._controller = controller
        self._controller.add_listener(self._on_event)

        # Worker-thread bookkeeping.
        self._listen_thread: QThread | None = None
        self._listen_worker: ListenWorker | None = None
        self._speak_thread: QThread | None = None
        self._speak_worker: SpeakWorker | None = None

        self.setWindowTitle("JARVIS")
        self.resize(620, 520)

        self._build_ui()
        self._build_voice()
        self._install_shortcut()

        # Periodically let the controller expire stale approvals, keeping the
        # displayed state honest even if the user never clicks anything.
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(lambda: self._controller.check_timeout())
        self._timer.start()

        self._render()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 24px; font-weight: 600;")
        layout.addWidget(self.status_label)

        self.description_label = QLabel()
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(divider)

        # Activation / stop controls
        controls = QHBoxLayout()
        self.activate_button = QPushButton("Activate (Ctrl+Space)")
        self.activate_button.clicked.connect(self._on_activate)
        controls.addWidget(self.activate_button)

        self.cancel_button = QPushButton("Cancel / Stop")
        self.cancel_button.clicked.connect(self._on_cancel)
        controls.addWidget(self.cancel_button)
        layout.addLayout(controls)

        # Typed command box (works without a microphone).
        typed = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText(
            'Try "open notepad", "what time is it", "list files in documents", '
            '"create folder plans in documents", or "cancel"'
        )
        self.command_input.returnPressed.connect(self._on_send_command)
        typed.addWidget(self.command_input)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._on_send_command)
        typed.addWidget(self.send_button)

        self.open_file_button = QPushButton("Open File…")
        self.open_file_button.clicked.connect(self._on_open_file)
        typed.addWidget(self.open_file_button)
        layout.addLayout(typed)

        # Transcript area
        self.transcript_label = QLabel("Transcript will appear here.")
        self.transcript_label.setWordWrap(True)
        self.transcript_label.setStyleSheet("color: #444;")
        layout.addWidget(self.transcript_label)

        # Approval panel (only visible while awaiting approval)
        self.approval_panel = QFrame()
        self.approval_panel.setFrameShape(QFrame.Shape.StyledPanel)
        panel_layout = QVBoxLayout(self.approval_panel)
        self.proposal_label = QLabel()
        self.proposal_label.setWordWrap(True)
        panel_layout.addWidget(self.proposal_label)

        approval_buttons = QHBoxLayout()
        self.approve_button = QPushButton("Approve")
        self.approve_button.clicked.connect(self._on_approve)
        approval_buttons.addWidget(self.approve_button)

        self.reject_button = QPushButton("Reject")
        self.reject_button.clicked.connect(self._on_reject)
        approval_buttons.addWidget(self.reject_button)
        panel_layout.addLayout(approval_buttons)
        layout.addWidget(self.approval_panel)

        # Result / message area
        self.message_label = QLabel("")
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        layout.addStretch(1)

    def _build_voice(self) -> None:
        """Wire the Qt-free voice components with worker threads."""
        router = CommandRouter()
        self._pipeline = VoiceCommandPipeline(
            MicrophoneRecorder(), VoskSpeechToText(), router
        )
        self._assistant = VoiceAssistant(
            self._controller, router, speak=self._speak
        )

        # Text-to-speech runs on its own thread.
        self._speak_thread = QThread(self)
        self._speak_worker = SpeakWorker(Pyttsx3TextToSpeech())
        self._speak_worker.moveToThread(self._speak_thread)
        self._speak_thread.started.connect(self._speak_worker.start)
        self.speak_requested.connect(
            self._speak_worker.say, Qt.ConnectionType.QueuedConnection
        )
        self._speak_thread.start()

    def _install_shortcut(self) -> None:
        """Bind the explicit activation shortcut from settings."""
        self._shortcut = QShortcut(QKeySequence(settings.ACTIVATION_SHORTCUT), self)
        self._shortcut.activated.connect(self._on_activate)

    # ------------------------------------------------------------------ #
    # Speech output
    # ------------------------------------------------------------------ #
    def _speak(self, text: str) -> None:
        """Queue a spoken line on the TTS worker thread."""
        self.speak_requested.emit(text)

    # ------------------------------------------------------------------ #
    # User gestures
    # ------------------------------------------------------------------ #
    def _on_activate(self) -> None:
        if self._controller.state is not AssistantState.IDLE:
            return
        if not self._assistant.request_listening():
            return
        self._start_listening()

    def _start_listening(self) -> None:
        """Start one listen/transcribe cycle on a worker thread."""
        self.transcript_label.setText("Listening… (speak one command)")
        self._listen_thread = QThread(self)
        self._listen_worker = ListenWorker(self._pipeline)
        self._listen_worker.moveToThread(self._listen_thread)
        self._listen_thread.started.connect(self._listen_worker.run)
        self._listen_worker.finished.connect(self._on_listen_finished)
        self._listen_worker.finished.connect(self._listen_thread.quit)
        self._listen_thread.finished.connect(self._listen_worker.deleteLater)
        self._listen_thread.finished.connect(self._on_listen_thread_finished)
        self._listen_thread.start()

    def _on_listen_finished(self, result) -> None:
        if result.transcript:
            self.transcript_label.setText(f'Heard: "{result.transcript}"')
        elif result.status.value == "OK":
            self.transcript_label.setText("Heard nothing intelligible.")
        else:
            self.transcript_label.setText(f"No transcription ({result.status.value}).")
        self._assistant.handle_listen_result(result)
        self._render()

    def _on_listen_thread_finished(self) -> None:
        self._listen_thread = None
        self._listen_worker = None

    def _on_cancel(self) -> None:
        # Stop audio work first, then clear the assistant state.
        if self._listen_worker is not None:
            self._listen_worker.stop()
        self._controller.cancel()
        self.transcript_label.setText("Stopped.")
        self.message_label.setText("Stopped. Any pending action was discarded.")
        self._render()

    def _on_send_command(self) -> None:
        text = self.command_input.text().strip()
        if not text:
            return
        self.command_input.clear()
        self.transcript_label.setText(f'Typed: "{text}"')
        self._assistant.submit_text(text)
        self._render()

    def _on_open_file(self) -> None:
        """Let the user pick a file, then propose opening it for approval."""
        start_dir = ""
        if self._action_context is not None:
            home = self._action_context.folder_map.get("home")
            if home is not None:
                start_dir = str(home)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open a file (proposes an action awaiting approval)",
            start_dir,
            "Safe files (*.txt *.md *.log *.csv *.json *.pdf *.png *.jpg "
            "*.jpeg *.gif *.bmp);;All files (*)",
        )
        if not path:
            return
        self.transcript_label.setText(f'Picked file: "{path}"')
        self._assistant.propose_action("open_file", {"path": path})
        self._render()

    def _on_approve(self) -> None:
        try:
            self._controller.approve()
        except Exception as exc:
            self.message_label.setText(f"Approval refused: {exc}")

    def _on_reject(self) -> None:
        try:
            self._controller.reject()
        except Exception as exc:
            self.message_label.setText(f"Nothing to reject: {exc}")

    # ------------------------------------------------------------------ #
    # Controller events -> UI
    # ------------------------------------------------------------------ #
    def _on_event(self, event: str, payload: dict) -> None:
        # Controller notifications arrive synchronously on the GUI thread, so
        # updating widgets directly here is safe.
        if event == "action_finished":
            outcome: ExecutionOutcome = payload["outcome"]
            if outcome.succeeded:
                self.message_label.setText(
                    f"'{outcome.action_name}' finished: {outcome.detail}"
                )
            elif outcome.started:
                self.message_label.setText(
                    f"'{outcome.action_name}' did NOT succeed: {outcome.detail}"
                )
            else:
                self.message_label.setText(
                    f"'{outcome.action_name}' was not started: {outcome.detail}"
                )
        elif event == "cancelled":
            self.message_label.setText("Stopped. Any pending action was discarded.")
        elif event == "approval_rejected":
            self.message_label.setText("Proposal rejected.")
        elif event == "approval_expired":
            self.message_label.setText("Proposal expired and was discarded.")
        elif event == "assistant_message":
            self.message_label.setText(str(payload.get("message", "")))

        self._render()

    def _render(self) -> None:
        """Redraw the window from the controller's current, real state."""
        state = self._controller.state
        self.status_label.setText(f"Status: {state.value}")
        self.description_label.setText(_STATE_DESCRIPTIONS.get(state, ""))

        awaiting = state is AssistantState.AWAITING_APPROVAL
        self.approval_panel.setVisible(awaiting)
        if awaiting:
            pending = self._controller.pending_approval
            if pending is not None:
                self.proposal_label.setText(
                    f"Proposed: {self._describe(pending.action_name, pending.arguments)}\n"
                    f"Action: {pending.action_name}\n"
                    f"Arguments: {dict(pending.arguments)}\n"
                    f"Expires at: {pending.expires_at:.1f}"
                )

        accepting_input = state in (AssistantState.IDLE, AssistantState.LISTENING)
        self.activate_button.setEnabled(state is AssistantState.IDLE)
        self.command_input.setEnabled(accepting_input)
        self.send_button.setEnabled(accepting_input)
        self.open_file_button.setEnabled(accepting_input)
        self.cancel_button.setEnabled(state is not AssistantState.IDLE)

    @staticmethod
    def _describe(action_name: str, arguments) -> str:
        """Return a short, human-readable summary of a proposal."""
        args = dict(arguments)
        if action_name == "open_application":
            return f"Open application '{args.get('target')}'"
        if action_name == "open_url":
            return f"Open URL {args.get('url')}"
        if action_name == "list_directory":
            return f"List folder '{args.get('location')}'"
        if action_name == "create_folder":
            return f"Create folder '{args.get('name')}' in '{args.get('location')}'"
        if action_name == "open_file":
            target = args.get("path") or args.get("name")
            return f"Open file '{target}'"
        if action_name == "tell_time":
            return "Report the current time"
        if action_name == "set_volume":
            return f"Set volume to {args.get('level')}"
        if action_name == "search_web":
            return f"Search the web for '{args.get('query')}'"
        return action_name

    # ------------------------------------------------------------------ #
    # Shutdown
    # ------------------------------------------------------------------ #
    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self._listen_worker is not None:
            self._listen_worker.stop()
        if self._listen_thread is not None:
            self._listen_thread.quit()
            self._listen_thread.wait(2000)
        if self._speak_worker is not None:
            # Ask the TTS worker to release its engine *on its own thread*
            # before we stop the event loop; skipping this crashes pyttsx3.
            QMetaObject.invokeMethod(
                self._speak_worker,
                "shutdown",
                Qt.ConnectionType.BlockingQueuedConnection,
            )
        if self._speak_thread is not None:
            self._speak_thread.quit()
            self._speak_thread.wait(2000)
        super().closeEvent(event)
