"""JARVIS entry point.

Run with either of:

    python -m app.main
    python -m app.main --dry-run
    python -m app.main --no-ai --no-history
    jarvis            # after `pip install -e .`

It creates the Qt application and the main window. No microphone, network, or
system access happens on startup: the assistant begins in IDLE and waits for an
explicit user gesture.

Flags:

* ``--dry-run``   — actions report what they *would* do and touch nothing.
* ``--no-ai``     — disable the optional AI features for this run, even if a key
                    is configured.
* ``--no-history``— start with local command history disabled for this run.

AI configuration is read from environment variables (see ``.env.example``).
A ``.env`` file in the project root is loaded on startup but never overrides a
real environment variable.
"""

from __future__ import annotations

import argparse
import logging
import sys

from ai.config import load_ai_config
from ai.env import load_dotenv
from PySide6.QtWidgets import QApplication

from actions.base import build_action_context
from logging_setup import setup_logging
from storage import open_storage
from ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Start the Qt event loop and return the process exit code."""
    parser = argparse.ArgumentParser(prog="jarvis", description="JARVIS assistant")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what actions would do without launching or changing anything.",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Disable the optional AI features for this run.",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Start with local command history disabled for this run.",
    )
    args = parser.parse_args(argv)

    # Load .env before reading configuration. Real env vars win.
    load_dotenv()

    # Configure logging after .env is loaded so the API key can be redacted.
    # Nothing is logged before this point, and the key is never logged at all.
    setup_logging()
    logger.info("JARVIS starting (dry_run=%s, ai=%s, history=%s)", args.dry_run,
                not args.no_ai, not args.no_history)

    app = QApplication(sys.argv)
    app.setApplicationName("JARVIS")

    context = build_action_context(dry_run=True if args.dry_run else None)

    # Optional AI. Constructing these performs no network I/O; it only reads
    # configuration. With no key the orchestrator reports "unavailable".
    from ai.client import AIClient
    from ai.orchestrator import AIOrchestrator

    ai_config = load_ai_config()
    if args.no_ai:
        ai_config = _with_enabled(ai_config, False)
    ai = AIOrchestrator(AIClient(ai_config))
    logger.info("AI is %s", "configured" if ai.is_available() else "unavailable")

    # Local storage (preferences + optional history). Failures here must never
    # stop the app from starting.
    preferences = history = None
    try:
        _database, preferences, history = open_storage()
        if args.no_history:
            preferences.history_enabled = False
    except Exception:
        logger.warning("Local storage unavailable; continuing without it",
                       exc_info=True)
        preferences = history = None

    window = MainWindow(
        action_context=context,
        ai=ai,
        preferences=preferences,
        history=history,
    )
    window.show()
    logger.info("JARVIS ready in IDLE")
    return app.exec()


def _with_enabled(config, enabled: bool):
    """Return a copy of ``config`` with the enabled flag overridden."""
    from dataclasses import replace

    return replace(config, enabled=enabled)


if __name__ == "__main__":
    raise SystemExit(main())
