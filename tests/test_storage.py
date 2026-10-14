"""Tests for local storage: preferences and optional command history."""

from __future__ import annotations

from storage import open_storage, resolve_db_path
from storage.db import SCHEMA_VERSION, Database
from storage.history import HistoryStore
from storage.preferences import (
    AI_ENABLED,
    HISTORY_ENABLED,
    Preferences,
)


def make_store(path: str = ":memory:") -> Database:
    return Database(path)


# --------------------------------------------------------------------------- #
# Schema + preferences
# --------------------------------------------------------------------------- #
def test_schema_version_recorded():
    db = make_store()
    assert db.schema_version() == SCHEMA_VERSION


def test_history_default_is_off():
    prefs = Preferences(make_store(), history_enabled_default=False)
    assert prefs.history_enabled is False


def test_history_default_can_be_on():
    prefs = Preferences(make_store(), history_enabled_default=True)
    assert prefs.history_enabled is True


def test_ai_default_is_off_unless_configured():
    prefs = Preferences(make_store())
    assert prefs.ai_enabled is False
    prefs = Preferences(make_store(), ai_enabled_default=True)
    assert prefs.ai_enabled is True


def test_preference_round_trip():
    prefs = Preferences(make_store())
    prefs.history_enabled = True
    prefs.ai_enabled = True
    assert prefs.history_enabled is True
    assert prefs.ai_enabled is True
    assert prefs.get(HISTORY_ENABLED) == "true"
    assert prefs.get(AI_ENABLED) == "true"


def test_clear_preferences_resets_to_default():
    prefs = Preferences(make_store(), history_enabled_default=False)
    prefs.history_enabled = True
    prefs.clear()
    assert prefs.history_enabled is False
    assert prefs.ai_enabled is False


# --------------------------------------------------------------------------- #
# History
# --------------------------------------------------------------------------- #
def test_history_recorded_only_when_enabled():
    history = HistoryStore(make_store())
    assert history.add("open notepad", enabled=False) is False
    assert history.count() == 0
    assert history.add("open notepad", enabled=True) is True
    assert history.count() == 1


def test_empty_transcript_is_not_stored():
    history = HistoryStore(make_store())
    assert history.add("   ", enabled=True) is False
    assert history.count() == 0


def test_recent_returns_newest_first():
    history = HistoryStore(make_store())
    history.add("first", enabled=True)
    history.add("second", enabled=True)
    entries = history.recent()
    assert [e.transcript for e in entries] == ["second", "first"]


def test_transcript_is_truncated():
    history = HistoryStore(make_store(), transcript_max_chars=10)
    history.add("x" * 1000, enabled=True)
    assert len(history.recent()[0].transcript) == 10


def test_control_characters_are_stripped():
    history = HistoryStore(make_store(), transcript_max_chars=100)
    history.add("a\x00b\tc\n d", enabled=True)
    stored = history.recent()[0].transcript
    assert "\x00" not in stored
    assert "\n" not in stored
    assert "\t" in stored


def test_update_latest_outcome():
    history = HistoryStore(make_store())
    history.add("open notepad", action_name="open_application", enabled=True)
    assert history.update_latest_outcome(outcome="Launched.", succeeded=True) is True
    entry = history.recent()[0]
    assert entry.outcome == "Launched."
    assert entry.succeeded is True
    assert entry.action_name == "open_application"


def test_update_latest_outcome_with_no_rows_is_false():
    history = HistoryStore(make_store())
    assert history.update_latest_outcome(outcome="x", succeeded=True) is False


def test_history_is_trimmed_to_max_entries():
    history = HistoryStore(make_store(), max_entries=3)
    for i in range(6):
        history.add(f"cmd {i}", enabled=True)
    assert history.count() == 3
    assert history.recent()[0].transcript == "cmd 5"


def test_clear_history():
    history = HistoryStore(make_store())
    history.add("a", enabled=True)
    history.clear()
    assert history.count() == 0


def test_max_entries_zero_stores_nothing():
    history = HistoryStore(make_store(), max_entries=0)
    history.add("a", enabled=True)
    assert history.count() == 0


# --------------------------------------------------------------------------- #
# open_storage / paths
# --------------------------------------------------------------------------- #
def test_open_storage_creates_file(tmp_path):
    db, prefs, history = open_storage(tmp_path / "sub" / "jarvis.db")
    assert (tmp_path / "sub" / "jarvis.db").exists()
    assert prefs.history_enabled is False
    history.add("hello", enabled=True)
    assert history.count() == 1
    db.close()


def test_resolve_db_path_default_is_absolute():
    path = resolve_db_path()
    assert path.is_absolute()


def test_resolve_db_path_relative_uses_project_root():
    from config import settings

    path = resolve_db_path("data/x.db")
    assert path == settings.PROJECT_ROOT / "data" / "x.db"
