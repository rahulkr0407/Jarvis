"""JARVIS entry point.

Run with either of:

    python -m app.main
    jarvis            # after `pip install -e .`

It creates the Qt application and the main window. No microphone, network, or
system access happens on startup: the assistant begins in IDLE and waits for an
explicit user gesture.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main() -> int:
    """Start the Qt event loop and return the process exit code."""
    app = QApplication(sys.argv)
    app.setApplicationName("JARVIS")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
