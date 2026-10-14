"""A dependency-free ``.env`` loader.

Real environments win: a variable already present in ``os.environ`` is never
overridden by a file. This keeps CI/production behaviour predictable and means a
stray ``.env`` can never shadow a properly exported secret.

The parser is intentionally minimal and forgiving — it understands
``KEY=VALUE`` lines, optional surrounding quotes, ``export`` prefixes, and
``#`` comments. Anything it does not understand is ignored rather than raising,
because a malformed ``.env`` must never stop the assistant from starting.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path

from config import settings


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse the contents of a ``.env`` file into a plain dict."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def load_dotenv(
    path: str | Path | None = None,
    *,
    environ: MutableMapping[str, str] | None = None,
    override: bool = False,
) -> dict[str, str]:
    """Load a ``.env`` file into ``environ`` (defaults to ``os.environ``).

    Returns the values that were actually applied. Existing variables are kept
    unless ``override`` is true.
    """
    target = os.environ if environ is None else environ
    candidate = Path(settings.PROJECT_ROOT / ".env" if path is None else path)
    if not candidate.exists():
        return {}

    try:
        text = candidate.read_text(encoding="utf-8")
    except Exception:
        # A missing/unreadable .env must never break startup.
        return {}

    applied: dict[str, str] = {}
    for key, value in parse_dotenv(text).items():
        if override or key not in target:
            target[key] = value
            applied[key] = value
    return applied
