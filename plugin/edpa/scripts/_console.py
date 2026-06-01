"""Force UTF-8 on stdout/stderr for EDPA's CLI entry points.

EDPA ships ~25 small scripts run directly as ``python3
.edpa/engine/scripts/<tool>.py``. They print decorative glyphs (checkmarks,
arrows, bullets: ``checkmark``, ``->``, ``.``) for human-readable progress.
On legacy Windows consoles (cp1250/cp1252) ``print("checkmark")`` raises
``UnicodeEncodeError`` and aborts the whole command mid-run — the exact
failure that broke first-run ``project_setup.py`` on Windows.

Importing this module reconfigures ``sys.stdout``/``sys.stderr`` to UTF-8 as
an import side effect, so each entry point opts in with a small guarded
``import _console`` block instead of duplicating the reconfigure logic in
every ``main()``. Entry points guard the import with ``try/except
ImportError`` so a partially-vendored engine degrades to plain output rather
than crashing. It is:

  * idempotent  — no-op when the stream is already UTF-8;
  * harmless    — wrapped in try/except; silently skips streams that can't
                  be reconfigured (pytest capture, already-detached pipes);
  * total       — ``errors="replace"`` guarantees a glyph never crashes a
                  command even on a terminal that genuinely can't render it.

Not imported by ``mcp_server.py`` on purpose: its glyphs live in JSON-RPC
tool descriptions, which the MCP SDK already frames as UTF-8 on the wire.
"""
from __future__ import annotations

import sys


def force_utf8() -> None:
    """Reconfigure stdout/stderr to UTF-8 (best effort, never raises)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            # Stream isn't a TextIOWrapper (e.g. pytest capture) — skip.
            continue
        try:
            if (getattr(stream, "encoding", "") or "").lower() not in ("utf-8", "utf8"):
                reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # Already detached, or the stream rejects re-encoding. Best
            # effort only — a missing glyph fix must never become a crash.
            pass


force_utf8()
