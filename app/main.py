"""JARVIS entry point.

Run with either of:

    python -m app.main
    python -m app.main --dry-run
    jarvis            # after `pip install -e .`

It creates the Qt application and the main window. No microphone, network, or
system access happens on startup: the assistant begins in IDLE and waits for an
explicit user gesture.

``--dry-run`` makes every action report what it *would* do and touch nothing —
useful for developing and demonstrating the approval flow safely.
"""

from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from actions.base import build_action_context
from ui.main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    """Start the Qt event loop and return the process exit code."""
    parser = argparse.ArgumentParser(prog="jarvis", description="JARVIS assistant")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what actions would do without launching or changing anything.",
    )
    args = parser.parse_args(argv)

    app = QApplication(sys.argv)
    app.setApplicationName("JARVIS")

    context = build_action_context(dry_run=True if args.dry_run else None)
    window = MainWindow(action_context=context)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
