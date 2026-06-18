"""Static guard: every text-mode file handle in the engine pins encoding='utf-8'.

Without an explicit encoding, ``open`` / ``Path.read_text`` / ``Path.write_text``
/ ``os.fdopen`` use the locale encoding — cp1250/cp1252 on a Czech/German
Windows box. Reading a UTF-8 config (``edpa.yaml`` ships ``<-`` and ``x``) then
raises ``UnicodeDecodeError``; writing an item whose title has diacritics
raises ``UnicodeEncodeError``. Both abort the command. Pinning UTF-8 makes the
engine behave identically on Linux, macOS, and Windows.

The same locale trap applies to ``subprocess`` in **text mode**:
``run(..., text=True)`` decodes git/gh stdout with cp1252 and raises
``UnicodeDecodeError`` in the reader thread the instant a commit message or
author name carries diacritics (D-23 — crashed ``/edpa:engine`` on a Czech
Windows box). ``test_all_subprocess_text_pins_utf8`` guards that. Calls that
capture *bytes* (``capture_output=True`` with no ``text=``/``universal_newlines=``)
never decode, so they can't hit the trap and are intentionally left alone.

This is an AST walk (not a grep) so it sees through multi-line calls and never
false-positives on a continuation line that already carries ``encoding=``.
``os.open`` is excluded — it returns a raw file descriptor and takes no
encoding; ``*b`` binary modes are excluded too.
"""
from __future__ import annotations

import ast
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "plugin" / "edpa" / "scripts"
TEXT_IO = {"open", "fdopen", "read_text", "write_text"}


def _func_name(call: ast.Call) -> str | None:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _is_os_open(call: ast.Call) -> bool:
    """`os.open(...)` is a raw fd syscall — no encoding kwarg exists."""
    f = call.func
    return (
        isinstance(f, ast.Attribute)
        and f.attr == "open"
        and isinstance(f.value, ast.Name)
        and f.value.id == "os"
    )


def _is_binary(call: ast.Call) -> bool:
    mode = None
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        mode = call.args[1].value
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            mode = kw.value.value
    return isinstance(mode, str) and "b" in mode


def _violations(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _func_name(node)
        if name not in TEXT_IO:
            continue
        if any(kw.arg == "encoding" for kw in node.keywords):
            continue
        if name == "open" and _is_os_open(node):
            continue
        if name in ("open", "fdopen") and _is_binary(node):
            continue
        bad.append((name, node.lineno))
    return bad


def test_all_text_io_pins_utf8() -> None:
    failures = {
        path.name: v
        for path in sorted(SCRIPTS.glob("*.py"))
        if (v := _violations(path))
    }
    assert not failures, (
        "text-mode file I/O without encoding='utf-8' (crashes on Windows "
        "cp1250 with non-ASCII content):\n"
        + "\n".join(f"  {name}: {sites}" for name, sites in failures.items())
    )


# ─── subprocess text mode ──────────────────────────────────────────────────
SUBPROCESS_FUNCS = {"run", "Popen", "check_output", "check_call", "call"}


def _is_subprocess_call(call: ast.Call) -> bool:
    f = call.func
    return (
        isinstance(f, ast.Attribute)
        and f.attr in SUBPROCESS_FUNCS
        and isinstance(f.value, ast.Name)
        and f.value.id == "subprocess"
    )


def _kw_is_true(call: ast.Call, name: str) -> bool:
    for kw in call.keywords:
        if kw.arg == name:
            return isinstance(kw.value, ast.Constant) and kw.value.value is True
    return False


def _subprocess_text_violations(path: Path) -> list[tuple[str, int]]:
    """Calls that DECODE stdout/stderr as text (``text=True`` or
    ``universal_newlines=True``) but never pin ``encoding=``. A bare
    ``capture_output=True`` returns *bytes* — no decode, no trap — so it is
    NOT flagged; only the calls that actually decode are at risk."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_subprocess_call(node):
            continue
        decodes = _kw_is_true(node, "text") or _kw_is_true(node, "universal_newlines")
        if not decodes:
            continue
        if any(kw.arg == "encoding" for kw in node.keywords):
            continue
        bad.append((node.func.attr, node.lineno))
    return bad


def test_all_subprocess_text_pins_utf8() -> None:
    failures = {
        path.name: v
        for path in sorted(SCRIPTS.glob("*.py"))
        if (v := _subprocess_text_violations(path))
    }
    assert not failures, (
        "subprocess in text mode without encoding='utf-8' — decodes git/gh "
        "stdout with the locale codec, so a diacritic in a commit message or "
        "author name raises UnicodeDecodeError in the reader thread on a "
        "cp1252 Windows box (D-23):\n"
        + "\n".join(f"  {name}: {sites}" for name, sites in failures.items())
        + "\nFix: add encoding=\"utf-8\" to each call (or capture bytes if the "
        "output is genuinely binary)."
    )
