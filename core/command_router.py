"""Turn free text into a *proposed* action — and nothing more.

Speech is untrusted input. This module is the boundary where text is allowed to
influence the assistant, and it is intentionally strict:

* Only a small set of phrase shapes is recognized.
* The resulting action name must be in the allowlist, or the whole thing is
  discarded.
* Arguments are validated and clamped (an integer volume is bounded, a search
  query is length-capped, an application target must look like a name).

Routing never executes anything. It returns an :class:`Intent`, which the
controller still requires the user to approve before anything runs.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from config import settings

# A conservative pattern for an application name. No paths, no separators.
_APP_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,63}$")
_MAX_QUERY_LENGTH = 200


@dataclass(frozen=True)
class Intent:
    """A proposed action parsed from text. Not yet approved or executed."""

    action_name: str
    arguments: Mapping[str, object]


class CommandRouter:
    """Maps recognized text to an allowlisted :class:`Intent` (or ``None``)."""

    def __init__(self, allowed_actions: Iterable[str] | None = None) -> None:
        self._allowed = frozenset(
            settings.ALLOWED_ACTIONS if allowed_actions is None else allowed_actions
        )

    def route(self, text: str) -> Intent | None:
        """Return an Intent for ``text`` if it matches an allowed action.

        Returns ``None`` when the text is empty, unrecognized, or would map to an
        action that is not allowlisted.
        """
        if not text:
            return None
        normalized = " ".join(text.strip().lower().split())
        if not normalized:
            return None

        for matcher in (self._match_open, self._match_volume, self._match_search):
            intent = matcher(normalized)
            if intent is not None and intent.action_name in self._allowed:
                return intent
        return None

    # ------------------------------------------------------------------ #
    # Individual rules
    # ------------------------------------------------------------------ #
    def _match_open(self, text: str) -> Intent | None:
        match = re.match(r"^(?:open|launch|start)\s+(.+)$", text)
        if not match:
            return None
        target = match.group(1).strip()
        if not _APP_TARGET.match(target):
            return None
        return Intent("open_application", {"target": target})

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
        query = match.group(1).strip()
        if not query:
            return None
        return Intent("search_web", {"query": query[:_MAX_QUERY_LENGTH]})
