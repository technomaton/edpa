"""Atomic local ID counter for EDPA item types.

V2 replacement for GH-issue-derived IDs. Resolves the next ID via
``max(counter_file, fs_scan) + 1``, writes the counter atomically
(tmp + rename), and protects concurrent processes with a file lock.

Counter file layout (``.edpa/config/id_counters.yaml``)::

    counters:
      Defect: 9
      Epic: 12
      Event: 3
      Feature: 34
      Initiative: 5
      Risk: 2
      Story: 78

See ``docs/v2/plan.md`` § "ID safety — local defense in depth" for the
full layered design. This module implements Layers 1 (fs_scan) and 2
(file lock); validation hooks and idempotency live elsewhere.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import yaml
try:
    from filelock import FileLock, Timeout
except ImportError:
    # filelock not installed (e.g. a fresh Windows box where the one-time
    # dependency install was skipped). Fall back to a pure-stdlib lock so ID
    # allocation still works instead of crashing the bootstrap with
    # ModuleNotFoundError. The fallback preserves the cross-process
    # mutual-exclusion contract; see _fallback_lock for its limitations.
    from _fallback_lock import FileLock, Timeout

# Mirrored from backlog.py to avoid circular import. Keep in sync until
# backlog.py is refactored to import these from here (Krok 2).
TYPE_DIRS = {
    "Initiative": "initiatives",
    "Epic":       "epics",
    "Feature":    "features",
    "Story":      "stories",
    "Defect":     "defects",
    "Event":      "events",
    "Risk":       "risks",
}

TYPE_PREFIX = {
    "Initiative": "I",
    "Epic":       "E",
    "Feature":    "F",
    "Story":      "S",
    "Defect":     "D",
    "Event":      "EV",
    "Risk":       "R",
}

_COUNTER_REL = Path(".edpa/config/id_counters.yaml")
_LOCK_REL = Path(".edpa/.id_counter.lock")
_LOCK_TIMEOUT_SEC = 5


class IdCounterError(Exception):
    """Raised when the ID counter is in an unrecoverable state."""


def _read_counter(counter_path: Path, item_type: str) -> int:
    if not counter_path.exists():
        return 0
    try:
        data = yaml.safe_load(counter_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise IdCounterError(f"Cannot parse {counter_path}: {e}") from e
    return int((data.get("counters") or {}).get(item_type, 0))


def _scan_fs_max(backlog_dir: Path, item_type: str) -> int:
    if not backlog_dir.exists():
        return 0
    pattern = re.compile(rf"^{re.escape(TYPE_PREFIX[item_type])}-(\d+)$")
    max_num = 0
    for f in backlog_dir.glob("*.md"):
        m = pattern.match(f.stem)
        if m:
            num = int(m.group(1))
            if num > max_num:
                max_num = num
    return max_num


def _write_counter_atomic(counter_path: Path, item_type: str, value: int) -> None:
    counter_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if counter_path.exists():
        try:
            data = yaml.safe_load(counter_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            raise IdCounterError(f"Cannot parse {counter_path}: {e}") from e
    counters = data.get("counters") or {}
    counters[item_type] = value
    data["counters"] = counters

    fd, tmp_path = tempfile.mkstemp(
        suffix=".yaml",
        prefix=".id_counters_",
        dir=str(counter_path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=True, default_flow_style=False)
        os.replace(tmp_path, counter_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def next_id(item_type: str, root: Path | str) -> str:
    """Reserve and return the next available ID for ``item_type``.

    Atomically:

    1. Read counter value from ``.edpa/config/id_counters.yaml``.
    2. Scan ``.edpa/backlog/{type}/`` for max numeric suffix.
    3. ``next_num = max(counter, fs_scan) + 1``.
    4. Bump counter file to ``next_num``.
    5. Return formatted ID (e.g. ``"S-79"``).

    Protected by ``.edpa/.id_counter.lock``; two concurrent callers on
    the same repo cannot allocate the same number.
    """
    if item_type not in TYPE_PREFIX:
        raise ValueError(f"Unknown item type: {item_type}")

    root = Path(root)
    counter_path = root / _COUNTER_REL
    lock_path = root / _LOCK_REL
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    backlog_dir = root / ".edpa" / "backlog" / TYPE_DIRS[item_type]

    try:
        with FileLock(str(lock_path), timeout=_LOCK_TIMEOUT_SEC):
            counter_val = _read_counter(counter_path, item_type)
            fs_max = _scan_fs_max(backlog_dir, item_type)
            next_num = max(counter_val, fs_max) + 1
            _write_counter_atomic(counter_path, item_type, next_num)
            return f"{TYPE_PREFIX[item_type]}-{next_num}"
    except Timeout as e:
        raise IdCounterError(
            f"Could not acquire {lock_path} within {_LOCK_TIMEOUT_SEC}s"
        ) from e


def seed_counters_from_fs(root: Path | str) -> dict[str, int]:
    """Scan all backlog dirs and set ``counter[type] = max(fs_scan)``.

    Used by ``migrate_v1_to_v2.py`` to seed an ``id_counters.yaml`` for a
    project whose IDs were previously allocated by GitHub (no local
    counter file existed). Also useful as a recovery operation if the
    counter file is lost or corrupted.

    Returns the resulting ``{type: counter}`` map.
    """
    root = Path(root)
    counter_path = root / _COUNTER_REL
    lock_path = root / _LOCK_REL
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    backlog_root = root / ".edpa" / "backlog"

    try:
        with FileLock(str(lock_path), timeout=_LOCK_TIMEOUT_SEC):
            counters: dict[str, int] = {}
            for item_type, dir_name in TYPE_DIRS.items():
                counters[item_type] = _scan_fs_max(
                    backlog_root / dir_name, item_type,
                )
            counter_path.parent.mkdir(parents=True, exist_ok=True)
            import tempfile as _tempfile
            fd, tmp_path = _tempfile.mkstemp(
                suffix=".yaml",
                prefix=".id_counters_",
                dir=str(counter_path.parent),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    yaml.safe_dump(
                        {"counters": counters}, f,
                        sort_keys=True, default_flow_style=False,
                    )
                os.replace(tmp_path, counter_path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            return counters
    except Timeout as e:
        raise IdCounterError(
            f"Could not acquire {lock_path} within {_LOCK_TIMEOUT_SEC}s"
        ) from e
