"""Tests for _fallback_lock.py and id_counter's filelock soft-import.

``filelock`` is a declared dependency, but a fresh Windows box can end up
without it (the one-time SessionStart dep install was skipped). id_counter
must then allocate IDs via the pure-stdlib fallback instead of crashing the
bootstrap with ``ModuleNotFoundError: No module named 'filelock'``.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "edpa" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _fallback_lock import FileLock, Timeout  # noqa: E402


# --- lock mechanics ---------------------------------------------------------

def test_acquire_release_roundtrip(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    with FileLock(str(lock)):
        assert lock.exists()  # held → file present
    assert not lock.exists()  # released → file removed


def test_second_holder_times_out(tmp_path: Path) -> None:
    lock = str(tmp_path / "x.lock")
    held = FileLock(lock, timeout=-1).acquire()
    try:
        with pytest.raises(Timeout):
            FileLock(lock, timeout=0.2).acquire()
    finally:
        held.release()


def test_threads_never_overlap(tmp_path: Path) -> None:
    """The critical section holds at most one thread at any instant."""
    lock = str(tmp_path / "x.lock")
    inside: list[int] = []
    max_seen = [0]
    guard = threading.Lock()

    def worker() -> None:
        for _ in range(5):
            with FileLock(lock, timeout=5):
                with guard:
                    inside.append(1)
                    max_seen[0] = max(max_seen[0], len(inside))
                time.sleep(0.001)
                with guard:
                    inside.pop()

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert max_seen[0] == 1, "two threads held the fallback lock at once"


def test_stale_lock_is_reclaimed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A lock file left by a dead holder must not wedge allocation forever."""
    import _fallback_lock

    lock_path = tmp_path / "x.lock"
    lock_path.write_text("orphan", encoding="utf-8")  # nobody holds it
    monkeypatch.setattr(_fallback_lock, "_STALE_AFTER_SEC", 0.0)
    with FileLock(str(lock_path), timeout=1):
        assert lock_path.exists()  # reclaimed and re-acquired, no Timeout


# --- id_counter soft-import (subprocess isolation) --------------------------

_PROG = """
import sys
sys.modules['filelock'] = None  # simulate `import filelock` -> ImportError
sys.path.insert(0, "__SCRIPTS__")
import id_counter as ic
assert ic.FileLock.__module__ == '_fallback_lock', ic.FileLock.__module__
import tempfile, pathlib
d = pathlib.Path(tempfile.mkdtemp())
(d / '.edpa' / 'config').mkdir(parents=True)
(d / '.edpa' / 'backlog').mkdir(parents=True)
print(ic.next_id('Story', d))
print(ic.next_id('Story', d))
""".replace("__SCRIPTS__", str(SCRIPTS))


def test_id_counter_falls_back_when_filelock_missing() -> None:
    r = subprocess.run([sys.executable, "-c", _PROG], capture_output=True, text=True)
    assert r.returncode == 0, f"bootstrap crashed without filelock:\n{r.stderr}"
    assert r.stdout.split() == ["S-1", "S-2"], r.stdout
