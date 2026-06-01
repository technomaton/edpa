"""Tests for _console.force_utf8 and the guarded-import convention.

_console reconfigures stdout/stderr to UTF-8 so EDPA's progress glyphs
(``checkmark``, ``->``, ``.``) don't raise UnicodeEncodeError on a cp1250
Windows console. It must upgrade a legacy stream, never raise, and the entry
points must import it defensively (a partial vendor must degrade, not crash).
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "edpa" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import _console  # noqa: E402


def _norm(enc: str | None) -> str:
    return (enc or "").lower().replace("-", "")


def test_force_utf8_upgrades_cp1250_stream() -> None:
    out = io.TextIOWrapper(io.BytesIO(), encoding="cp1250")
    err = io.TextIOWrapper(io.BytesIO(), encoding="cp1250")
    saved = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        _console.force_utf8()
        assert _norm(out.encoding) == "utf8"
        assert _norm(err.encoding) == "utf8"
        out.write("✓ → ·")  # would crash on cp1250 without the upgrade
    finally:
        sys.stdout, sys.stderr = saved


def test_force_utf8_never_raises_on_non_reconfigurable_stream() -> None:
    # io.StringIO has no .reconfigure() — must be skipped silently.
    saved = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    try:
        _console.force_utf8()  # no exception
    finally:
        sys.stdout, sys.stderr = saved


def test_force_utf8_is_idempotent_on_utf8_stream() -> None:
    out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    saved = sys.stdout
    sys.stdout = out
    try:
        _console.force_utf8()
        _console.force_utf8()
        assert _norm(out.encoding) == "utf8"
    finally:
        sys.stdout = saved


def test_entry_points_guard_the_console_import() -> None:
    """A bare top-level ``import _console`` crashes a partially-vendored engine
    (the regression that broke the CI-materialization E2E). Every importer must
    keep it inside a ``try/except ImportError`` — detected here by the 4-space
    indent of the guarded form.
    """
    offenders = []
    for f in SCRIPTS.glob("*.py"):
        if f.name == "_console.py":  # the module itself, not an importer
            continue
        text = f.read_text(encoding="utf-8")
        if "import _console" not in text:
            continue
        if "    import _console" not in text:  # not indented → not guarded
            offenders.append(f.name)
    assert not offenders, f"unguarded top-level `import _console` in: {offenders}"
