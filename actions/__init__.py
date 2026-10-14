"""Phase 4: permission-controlled Windows actions.

Each supported action lives in its own module with a single ``run``-style
handler. Actions are **never** executed directly by the router or the UI: they
run only through :func:`actions.registry.build_executor`, which is called by the
controller *after* an exact-match approval.

Everything here is Qt-free and side-effect-free at import time. Real side effects
(launching a process, creating a folder, opening a file) happen only when an
action's handler runs, and never when ``dry_run`` is set.
"""
