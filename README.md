# JARVIS — Personal AI Assistant for Windows

JARVIS is a desktop assistant for Windows, built to **eventually** control a
laptop through voice commands. It now contains **Phase 1 (safe foundation)**,
**Phase 2 (voice input + spoken replies)**, **Phase 3 (structured, validated
command parsing)**, and **Phase 4 (permission-controlled actions)**.

Phase 4 adds a small set of real, permission-gated Windows actions. Approving an
action that is *not* implemented (for example `tell_time` or `set_volume`) still
reports "not implemented" honestly — JARVIS never claims a success that did not
happen.

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

### Phase 3 — structured, validated command parsing
- A closed vocabulary of intents: `open_application`, `search_web`, `tell_time`,
  `list_directory`, `create_folder`, `cancel_command`, `unknown`.
- Speech/typed text is turned into an `Intent` **only** after its arguments pass
  strict validators (no path separators, no `..` traversal, no control
  characters, bounded length).
- `list_directory` / `create_folder` may target only the user's **named safe
  folders** (`home`, `desktop`, `documents`, `downloads`) — never an absolute or
  arbitrary path.
- `cancel_command` ("stop", "never mind", "cancel") is a **control** command: it
  stops everything and clears any pending proposal with **no approval**.
- Unknown or unsafe input returns no intent and yields a spoken clarification,
  then returns to `IDLE`.
- Parsing stays fully **offline and deterministic**; no LLM is involved.
- 79 additional automated tests (163 total).

Not in Phase 3: real actions (still "not implemented"), any cloud/LLM parsing,
wake-word listening, or operating-system control.

### Phase 4 — permission-controlled actions
- **Open an allowlisted application** (`open notepad`) — launched with
  `subprocess.Popen` and an explicit argument list, never `shell=True`.
- **Open an approved URL** (`go to example.com`) — http/https only, in the
  default browser.
- **Read a permitted directory** (`list files in documents`).
- **Create a folder in the workspace** (`create folder plans in documents`).
- **Open a permitted file** (`open notes.txt`, or pick one with **Open File…**).
- Every action is its own module under `actions/`, runs only after an exact-match
  approval, has a hard timeout, and is written to an **audit log** with its
  arguments scrubbed of secrets.
- A project-local **`workspace/` sandbox**: file actions can never reach a real
  user folder unless you deliberately reconfigure the folder map.
- **Dry-run mode** (`--dry-run`) reports what each action *would* do and touches
  nothing.
- 80 additional automated tests (244 total; all actions are mocked).

Not in Phase 4: destructive actions, arbitrary scripts, registry changes,
credential access, unrestricted system commands, mouse/keyboard automation, or
shutdown/deletion. Those remain permanently unsupported.

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

Add `--dry-run` to make every action report what it *would* do without launching
an application or changing any file:

```powershell
python -m app.main --dry-run
```

The window opens in **IDLE**. Then:

- Click **Activate** or press **Ctrl+Space** to listen. The mic opens, captures
  **one** utterance, then closes. The transcript appears in the UI.
- If the transcript maps to an allowed action, it becomes a **proposal** and the
  approval panel appears — approve or reject it.
- Type a command in the box (e.g. `open notepad`, `go to example.com`,
  `list files in documents`, `create folder plans in documents`, `open
  notes.txt`) and click **Send** to test without a microphone.
- Use **Open File…** to pick a permitted file; it becomes an `open_file`
  proposal that still needs approval.
- **Cancel / Stop** stops any capture and clears any pending proposal. Typing
  `cancel` / `stop` does the same without needing approval.

### Configuring Phase 4 (`config/settings.py`)

- `APPLICATION_ALLOWLIST` — the only applications `open_application` may launch
  (name → argv). Prefer absolute paths to the executable.
- `WORKSPACE_ROOT` and `FOLDER_MAP` — the sandbox and how `home`/`desktop`/
  `documents`/`downloads` map into it.
