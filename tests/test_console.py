"""Tests for _console.force_utf8 and the guarded-import convention.

_console reconfigures stdout/stderr to UTF-8 so EDPA's progress glyphs
(``checkmark``, ``->``, ``.``) don't raise UnicodeEncodeError on a cp1250
Windows console. It must upgrade a legacy stream, never raise, and the entry
points must import it defensively (a partial vendor must degrade, not crash).
"""
from __future__ import annotations

import ast
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


# mcp_server's glyphs live only in JSON-RPC tool descriptions, framed UTF-8 on
# the wire by the SDK; it deliberately does NOT reconfigure stdout (see the
# _console.py docstring). Everything else that decorates console output opts in.
_CONSOLE_EXEMPT = {"mcp_server.py", "_console.py"}


def _is_entry_point(tree: ast.AST) -> bool:
    """True if the module has an ``if __name__ == "__main__":`` guard."""
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            dumped = ast.dump(node.test)
            if "__name__" in dumped and "__main__" in dumped:
                return True
    return False


def _prints_nonascii_literal(tree: ast.AST) -> bool:
    """True if any ``print(...)`` carries a non-ASCII string literal — a
    decorative glyph (✓ → — ∅ …) that UnicodeEncodeError-crashes a cp1250
    console. Walks into f-strings so ``print(f"✓ {x}")`` counts."""
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"):
            continue
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Constant) and isinstance(sub.value, str)
                    and any(ord(ch) > 127 for ch in sub.value)):
                return True
    return False


def test_glyph_printing_entry_points_import_console() -> None:
    """Pinning file I/O to UTF-8 (test_encoding_hygiene) is not enough: a CLI
    that ``print()``s a glyph still crashes on a cp1250/cp1252 Windows console
    unless it imports ``_console`` to reconfigure *stdout*. This is the
    pi_planning.py ``--open`` regression — it wrote the whole 787 kB report,
    then exited 1 on ``print("✓ …")`` (D-21). Catch the class, not the instance.
    """
    offenders = []
    for f in sorted(SCRIPTS.glob("*.py")):
        if f.name in _CONSOLE_EXEMPT:
            continue
        src = f.read_text(encoding="utf-8")
        tree = ast.parse(src)
        if _is_entry_point(tree) and _prints_nonascii_literal(tree):
            if "import _console" not in src:
                offenders.append(f.name)
    assert not offenders, (
        "entry-point script print()s a non-ASCII glyph but never imports "
        "_console — UnicodeEncodeError-crashes on a cp1250/cp1252 Windows "
        "console after doing its real work:\n  " + "\n  ".join(offenders)
        + "\nFix: add a guarded `try: import _console` at the top of main()."
    )
