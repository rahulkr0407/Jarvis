"""A tiny SQLite wrapper with a simple schema-version migration step.

The database is meant to be created transparently on first run. Schema changes
are tracked with ``PRAGMA user_version`` so a future phase can migrate an
existing file without guesswork.

This module never stores anything sensitive by itself: it only creates empty
tables and offers generic row helpers. The privacy rules live in the callers
(:mod:`storage.preferences`, :mod:`storage.history`).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path

#: The current schema version. Bump this and add a migration branch when the
#: schema changes.
SCHEMA_VERSION = 1

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS preferences (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS history (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at  REAL    NOT NULL,
        transcript  TEXT    NOT NULL,
        action_name TEXT,
        outcome     TEXT,
        succeeded   INTEGER
    )
    """,
)


class Database:
    """A thin SQLite connection with schema initialisation.

    Pass ``":memory:"`` for an ephemeral database in tests.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    @property
    def path(self) -> str:
        """The database file path (or ``:memory:``)."""
        return self._path

    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying connection (for advanced callers/tests)."""
        return self._conn

    def _init_schema(self) -> None:
        for statement in _SCHEMA:
            self._conn.execute(statement)
        self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self._conn.commit()

    def schema_version(self) -> int:
        """Return the schema version recorded in the database."""
        row = self._conn.execute("PRAGMA user_version").fetchone()
        return int(row[0]) if row is not None else 0

    # ------------------------------------------------------------------ #
    # Generic helpers
    # ------------------------------------------------------------------ #
    def execute(self, sql: str, parameters: Sequence[object] = ()) -> sqlite3.Cursor:
        """Run a statement and commit."""
        cursor = self._conn.execute(sql, parameters)
        self._conn.commit()
        return cursor

    def query(self, sql: str, parameters: Sequence[object] = ()) -> list[sqlite3.Row]:
        """Run a read-only query and return all rows."""
        return list(self._conn.execute(sql, parameters))

    def executemany(self, sql: str, rows: Iterable[Sequence[object]]) -> None:
        """Run a statement for many parameter tuples and commit."""
        self._conn.executemany(sql, rows)
        self._conn.commit()

    def close(self) -> None:
        """Close the connection. Safe to call more than once."""
        try:
            self._conn.close()
        except Exception:
            pass
