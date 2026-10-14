"""User preferences, stored as small key/value flags.

Only non-sensitive settings live here: whether command history is enabled and
whether the optional AI features are enabled. Values are stored as text and
converted on read.

The most important preference is :attr:`history_enabled`, which defaults to the
value configured in :mod:`config.settings` (off by default).
"""

from __future__ import annotations

from storage.db import Database

#: Preference keys. Kept as constants so callers do not drift on spelling.
HISTORY_ENABLED = "history_enabled"
AI_ENABLED = "ai_enabled"

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _to_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


class Preferences:
    """Read/write access to the ``preferences`` table."""

    def __init__(
        self,
        database: Database,
        *,
        history_enabled_default: bool = False,
        ai_enabled_default: bool = False,
    ) -> None:
        self._db = database
        self._history_default = bool(history_enabled_default)
        self._ai_default = bool(ai_enabled_default)

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the stored string for ``key`` or ``default``."""
        rows = self._db.query(
            "SELECT value FROM preferences WHERE key = ?", (key,)
        )
        return rows[0]["value"] if rows else default

    def set(self, key: str, value: object) -> None:
        """Store ``value`` (converted to text) under ``key``."""
        self._db.execute(
            "INSERT INTO preferences (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Return a boolean preference, falling back to ``default``."""
        parsed = _to_bool(self.get(key))
        return default if parsed is None else parsed

    def set_bool(self, key: str, value: bool) -> None:
        """Store a boolean preference."""
        self.set(key, "true" if value else "false")

    # ------------------------------------------------------------------ #
    # Named preferences
    # ------------------------------------------------------------------ #
    @property
    def history_enabled(self) -> bool:
        """Whether command history is being recorded."""
        return self.get_bool(HISTORY_ENABLED, self._history_default)

    @history_enabled.setter
    def history_enabled(self, value: bool) -> None:
        self.set_bool(HISTORY_ENABLED, value)

    @property
    def ai_enabled(self) -> bool:
        """Whether the optional AI features are switched on by the user."""
        return self.get_bool(AI_ENABLED, self._ai_default)

    @ai_enabled.setter
    def ai_enabled(self, value: bool) -> None:
        self.set_bool(AI_ENABLED, value)

    def clear(self) -> None:
        """Remove every stored preference (used by 'clear stored data')."""
        self._db.execute("DELETE FROM preferences")
