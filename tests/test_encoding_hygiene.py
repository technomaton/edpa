"""Static guard: every text-mode file handle in the engine pins encoding='utf-8'.

Without an explicit encoding, ``open`` / ``Path.read_text`` / ``Path.write_text``
/ ``os.fdopen`` use the locale encoding — cp1250/cp1252 on a Czech/German
Windows box. Reading a UTF-8 config (``edpa.yaml`` ships ``<-`` and ``x``) then
raises ``UnicodeDecodeError``; writing an item whose title has diacritics
raises ``UnicodeEncodeError``. Both abort the command. Pinning UTF-8 makes the
engine behave identically on Linux, macOS, and Windows.

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
