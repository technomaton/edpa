"""Pure-stdlib cross-platform file lock — fallback for the `filelock` package.

`id_counter.py` prefers third-party `filelock` (battle-tested, richer). When
it isn't importable — e.g. a fresh Windows box where the one-time dependency
install was skipped — this minimal lock keeps EDPA's ID-allocation
concurrency guarantee intact instead of crashing the bootstrap with
``ModuleNotFoundError: No module named 'filelock'``.

It mirrors the slice of filelock's API that id_counter uses:

  * ``FileLock(lock_file, timeout=...)`` as a context manager;
  * ``Timeout`` raised when the lock can't be acquired in time.

Mechanism: atomic ``O_CREAT | O_EXCL`` creation of the lock file. Whoever
creates it owns it until ``release()`` unlinks it. ``O_EXCL`` is enforced by
the OS across both threads and processes, on POSIX and Windows alike, so the
mutual-exclusion contract holds.

Limitation vs. filelock: a holder that dies mid-critical-section leaves the
file behind (no OS auto-release). id_counter holds the lock for microseconds
with a 5 s timeout, so we reclaim any lock older than ``_STALE_AFTER_SEC``
(far above any legitimate hold) — a crash can't wedge ID allocation forever.
Install ``filelock`` (it's in requirements.txt) for the robust lock.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

_STALE_AFTER_SEC = 30.0
_POLL_SEC = 0.02


class Timeout(TimeoutError):
    """Raised when the lock cannot be acquired within the timeout window."""


class FileLock:
    """Minimal ``filelock.FileLock``-compatible advisory lock."""

    def __init__(self, lock_file: str, timeout: float = -1) -> None:
        self._path = Path(lock_file)
        self._timeout = timeout
        self._fd: int | None = None

    def acquire(self) -> "FileLock":
        deadline = None if self._timeout < 0 else time.monotonic() + self._timeout
        while True:
            try:
                self._fd = os.open(str(self._path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                return self
            except FileExistsError:
                self._reap_if_stale()
                if deadline is not None and time.monotonic() >= deadline:
                    raise Timeout(
                        f"Could not acquire lock {self._path} within {self._timeout}s"
                    )
                time.sleep(_POLL_SEC)

    def _reap_if_stale(self) -> None:
        try:
            age = time.time() - self._path.stat().st_mtime
        except OSError:
            return
        if age > _STALE_AFTER_SEC:
            try:
                os.unlink(self._path)
            except OSError:
                pass

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            os.close(self._fd)
        finally:
            self._fd = None
        try:
            os.unlink(self._path)
        except OSError:
            pass

    def __enter__(self) -> "FileLock":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()
