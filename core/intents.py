"""The vocabulary of structured commands, and the validators that guard it.

Speech and typed text are **untrusted input**. This module defines the small,
closed set of things the assistant may ever turn that input into, and the strict
rules each argument must satisfy before an :class:`Intent` is allowed to exist.

Design notes:

* An :class:`Intent` is a *proposal shape only*. It carries an allowlisted action
  name plus already-validated, bounded arguments. Creating an intent never runs
  anything and never touches the controller.
* :class:`IntentName` is the complete list of recognized commands. ``UNKNOWN``
  exists as an explicit value for callers that want to name "no match", but the
  router reports a non-match as ``None``; ``UNKNOWN`` is therefore never proposed.
* Every validator rejects the same dangerous shapes: path separators, ``..``
  traversal, control characters, and over-long values. There is no way to smuggle
  a raw shell command or an arbitrary filesystem path through an argument.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from config import settings

# An application or folder name: starts alphanumeric, no separators, no quotes.
_APP_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,63}$")
_FOLDER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,63}$")


class IntentName(str, Enum):
    """The complete, closed set of command names the router may produce."""

    OPEN_APPLICATION = "open_application"
    OPEN_URL = "open_url"
    OPEN_FILE = "open_file"
    SEARCH_WEB = "search_web"
    TELL_TIME = "tell_time"
    LIST_DIRECTORY = "list_directory"
    CREATE_FOLDER = "create_folder"
    CANCEL_COMMAND = "cancel_command"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Intent:
    """A proposed action parsed from text. Not yet approved or executed.

    ``arguments`` is frozen into a read-only mapping so an already-parsed intent
    cannot be silently edited before it reaches the approval layer.
    """

    action_name: str
    arguments: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "arguments", MappingProxyType(dict(self.arguments))
        )


# --------------------------------------------------------------------------- #
# Argument validators
# --------------------------------------------------------------------------- #
def validate_app_target(raw: str) -> str | None:
    """Return a safe application target, or ``None`` if it is not acceptable.

    Rejects anything with path separators (``/``, ``\\``), ``..`` traversal,
    control characters, or an over-long name.
    """
    target = (raw or "").strip()
    if not target or ".." in target:
        return None
    if not _APP_TARGET.match(target):
        return None
    return target


def validate_search_query(raw: str) -> str | None:
    """Return a length-capped search query, or ``None`` if it is empty."""
    query = (raw or "").strip()
    if not query:
        return None
    return query[: settings.MAX_SEARCH_QUERY_LENGTH]


def validate_folder_name(raw: str) -> str | None:
    """Return a safe, single-segment folder name, or ``None`` if unacceptable.

    No separators, no ``..`` traversal, no control characters, and bounded length.
    """
    name = (raw or "").strip()
    if not name or ".." in name:
        return None
    if len(name) > settings.MAX_FOLDER_NAME_LENGTH:
        return None
    if not _FOLDER_NAME.match(name):
        return None
    return name


def resolve_safe_root(raw: str) -> str | None:
    """Map a location word to a canonical safe root name, or ``None``.

    Only names in :data:`config.settings.SAFE_FOLDERS` are accepted; these are
    well-known user folders. Arbitrary or absolute paths can never pass here.
    """
    token = " ".join((raw or "").strip().lower().split())
    for prefix in ("my ", "the "):
        if token.startswith(prefix):
            token = token[len(prefix):].strip()
    if token in settings.SAFE_FOLDERS:
        return token
    return None
