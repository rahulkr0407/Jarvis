"""Local storage for user preferences and optional command history.

Everything here is **local** (a single SQLite file) and Qt-free. The store is
designed around one privacy rule: nothing sensitive is ever persisted.

* Command history is **off by default** and only records the text of a command
  plus the resulting action name — never raw audio, API keys, or file contents.
* Preferences are tiny key/value flags (for example whether history is enabled).
* The store never holds credentials. API keys live only in the environment.

The database is opened explicitly via :func:`open_storage`, which also creates
the parent directory on demand.
"""

from __future__ import annotations

from pathlib import Path

from config import settings
from storage.db import Database
from storage.history import HistoryStore
from storage.preferences import Preferences

__all__ = ["Database", "Preferences", "HistoryStore", "open_storage", "resolve_db_path"]


def resolve_db_path(path: str | Path | None = None) -> Path:
    """Return the database path as an absolute :class:`Path`.

    Relative paths (including the default) resolve against ``PROJECT_ROOT`` so
    the app behaves the same regardless of the current working directory.
    """
    candidate = Path(settings.DATABASE_PATH if path is None else path)
    return candidate if candidate.is_absolute() else settings.PROJECT_ROOT / candidate


def open_storage(
    path: str | Path | None = None,
    *,
    history_enabled_default: bool | None = None,
    ai_enabled_default: bool | None = None,
) -> tuple[Database, Preferences, HistoryStore]:
    """Open (creating on demand) the local store and return its parts."""
    database = Database(resolve_db_path(path))
    history_default = (
        settings.HISTORY_ENABLED_DEFAULT
        if history_enabled_default is None
        else history_enabled_default
    )
    ai_default = (
        settings.AI_ENABLED_DEFAULT
        if ai_enabled_default is None
        else ai_enabled_default
    )
    preferences = Preferences(
        database,
        history_enabled_default=history_default,
        ai_enabled_default=ai_default,
    )
    history = HistoryStore(
        database,
        max_entries=settings.HISTORY_MAX_ENTRIES,
        transcript_max_chars=settings.HISTORY_TRANSCRIPT_MAX_CHARS,
    )
    return database, preferences, history
