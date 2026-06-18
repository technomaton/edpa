"""Item lifecycle timestamps derived from git log.

V2 replacement for the ``createdAt``/``updatedAt``/``closedAt`` fields
that ``sync.py`` previously pulled from the GitHub Issues API. All
timestamps are returned as ISO-8601 strings exactly as
``git log --format=%aI`` emits them (e.g. ``2026-05-25T14:00:00+02:00``
or ``2026-05-25T12:00:00Z`` for UTC).

Returns ``None`` when the file is not tracked, the relevant commit
cannot be found, or ``git`` is unavailable. Callers should treat
``None`` as "unknown" rather than as a failure.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        res = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False, encoding="utf-8",
        )
    except FileNotFoundError:
        return None
    if res.returncode != 0:
        return None
    out = res.stdout.strip()
    return out or None


def _rel(file_path: Path, repo_root: Path) -> Path:
    return file_path.relative_to(repo_root) if file_path.is_absolute() else file_path


def created_at(file_path: Path, repo_root: Path) -> str | None:
    """Author date of the first commit that added ``file_path``."""
    out = _git(
        [
            "log",
            "--diff-filter=A",
            "--follow",
            "--format=%aI",
            "--reverse",
            "--",
            str(_rel(file_path, repo_root)),
        ],
        repo_root,
    )
    return out.splitlines()[0] if out else None


def updated_at(file_path: Path, repo_root: Path) -> str | None:
    """Author date of the most recent commit touching ``file_path``."""
    return _git(
        ["log", "-1", "--format=%aI", "--", str(_rel(file_path, repo_root))],
        repo_root,
    )


def closed_at(file_path: Path, repo_root: Path) -> str | None:
    """Author date of the first commit where ``status: Done`` appears in ``file_path``.

    Uses ``git log -G`` pickaxe-style search. Returns ``None`` if the file
    never entered Done state. Re-open + re-close cycles return the *first*
    transition to Done.
    """
    out = _git(
        [
            "log",
            "-G",
            r"^status:[[:space:]]*Done",
            "--format=%aI",
            "--reverse",
            "--",
            str(_rel(file_path, repo_root)),
        ],
        repo_root,
    )
    return out.splitlines()[0] if out else None