- `SAFE_OPEN_EXTENSIONS` — the file types `open_file` may open.
- `EXECUTION_TIMEOUT_SECONDS`, `MAX_DIRECTORY_ENTRIES`, `DRY_RUN`,
  `AUDIT_LOG_PATH`.

## Run the tests

```powershell
python -m pytest
```

The suite uses fake audio components and **mocks every OS call**, so it needs
**no microphone, no model, no display, no browser, and it never launches an
application or changes your files**.

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
├── actions/                 # Phase 4: permission-controlled actions
│   ├── __init__.py
│   ├── base.py              # ActionResult, ActionContext, error types
│   ├── paths.py             # Workspace confinement + root resolution
│   ├── audit.py             # File/Null audit logger + secret redaction
│   ├── open_application.py  # Launch an allowlisted app
│   ├── open_url.py          # http/https URL validation + open
│   ├── list_directory.py    # Read a permitted directory
│   ├── create_folder.py     # Create a folder inside the workspace
│   ├── open_file.py         # Open a permitted file (extension allowlist)
│   └── registry.py          # Handler table + timeout-guarded executor
├── core/                    # Qt-free domain + orchestration
│   ├── __init__.py
│   ├── states.py            # AssistantState enum
│   ├── state_machine.py     # Transition table + InvalidTransitionError
│   ├── controller.py        # State/policy/approval/execution authority
│   ├── intents.py           # Phase 3: Intent vocabulary + argument validators
│   ├── command_router.py    # Phase 3: text -> validated Intent (or None)
│   ├── voice_pipeline.py    # Phase 2: record -> transcribe -> route
│   └── assistant.py         # Phase 2/3: orchestration (proposal, reply, cancel)
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
│   ├── test_command_router.py   # Phase 2/3/4
│   ├── test_intents.py          # Phase 3
│   ├── test_voice_pipeline.py   # Phase 2
│   ├── test_assistant.py        # Phase 2/3/4
│   ├── test_action_paths.py          # Phase 4
│   ├── test_action_open_application.py
│   ├── test_action_open_url.py
│   ├── test_action_list_directory.py
│   ├── test_action_create_folder.py
│   ├── test_action_open_file.py
│   ├── test_executor_registry.py
│   └── test_actions_integration.py
├── models/                  # Vosk model (downloaded; git-ignored)
├── workspace/               # Phase 4 sandbox for file actions (git-ignored)
├── logs/                    # Phase 4 audit log (git-ignored)
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
- **`actions/`** — Phase 4. The only code allowed to touch the OS. Each action is
  a small, independent module with the same shape: validate → do the one thing →
  return an `ActionResult`. Qt-free and controller-free.
  - `base.py` defines `ActionResult` (never raise to the caller), `ActionContext`
    (permitted folders, app allowlist, extensions, timeout, dry-run, audit), and
    the action error types.
  - `paths.py` confines every file operation to the workspace: arguments are
    resolved and checked with `Path.resolve()` + `is_relative_to`, so `..` and
    symlink escapes are refused.
  - `audit.py` appends one JSON line per attempt to `logs/audit.log`, with URL
    credentials/tokens and other secrets redacted.
  - `registry.py` maps action names to handlers and wraps each call with a
    **timeout guard** (a one-shot daemon thread) so a stuck action cannot hang the
    assistant.
