# JARVIS — Personal AI Assistant for Windows

JARVIS is a desktop assistant for Windows, built to **eventually** control a
laptop through voice commands. It now contains **Phase 1 (safe foundation)** and
**Phase 2 (voice input + spoken replies)**. There are still **no real
computer-control actions**: approving anything reports "not implemented".

Safety is the point. The assistant stays **IDLE by default**, never opens the
microphone on its own, never records continuously, and never executes anything
without an explicit, exact-match approval. Speech is treated as **untrusted
input**, not permission to act.

---

## Status

### Phase 1 — safe foundation
- Explicit state machine: `IDLE`, `LISTENING`, `AWAITING_APPROVAL`, `EXECUTING`.
- Safe transitions, cancellation, rejection, invalid-transition handling, and
  approval timeouts.
- Deny-by-default action policy with an allowlist.
- PySide6 window with status, activation, cancel/stop, and an approval panel.
- Automated tests (46).

### Phase 2 — voice input and spoken replies
- Microphone capture that starts **only** after explicit activation and records
  **one utterance per activation**, then stops.
- Offline speech-to-text with **Vosk** (no cloud).
- Text-to-speech with **pyttsx3** (local Windows voices).
- Microphone errors, no-speech timeouts, transcription failures, and
  cancellation are all handled and shown in the UI.
- Audio work runs on **worker threads** so the UI never freezes.
- A **typed command box** lets you exercise the whole flow without a microphone.
- 35 additional automated tests (81 total).

Not in Phase 2: real actions, wake-word/continuous listening, cloud services, or
operating-system control.

---

## Requirements

- Windows 10/11
- Python 3.10 or newer (developed against 3.12, 64-bit)
- A microphone (for voice input) and a Windows voice (for speech output)

## Setup

From the project folder (`Desktop\Jarvis`):

```powershell
# (optional but recommended) create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# core app + tests
python -m pip install -e ".[dev]"

# voice input/output (Vosk, sounddevice, pyttsx3)
python -m pip install -e ".[voice]"

# or install everything at once
python -m pip install -e ".[dev,voice]"
```

> On a Windows Store Python install you may hit `MAX_PATH` errors from PySide6.
> A project-local `.venv` (short path) avoids this; run commands through
> `.\.venv\Scripts\python.exe` if in doubt.

### Download the speech model (required for voice input)

No model is bundled and nothing is downloaded automatically. Get the small
English Vosk model once, into `models/`:

```powershell
New-Item -ItemType Directory -Force models | Out-Null
Invoke-WebRequest -Uri "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip" -OutFile "models\vosk-model-small-en-us-0.15.zip"
Expand-Archive -Path "models\vosk-model-small-en-us-0.15.zip" -DestinationPath "models"
Remove-Item "models\vosk-model-small-en-us-0.15.zip"
```

Result (this exact path is what the app expects, see `config/settings.py`):

```
models\vosk-model-small-en-us-0.15\
```

The model is ~40 MB zipped / ~50 MB extracted and is **excluded from git** via
`.gitignore`. If the folder is missing, voice input reports a clear message and
the typed command box still works.

Model source: <https://alphacephei.com/vosk/models>

## Run the application

```powershell
python -m app.main
```

The window opens in **IDLE**. Then:

- Click **Activate** or press **Ctrl+Space** to listen. The mic opens, captures
  **one** utterance, then closes. The transcript appears in the UI.
- If the transcript maps to an allowed action, it becomes a **proposal** and the
  approval panel appears — approve or reject it.
- Type a command in the box (e.g. `open notepad`, `set volume 30`,
  `search for cats`) and click **Send** to test without a microphone.
- **Cancel / Stop** stops any capture and clears any pending proposal.

## Run the tests

```powershell
python -m pytest
```

The suite uses fake audio components, so it needs **no microphone, no model, and
no display**.

---

## Project structure

```
Jarvis/
├── app/
│   ├── __init__.py
│   └── main.py              # Entry point: builds QApplication + window
├── audio/                   # Phase 2: Qt-free audio layer
│   ├── __init__.py
│   ├── errors.py            # AudioError and subclasses
│   ├── microphone.py        # MicrophoneRecorder (sounddevice, lazy import)
│   ├── stt.py               # SpeechToText protocol + VoskSpeechToText
│   └── tts.py               # TextToSpeech protocol + Pyttsx3/Null TTS
├── core/                    # Qt-free domain + orchestration
│   ├── __init__.py
│   ├── states.py            # AssistantState enum
│   ├── state_machine.py     # Transition table + InvalidTransitionError
│   ├── controller.py        # State/policy/approval/execution authority
│   ├── command_router.py    # Phase 2: text -> allowlisted Intent (or None)
│   ├── voice_pipeline.py    # Phase 2: record -> transcribe -> route
│   └── assistant.py         # Phase 2: orchestration (proposal or reply)
├── security/                # Guardrails
│   ├── __init__.py
│   ├── actions.py           # ActionSpec + ActionRegistry (the allowlist)
│   ├── policy.py            # ActionPolicy: deny-by-default
│   └── approval.py          # Expiring, exact-match ApprovalRequest
├── ui/
│   ├── __init__.py
│   ├── workers.py           # Phase 2: QThread workers (listen, speak)
│   └── main_window.py       # PySide6 window
├── tests/
│   ├── __init__.py
│   ├── fakes.py             # Phase 2: fake recorder/STT/TTS + clock
│   ├── test_state_machine.py
│   ├── test_policy.py
│   ├── test_approval.py
│   ├── test_controller.py
│   ├── test_command_router.py   # Phase 2
│   ├── test_voice_pipeline.py   # Phase 2
│   └── test_assistant.py        # Phase 2
├── models/                  # Vosk model (downloaded; git-ignored)
├── config/
│   ├── __init__.py
│   └── settings.py          # Timeout, shortcut, allowlist, voice config
├── pyproject.toml           # Metadata, dependencies, pytest config
├── .gitignore
└── README.md
```

