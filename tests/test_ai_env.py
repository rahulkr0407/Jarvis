"""Tests for the dependency-free .env loader."""

from __future__ import annotations

from ai.env import load_dotenv, parse_dotenv


def test_parse_basic_pairs():
    text = "JARVIS_LLM_API_KEY=secret\nJARVIS_LLM_MODEL=gpt-4o-mini\n"
    assert parse_dotenv(text) == {
        "JARVIS_LLM_API_KEY": "secret",
        "JARVIS_LLM_MODEL": "gpt-4o-mini",
    }


def test_parse_ignores_comments_blanks_and_malformed_lines():
    text = (
        "# a comment\n"
        "\n"
        "   \n"
        "not a pair\n"
        "KEY=value\n"
    )
    assert parse_dotenv(text) == {"KEY": "value"}


def test_parse_strips_quotes_and_export_prefix():
    text = 'export A="one two"\nB=\'three\'\n'
    assert parse_dotenv(text) == {"A": "one two", "B": "three"}


def test_parse_allows_empty_values():
    assert parse_dotenv("EMPTY=") == {"EMPTY": ""}


def test_load_dotenv_sets_missing_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\nB=2\n", encoding="utf-8")
    environ: dict[str, str] = {"A": "existing"}
    applied = load_dotenv(env_file, environ=environ)
    assert environ == {"A": "existing", "B": "2"}
    assert applied == {"B": "2"}


def test_load_dotenv_real_env_wins_and_override_can_win(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("A=new\n", encoding="utf-8")

    environ = {"A": "old"}
    load_dotenv(env_file, environ=environ)
    assert environ["A"] == "old"

    load_dotenv(env_file, environ=environ, override=True)
    assert environ["A"] == "new"


def test_load_dotenv_missing_file_is_silent(tmp_path):
    assert load_dotenv(tmp_path / "nope.env", environ={}) == {}


def test_load_dotenv_unreadable_is_silent(tmp_path):
    directory = tmp_path / "adir.env"
    directory.mkdir()
    # Reading a directory raises; the loader must swallow it.
    assert load_dotenv(directory, environ={}) == {}