- **`core/`** — the "brain". Pure Python.
  - `state_machine.py` declares every legal move in one table.
  - `controller.py` is the only place states change; it enforces policy and
    approvals, then interprets the returned `ActionResult` (success/failure/detail)
    so the UI never reports a false success.
  - `intents.py` defines the small, closed vocabulary of intents and the strict
    validators that every argument must pass before an `Intent` may exist.
  - `command_router.py` is the **untrusted-text boundary**: only a few phrase
    shapes are recognized, `open_application` targets must be in the app
    allowlist, URL schemes are limited to http/https, open-file extensions are
    checked, and arguments are validated/bounded. `cancel_command` is a control
    intent and is not gated. It returns an *intent*, never an execution.
  - `voice_pipeline.py` records one utterance, detects speech by RMS energy,
    transcribes, routes, and returns a `ListenResult`. It never touches the
    controller.
  - `assistant.py` orchestrates: OK transcript → proposal (or a spoken reply),
    `cancel_command` → immediate stop with no approval, errors → spoken reply then
    back to IDLE. It exposes `propose_action()` so the UI can offer a proposal
    (e.g. an "Open File…" pick) without executing anything itself.
- **`security/`** — the guardrails (allowlist, deny-by-default policy, expiring
  exact-match approvals).
- **`ui/`** — presentation and threading.
  - `workers.py` runs capture/transcription and speech on their own `QThread`s.
  - `main_window.py` renders the real state and forwards user gestures; it builds
    the action executor and shows a friendly description of each proposal.
- **`config/settings.py`** — one place for the approval timeout, shortcut,
  allowlists (actions and applications), workspace/folder map, safe extensions,
  execution timeout, dry-run default, audit path, and all voice settings.
- **`workspace/`** — the sandbox where file actions operate. Created on demand and
  git-ignored.
- **`logs/`** — the audit log directory. Created on demand and git-ignored.

---

## How the safety model works

1. **Idle by default.** The controller starts in `IDLE`. The only way to listen
   is the **Activate** button or **Ctrl+Space**. No microphone is opened at
   startup, and never in `IDLE`.
2. **One utterance, then off.** While `LISTENING`, the mic records a single
   utterance (capped at `RECORD_MAX_SECONDS`), then the device is closed. There
   is no continuous listening and no wake word.
3. **Speech is untrusted.** The transcript goes through `CommandRouter`, which
   only recognizes a few phrase shapes and only for **allowlisted** actions.
   Arguments must pass the validators in `intents.py` (no path separators, no
   `..`, no control characters, bounded length) and folder locations are limited
   to named safe folders. Anything else is refused. Recognition never runs an
   action.
4. **Exact approval.** An allowed phrase becomes an `ApprovalRequest` holding the
   exact action, a frozen copy of the arguments, a SHA-256 fingerprint, a random
   token, and a deadline. It is still just a proposal.
5. **Stale approvals rejected.** `approve(token)` only accepts the current
   proposal's token; an older or wrong token raises `StaleApprovalError`.
6. **Timeouts.** Past the deadline (default 30 s) the proposal is discarded and
   the assistant returns to `IDLE`; the UI polls `check_timeout()`.
7. **Cancel wins.** `cancel()` clears the pending proposal and asks the audio
   worker to stop, so a not-yet-started action can never run. Saying or typing
   `stop` / `cancel` triggers this directly, with **no approval** — a control
   command is never gated by the action allowlist.
8. **Actions are sandboxed and bounded.** File actions run only inside the
   project-local `workspace/`; `open_application` only launches names in
   `APPLICATION_ALLOWLIST` using an explicit argument list (`shell=False`);
   `open_url` only accepts http/https and rejects embedded credentials; and
   `open_file` only opens extensions in `SAFE_OPEN_EXTENSIONS`. Every action has
   a hard timeout and returns a plain `ActionResult` instead of raising.
9. **Every attempt is audited.** `logs/audit.log` records one JSON line per action
   attempt (success or failure) with a redacted argument set — never a secret.
10. **No false success.** The UI shows the executor's real outcome. Actions that
    are implemented report what actually happened; actions that are **not**
    implemented (e.g. `tell_time`, `set_volume`) report "not implemented" — never
    "success". A timed-out or failed action is shown as such.
11. **Dry-run is available.** With `--dry-run` (or `DRY_RUN=True`) each action
    reports what it *would* do and changes nothing.