### What each part does

- **`app/main.py`** — starts Qt and shows the window. Nothing else runs on
  startup; no microphone is opened.
- **`audio/`** — the hardware boundary. Qt-free and controller-free. Every
  third-party import (`sounddevice`, `vosk`, `pyttsx3`) is lazy, so the app and
  tests work even without the voice extras.
  - `microphone.py` yields fixed-size PCM blocks, stops on a flag or a hard time
    limit, and always closes the device.
  - `stt.py` loads the Vosk model lazily and raises a clear error if it is
    missing.
  - `tts.py` speaks with the local Windows voice; failures are swallowed so they
    never break the assistant.
- **`core/`** — the "brain". Pure Python.
  - `state_machine.py` declares every legal move in one table.
  - `controller.py` is the only place states change; it enforces policy and
    approvals.
  - `command_router.py` is the **untrusted-text boundary**: only a few phrase
    shapes are recognized, the action must be allowlisted, and arguments are
    validated/clamped. It returns an *intent*, never an execution.
  - `voice_pipeline.py` records one utterance, detects speech by RMS energy,
    transcribes, routes, and returns a `ListenResult`. It never touches the
    controller.
  - `assistant.py` orchestrates: OK transcript → proposal (or a spoken reply),
    errors → spoken reply then back to IDLE. It can never reach `EXECUTING`.
- **`security/`** — the guardrails (allowlist, deny-by-default policy, expiring
  exact-match approvals).
- **`ui/`** — presentation and threading.
  - `workers.py` runs capture/transcription and speech on their own `QThread`s.
  - `main_window.py` renders the real state and forwards user gestures.
- **`config/settings.py`** — one place for the approval timeout, shortcut,
  allowlist, and all voice settings (model path, sample rate, timeouts, TTS).

---

## How the safety model works

1. **Idle by default.** The controller starts in `IDLE`. The only way to listen
   is the **Activate** button or **Ctrl+Space**. No microphone is opened at
   startup, and never in `IDLE`.
2. **One utterance, then off.** While `LISTENING`, the mic records a single
   utterance (capped at `RECORD_MAX_SECONDS`), then the device is closed. There
   is no continuous listening and no wake word.
3. **Speech is untrusted.** The transcript goes through `CommandRouter`, which
   only recognizes a few phrases and only for **allowlisted** actions. Anything
   else is refused. Recognition never runs an action.
4. **Exact approval.** An allowed phrase becomes an `ApprovalRequest` holding the
   exact action, a frozen copy of the arguments, a SHA-256 fingerprint, a random
   token, and a deadline. It is still just a proposal.
5. **Stale approvals rejected.** `approve(token)` only accepts the current
   proposal's token; an older or wrong token raises `StaleApprovalError`.
6. **Timeouts.** Past the deadline (default 30 s) the proposal is discarded and
   the assistant returns to `IDLE`; the UI polls `check_timeout()`.
7. **Cancel wins.** `cancel()` clears the pending proposal and asks the audio
   worker to stop, so a not-yet-started action can never run.
8. **No false success.** The UI shows the executor's real `ExecutionOutcome`. In
   Phase 2 nothing is implemented, so an approved action reports "not
   implemented" — never "success".
9. **No cloud.** Vosk and pyttsx3 are entirely local. Audio never leaves the
   machine.

---

## Technologies

- **Python 3.10+** — the language.
- **PySide6 (Qt for Python)** — widgets, signals/slots, `QShortcut`, `QTimer`,
  and `QThread` for background work.
- **Vosk** — offline speech-to-text (needs the model above).
- **sounddevice** — microphone capture via PortAudio. `RawInputStream` gives raw
  PCM bytes, so **numpy is not required**.
- **pyttsx3** — text-to-speech using local Windows SAPI5 voices.
- **pytest** — the test runner.

---

## Known limitations (Phase 2)

- No real actions: approving anything reports "not implemented".
- No wake word and no continuous listening; one command per activation.
- Speech detection uses a simple RMS energy threshold (not a VAD model), so noisy
  rooms may behave imperfectly.
- Transcription is batch (whole utterance), not streaming partials.
- The Vosk small English model is the only supported model out of the box;
  another model works by pointing `VOSK_MODEL_PATH` at it.
- TTS uses the system's default voice; voice selection is not exposed in the UI.

---

## Phase 2 verification checklist

- [ ] `python -m pip install -e ".[dev,voice]"` completes.
- [ ] The Vosk model is extracted to `models\vosk-model-small-en-us-0.15\`.
- [ ] `python -m pytest` passes (81 tests).
- [ ] `python -m app.main` opens in **IDLE** with no microphone activity.
- [ ] **Activate** / **Ctrl+Space** records exactly one utterance, then stops.
- [ ] The recognized transcript appears in the UI.
- [ ] A recognized allowed command (e.g. "open notepad") shows the approval
      panel; approve reports "not implemented"; reject/expire returns to IDLE.
- [ ] **Type** `open notepad` and click **Send** → same approval flow, no mic.
- [ ] With no model present, voice input shows a clear message; typed commands
      still work.
- [ ] **Cancel / Stop** during listening stops capture and clears any proposal.
- [ ] Unknown/unsafe speech (e.g. "run format c:") is refused (covered by tests).
- [ ] The UI stays responsive while listening (workers, not the GUI thread).

---

## Review before moving on

This is Phase 2. **Do not begin Phase 3 yet.** Review the changes and run the
tests, then commit and push to GitHub:

```powershell
git add .
git commit -m "Phase 2: offline voice input, spoken replies, worker threads"
git push
```
