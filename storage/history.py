"""Optional, local command history.

History is a convenience feature, not a log: it records only the *text* of a
command and the resulting action name/outcome. It is deliberately conservative:

* It stores nothing unless explicitly enabled (see
  :class:`storage.preferences.Preferences.history_enabled`).
* Transcripts are stripped of control characters and truncated, so a long or
  pasted blob cannot bloat the file or smuggle terminal escapes.
* It never stores audio, API keys, file contents, or model responses.
* The whole table can be cleared by the user at any time.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from storage.db import Database


@dataclass(frozen=True)
class HistoryEntry:
    """One recorded command."""

    id: int
    created_at: float
    transcript: str
    action_name: str | None
    outcome: str | None
    succeeded: bool | None


def _sanitize(text: str, max_chars: int) -> str:
    """Strip control characters and bound the length of a transcript."""
    cleaned = "".join(
        ch for ch in (text or "") if ch == "\t" or ch >= " "
    ).strip()
    return cleaned[:max_chars]


class HistoryStore:
    """Read/write access to the ``history`` table."""

    def __init__(
        self,
        database: Database,
        *,
        max_entries: int = 500,
        transcript_max_chars: int = 500,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._db = database
        self._max_entries = max(0, int(max_entries))
        self._transcript_max_chars = max(0, int(transcript_max_chars))
        self._clock = clock

    def add(
        self,
        transcript: str,
        *,
        action_name: str | None = None,
        outcome: str | None = None,
        succeeded: bool | None = None,
        enabled: bool = True,
    ) -> bool:
        """Record one command. Returns ``True`` if a row was written.

        Nothing is written when ``enabled`` is falsy, so callers can pass the
        current preference directly.
        """
        if not enabled:
            return False
        text = _sanitize(transcript, self._transcript_max_chars)
        if not text:
            return False
        succeeded_value = None if succeeded is None else int(bool(succeeded))
        self._db.execute(
            "INSERT INTO history (created_at, transcript, action_name, outcome, "
            "succeeded) VALUES (?, ?, ?, ?, ?)",
            (self._clock(), text, action_name, outcome, succeeded_value),
        )
        self._trim()
        return True

    def update_latest_outcome(
        self, *, outcome: str | None, succeeded: bool | None
    ) -> bool:
        """Attach an outcome to the most recent entry.

        Used after an approved action finishes so one command produces one row.
        Returns ``True`` if a row was updated.
        """
        rows = self._db.query("SELECT id FROM history ORDER BY id DESC LIMIT 1")
        if not rows:
            return False
        succeeded_value = None if succeeded is None else int(bool(succeeded))
        self._db.execute(
            "UPDATE history SET outcome = ?, succeeded = ? WHERE id = ?",
            (outcome, succeeded_value, int(rows[0]["id"])),
        )
        return True

    def recent(self, limit: int = 20) -> list[HistoryEntry]:
        """Return the most recent entries, newest first."""
        rows = self._db.query(
            "SELECT id, created_at, transcript, action_name, outcome, succeeded "
            "FROM history ORDER BY id DESC LIMIT ?",
            (max(0, int(limit)),),
        )
        return [self._row_to_entry(row) for row in rows]

    def count(self) -> int:
        """Return the number of stored entries."""
        rows = self._db.query("SELECT COUNT(*) AS n FROM history")
        return int(rows[0]["n"]) if rows else 0

    def clear(self) -> None:
        """Delete every stored entry."""
        self._db.execute("DELETE FROM history")

    def _trim(self) -> None:
        """Keep at most ``max_entries`` rows (drop the oldest)."""
        if self._max_entries <= 0:
            self.clear()
            return
        self._db.execute(
            "DELETE FROM history WHERE id NOT IN "
            "(SELECT id FROM history ORDER BY id DESC LIMIT ?)",
            (self._max_entries,),
        )

    @staticmethod
    def _row_to_entry(row) -> HistoryEntry:
        succeeded = row["succeeded"]
        return HistoryEntry(
            id=int(row["id"]),
            created_at=float(row["created_at"]),
            transcript=str(row["transcript"]),
            action_name=row["action_name"],
            outcome=row["outcome"],
            succeeded=None if succeeded is None else bool(succeeded),
        )
