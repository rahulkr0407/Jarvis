"""Turn free text into a *proposed* action — and nothing more.

Speech is untrusted input. This module is the boundary where text is allowed to
influence the assistant, and it is intentionally strict:

* Only a small set of phrase shapes is recognized.
* A recognized proposal action must be in the allowlist, or the whole thing is
  discarded.
* Arguments are validated and bounded (clamped volume, length-capped query, a
  name-like application or folder, a location limited to named safe folders).
* ``open_application`` targets are additionally checked against the configured
  **application allowlist**, and ``open_file`` targets against the safe-extension
  list, so an unsafe proposal is never even created.

Routing never executes anything. It returns an :class:`Intent`, which the
controller still requires the user to approve before anything runs.

``cancel_command`` is the one exception that is *not* a proposal: "stop"/"cancel"
is a control command, so it is recognized even when it is not in the action
allowlist, is never policy-gated, and never reaches the approval panel. The
assistant acts on it directly.

Every recognized intent's arguments have already passed the validators in
:mod:`core.intents`, so a malicious transcript can, at most, produce the same
safe shape as a harmless one — never a raw shell command or an arbitrary path.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from config import settings
from core.intents import (
    Intent,
    IntentName,
    resolve_safe_root,
    validate_app_target,
    validate_folder_name,
    validate_search_query,
)

# A URL the user typed explicitly with an http(s) scheme.
_URL_EXPLICIT = re.compile(
    r"^(?:open|go to|visit|navigate to|browse)\s+(https?://\S+)$"
)
# A URL given as "www.something".
_URL_WWW = re.compile(
    r"^(?:open|go to|visit|browse)\s+(www\.\S+)$"
)
# A bare host, only after an unambiguous navigation verb (never after "open").
_URL_HOST = re.compile(
    r"^(?:go to|visit|browse|navigate to)\s+"
    r"([a-z0-9][a-z0-9.\-]*\.[a-z]{2,}(?:/\S*)?)$"
)


class CommandRouter:
    """Maps recognized text to an allowlisted :class:`Intent` (or ``None``)."""

    def __init__(
        self,
        allowed_actions: Iterable[str] | None = None,
        application_allowlist: Mapping[str, object] | Iterable[str] | None = None,
    ) -> None:
        self._allowed = frozenset(
            settings.ALLOWED_ACTIONS if allowed_actions is None else allowed_actions
        )
        allow = (
            settings.APPLICATION_ALLOWLIST
            if application_allowlist is None
            else application_allowlist
        )
        names = allow.keys() if isinstance(allow, Mapping) else allow
        self._application_allowlist = frozenset(str(name).lower() for name in names)
        self._safe_extensions = frozenset(
            ext.lower() for ext in settings.SAFE_OPEN_EXTENSIONS
        )

    def route(self, text: str) -> Intent | None:
        """Return an Intent for ``text`` if it matches an allowed action.

        Returns ``None`` when the text is empty, unrecognized, or would map to an
        action that is not allowlisted. A ``cancel_command`` control intent is
        returned regardless of the action allowlist.
        """
        if not text:
            return None
        normalized = " ".join(text.strip().lower().split())
        if not normalized:
            return None

        # Control command: not an action, not gated, never proposed.
        cancel = self._match_cancel(normalized)
        if cancel is not None:
            return cancel

        for matcher in (
            self._match_time,
            self._match_list_dir,
            self._match_create_folder,
            self._match_open_url,
            self._match_open_file,
            self._match_open,
            self._match_volume,
            self._match_search,
        ):
            intent = matcher(normalized)
            if intent is not None and intent.action_name in self._allowed:
                return intent
        return None

    # ------------------------------------------------------------------ #
    # Individual rules
    # ------------------------------------------------------------------ #
    def _match_cancel(self, text: str) -> Intent | None:
        if re.match(
            r"^(?:cancel|cancel that|cancel command|never mind|nevermind|"
            r"forget it|stop|stop listening|abort)$",
            text,
        ):
            return Intent(IntentName.CANCEL_COMMAND.value, {})
        return None

    def _match_time(self, text: str) -> Intent | None:
        if re.match(
            r"^(?:what(?:'s| is) the time(?: now)?|what time is it|"
            r"tell me the time|current time|time)$",
            text,
        ):
            return Intent(IntentName.TELL_TIME.value, {})
        return None

    def _match_list_dir(self, text: str) -> Intent | None:
        match = re.match(
            r"^(?:list|show)\s+(?:the\s+)?(?:files|folder|directory|contents|"
            r"everything)(?:\s+(?:in|of)\s+(.+))?$",
            text,
        )
        if match is not None:
            location_raw = match.group(1)
        else:
            match = re.match(r"^what(?:'s| is)\s+in\s+(?:the\s+)?(.+)$", text)
            if match is None:
                return None
            location_raw = match.group(1)

        location = settings.DEFAULT_SAFE_FOLDER
        if location_raw:
            resolved = resolve_safe_root(location_raw)
            if resolved is None:
                return None
            location = resolved
        return Intent(IntentName.LIST_DIRECTORY.value, {"location": location})

    def _match_create_folder(self, text: str) -> Intent | None:
        match = re.match(
            r"^(?:create|make|new)\s+(?:a\s+)?(?:folder|directory|dir)\s+"
            r"(?:called\s+|named\s+)?(.+)$",
            text,
        )
        if not match:
            return None
        remainder = match.group(1).strip()
        location = settings.DEFAULT_SAFE_FOLDER

        located = re.match(r"^(.*?)\s+(?:in|under|inside)\s+(.+)$", remainder)
        if located:
            name_raw = located.group(1).strip()
            resolved = resolve_safe_root(located.group(2))
            if resolved is None:
                return None
            location = resolved
        else:
            name_raw = remainder

        name = validate_folder_name(name_raw)
        if name is None:
            return None
        return Intent(
            IntentName.CREATE_FOLDER.value, {"name": name, "location": location}
        )

    def _match_open_url(self, text: str) -> Intent | None:
        for pattern in (_URL_EXPLICIT, _URL_WWW, _URL_HOST):
            match = pattern.match(text)
            if match is not None:
                return Intent(IntentName.OPEN_URL.value, {"url": match.group(1)})
        return None

    def _match_open_file(self, text: str) -> Intent | None:
        explicit = re.match(
            r"^(?:open|view|show)\s+(?:the\s+)?file\s+(.+)$", text
        )
        if explicit is not None:
            remainder = explicit.group(1).strip()
        else:
            match = re.match(r"^(?:open|view|show)\s+(.+)$", text)
            if match is None:
                return None
            remainder = match.group(1).strip()

        location = settings.DEFAULT_SAFE_FOLDER
        located = re.match(r"^(.*?)\s+(?:in|under|inside)\s+(.+)$", remainder)
        if located:
            name_raw = located.group(1).strip()
            resolved = resolve_safe_root(located.group(2))
            if resolved is None:
                return None
            location = resolved
        else:
            name_raw = remainder

        if "." not in name_raw:
            return None
        extension = "." + name_raw.rsplit(".", 1)[1].lower()
        if extension not in self._safe_extensions:
            return None

        name = validate_folder_name(name_raw)
        if name is None:
            return None
        return Intent(
            IntentName.OPEN_FILE.value, {"name": name, "location": location}
        )

    def _match_open(self, text: str) -> Intent | None:
        match = re.match(r"^(?:open|launch|start)\s+(.+)$", text)
        if not match:
            return None
        target = validate_app_target(match.group(1))
        if target is None:
            return None
        key = target[:-4] if target.endswith(".exe") else target
        if key not in self._application_allowlist:
            return None
        return Intent(IntentName.OPEN_APPLICATION.value, {"target": target})

    def _match_volume(self, text: str) -> Intent | None:
        match = re.match(r"^(?:set\s+)?volume(?:\s+to)?\s+(\d{1,4})$", text)
        if not match:
            return None
        level = max(0, min(100, int(match.group(1))))
        return Intent("set_volume", {"level": level})

    def _match_search(self, text: str) -> Intent | None:
        match = re.match(r"^(?:search|google|look\s+up)\s+(?:for\s+)?(.+)$", text)
        if not match:
            return None
        query = validate_search_query(match.group(1))
        if query is None:
            return None
        return Intent(IntentName.SEARCH_WEB.value, {"query": query})
