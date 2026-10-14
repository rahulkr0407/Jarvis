"""Central configuration for JARVIS.

All tunable values live here as typed constants so the rest of the application
imports from a single source of truth. Plain Python is used on purpose: there is
no parsing and no extra dependency to keep the project easy to reason about and
to test.

Nothing in this file grants any capability to the assistant. It only describes
*limits*: how long an approval lasts, which shortcut activates listening, which
action names the policy may even consider, and how voice capture behaves.
"""

from __future__ import annotations

from pathlib import Path

#: Repository root (the folder that contains ``app/``, ``core/`` ...).
PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------- #
# Approval behaviour
# --------------------------------------------------------------------------- #
# How long a proposed action stays valid while waiting for the user to approve
# it. After this many seconds the proposal is discarded and the assistant
# returns to IDLE. A stale approval can never be replayed.
APPROVAL_TIMEOUT_SECONDS: float = 30.0

# --------------------------------------------------------------------------- #
# Activation
# --------------------------------------------------------------------------- #
# Explicit keyboard shortcut that activates listening. Microphone capture must
# only ever begin from an explicit user gesture such as this shortcut or the
# activation button. Nothing here starts any device.
ACTIVATION_SHORTCUT: str = "Ctrl+Space"

# --------------------------------------------------------------------------- #
# Policy allowlist
# --------------------------------------------------------------------------- #
# The ONLY action names JARVIS may ever propose. This is an allowlist: anything
# not listed here is denied by default. Later phases attach handlers; approving
# any of them still does nothing yet.
#
# Note: ``cancel_command`` is intentionally absent. It is a *control* command
# (stop everything, clear any pending proposal), not an action, so it is handled
# directly and never requires approval.
ALLOWED_ACTIONS: tuple[str, ...] = (
    "open_application",
    "set_volume",
    "search_web",
    "tell_time",
    "list_directory",
    "create_folder",
    "open_url",
    "open_file",
)

# --------------------------------------------------------------------------- #
# Command parsing limits (Phase 3)
# --------------------------------------------------------------------------- #
# Longest accepted search query, in characters. Anything longer is truncated.
MAX_SEARCH_QUERY_LENGTH: int = 200

# Longest accepted new-folder name, in characters.
MAX_FOLDER_NAME_LENGTH: int = 64

# The ONLY locations list_directory / create_folder may target. These are
# well-known *names* for the user's own folders; the router never accepts an
# absolute path, a drive, or a relative path with separators.
SAFE_FOLDERS: tuple[str, ...] = (
    "home",
    "desktop",
    "documents",
    "downloads",
)

# The location used when a command names no folder.
DEFAULT_SAFE_FOLDER: str = "home"

# --------------------------------------------------------------------------- #
# Phase 4: permission-controlled actions
# --------------------------------------------------------------------------- #
# Human-readable descriptions shown alongside a proposal before approval.
ACTION_DESCRIPTIONS: dict[str, str] = {
    "open_application": "Launch an allowlisted application.",
    "open_url": "Open an http(s) URL in the default browser.",
    "list_directory": "Read the contents of a permitted folder.",
    "create_folder": "Create a new folder inside a permitted location.",
    "open_file": "Open a permitted, non-executable file.",
    "search_web": "Open a web search for a query (not implemented).",
    "tell_time": "Report the current time (not implemented).",
    "set_volume": "Change the system volume (not implemented).",
}

# Applications JARVIS may launch. Maps a command word to an explicit argument
# vector (argv). Only names listed here can ever launch; everything else is
# refused. Prefer absolute paths for the strongest guarantee (see README risks);
# a bare name is resolved with ``shutil.which`` (PATH lookup).
APPLICATION_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "notepad": ("notepad.exe",),
    "calculator": ("calc.exe",),
    "paint": ("mspaint.exe",),
    "explorer": ("explorer.exe",),
}

# The sandbox for every file action. Relative paths resolve against PROJECT_ROOT.
# Nothing outside this tree can be listed, created, or opened.
WORKSPACE_ROOT: str = "workspace"

# Folder words (from Phase 3) mapped to sub-directories of WORKSPACE_ROOT.
# "." means the workspace root itself. Change these only to deliberately widen
# where file actions may operate.
FOLDER_MAP: dict[str, str] = {
    "home": ".",
    "desktop": "desktop",
    "documents": "documents",
    "downloads": "downloads",
}

# File extensions open_file may open. Executable/script/link types are absent on
# purpose: opening them would run code.
SAFE_OPEN_EXTENSIONS: tuple[str, ...] = (
    ".txt",
    ".md",
    ".log",
    ".csv",
    ".json",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
)

# Hard time limit for a single action, in seconds.
EXECUTION_TIMEOUT_SECONDS: float = 5.0

# Most directory entries list_directory will show in one result.
MAX_DIRECTORY_ENTRIES: int = 50

# When True, actions report what they WOULD do and touch nothing. Safe for
# development. Also settable from the command line with ``--dry-run``.
DRY_RUN: bool = False

# Append-only JSON-lines audit log. Relative paths resolve against PROJECT_ROOT.
# Arguments are scrubbed before writing; secrets are never stored.
AUDIT_LOG_PATH: str = "logs/audit.log"

# --------------------------------------------------------------------------- #
# Voice input (Phase 2)
# --------------------------------------------------------------------------- #
# Path to the offline Vosk model, relative to PROJECT_ROOT unless absolute.
# The model is NOT bundled and is NOT auto-downloaded. See README.md.
VOSK_MODEL_PATH: str = "models/vosk-model-small-en-us-0.15"

# Sample rate expected by the model. 16000 Hz is standard for Vosk small models.
VOSK_SAMPLE_RATE: int = 16000

# Microphone capture settings.
# One utterance is captured per activation; capture always stops afterwards.
RECORD_MAX_SECONDS: float = 8.0          # hard cap on a single capture
SILENCE_TIMEOUT_SECONDS: float = 1.5     # stop this long after speech stops
NO_SPEECH_TIMEOUT_SECONDS: float = 6.0   # give up if nothing is said in time
SILENCE_RMS_THRESHOLD: int = 500         # int16 RMS below this counts as silence
AUDIO_BLOCK_FRAMES: int = 8000           # ~0.5 s per read at 16 kHz

# --------------------------------------------------------------------------- #
# Voice output (Phase 2)
# --------------------------------------------------------------------------- #
TTS_ENABLED: bool = True
TTS_RATE: int = 180      # words per minute
TTS_VOLUME: float = 1.0  # 0.0 .. 1.0


def resolve_model_path() -> Path:
    """Return the Vosk model path as an absolute :class:`Path`.

    Relative paths are resolved against :data:`PROJECT_ROOT` so the app works
    regardless of the current working directory.
    """
    path = Path(VOSK_MODEL_PATH)
    return path if path.is_absolute() else PROJECT_ROOT / path
