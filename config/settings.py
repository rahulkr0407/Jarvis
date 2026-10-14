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
ALLOWED_ACTIONS: tuple[str, ...] = (
    "open_application",
    "set_volume",
    "search_web",
)

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