12. **No cloud.** Vosk and pyttsx3 are entirely local. Audio never leaves the
    machine; actions never phone home.

---

## Technologies

- **Python 3.10+** — the language.
- **PySide6 (Qt for Python)** — widgets, signals/slots, `QShortcut`, `QTimer`,
  and `QThread` for background work.
- **Vosk** — offline speech-to-text (needs the model above).
- **sounddevice** — microphone capture via PortAudio. `RawInputStream` gives raw
  PCM bytes, so **numpy is not required**.
- **pyttsx3** — text-to-speech using local Windows SAPI5 voices.
- **Standard library** (`subprocess`, `webbrowser`, `os.startfile`, `pathlib`) —
  Phase 4 actions, always with explicit argument lists and no shell.
- **pytest** — the test runner.

---

## Known limitations (Phase 4)

- Only five actions are implemented: `open_application`, `open_url`,
  `list_directory`, `create_folder`, `open_file`. Other allowlisted intents
  (`tell_time`, `set_volume`, `search_web`) report "not implemented".
- File actions operate **only inside `workspace/`**. They cannot reach a real user
  folder unless you deliberately point `FOLDER_MAP` at one (not recommended).
- Cancellation prevents a **not-yet-started** action from running, but it cannot
  reliably reverse an OS-level action that is already executing (e.g. an app that
  has already launched).
- The timeout guard runs each action on a one-shot daemon thread; a genuinely
  stuck action is reported as timed out but its underlying thread cannot be
  force-killed.
- No wake word and no continuous listening; one command per activation.
- Speech detection uses a simple RMS energy threshold (not a VAD model), so noisy
  rooms may behave imperfectly.
- Transcription is batch (whole utterance), not streaming partials.
- The Vosk small English model is the only supported model out of the box;
  another model works by pointing `VOSK_MODEL_PATH` at it.
- TTS uses the system's default voice; voice selection is not exposed in the UI.
- Parsing is a small set of literal phrase shapes (deterministic, offline), not a
  general natural-language parser; phrasings outside those shapes are refused.
- Sub-paths within a folder are not yet supported (e.g. `documents\2026`).

---

## Phase 4 verification checklist

- [ ] `python -m pip install -e ".[dev,voice]"` completes.
- [ ] The Vosk model is extracted to `models\vosk-model-small-en-us-0.15\`.
- [ ] `python -m pytest` passes (244 tests, 1 skipped).
- [ ] `python -m app.main` opens in **IDLE** with no microphone activity.
- [ ] Typing `open notepad` shows an `open_application` proposal; approving it
      launches Notepad.
- [ ] Typing `open powershell` or `open cmd` is refused (not in the app allowlist).
- [ ] Typing `go to example.com` shows an `open_url` proposal; approving it opens
      the browser. (`https://user:pass@…` is refused.)
- [ ] Typing `list files in documents` shows a `list_directory` proposal with
      `location: documents`.
- [ ] Typing `create folder plans in documents` creates `workspace\documents\plans`.
- [ ] Typing `create folder plans in C:\Windows` or a `..` name is refused.
- [ ] **Open File…** on a permitted file (e.g. `.txt`) shows an `open_file`
      proposal; an `.exe` is refused.
- [ ] `python -m app.main --dry-run` reports "would …" and launches/changes
      nothing.
- [ ] Typing `cancel` / `stop` stops everything and clears any pending proposal
      **without** an approval prompt, and prevents a pending action from running.
- [ ] `logs\audit.log` gains one JSON line per action attempt, with secrets
      redacted.
- [ ] The UI stays responsive while an action runs (timeout guard, not the GUI
      thread).

---

## Review before moving on

This is Phase 4. **Do not begin Phase 5 yet.** Review the changes and run the
tests, then commit and push to GitHub:

```powershell
git add .
git commit -m "Phase 4: permission-controlled Windows actions"
git push
```
