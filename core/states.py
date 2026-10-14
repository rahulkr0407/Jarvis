"""The assistant state enum.

The assistant is intentionally IDLE by default. It only leaves IDLE when the
user explicitly activates it. Each state has a single, narrow meaning:

- ``IDLE``               Nothing is happening. No device is active.
- ``LISTENING``          The user activated the assistant and it may gather a
                         command. (Phase 1: a label only; no microphone.)
- ``AWAITING_APPROVAL``  A specific action was proposed and is waiting for the
                         user to approve or reject it.
- ``EXECUTING``          An approved action is (about to be) run.
"""

from __future__ import annotations

from enum import Enum


class AssistantState(str, Enum):
    """Discrete states of the assistant.

    Subclassing ``str`` keeps the values human-readable and easy to log or show
    in the UI.
    """

    IDLE = "IDLE"
    LISTENING = "LISTENING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
