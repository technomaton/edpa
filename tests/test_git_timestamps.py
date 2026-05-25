"""Tests for plugin/edpa/scripts/_git_timestamps.py.

Builds a small fixture git repo, makes controlled commits at known
timestamps, then verifies that ``created_at``/``updated_at``/``closed_at``
return the right ISO-8601 strings from ``git log``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import _git_timestamps as gts


# Matches both "...+02:00" and "...Z" (git uses Z for UTC).
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$")


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _git_run(args: list[str], cwd: Path, env_extra: dict[str, str] | None = None) -> None:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, check=True, capture_output=True
    )


def _git_init(root: Path) -> None:
    _git_run(["init", "-q", "-b", "main"], root)
    _git_run(["config", "user.email", "test@example.com"], root)
    _git_run(["config", "user.name", "Test User"], root)
    _git_run(["config", "commit.gpgsign", "false"], root)


def _commit(root: Path, msg: str, when_iso: str) -> None:
    env = {
        "GIT_AUTHOR_DATE": when_iso,
        "GIT_COMMITTER_DATE": when_iso,
    }
    _git_run(["add", "-A"], root)
    _git_run(["commit", "-q", "-m", msg], root, env_extra=env)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git_init(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# created_at
# ---------------------------------------------------------------------------

def test_created_at_returns_first_commit_time(repo: Path) -> None:
    item = repo / ".edpa/backlog/stories/S-1.md"
    item.parent.mkdir(parents=True)
    item.write_text("---\nid: S-1\nstatus: Planned\n---\n")
    _commit(repo, "add S-1", "2026-01-15T10:00:00+02:00")

    item.write_text("---\nid: S-1\nstatus: InProgress\n---\n")
    _commit(repo, "S-1 in progress", "2026-02-01T12:30:00+02:00")

    assert gts.created_at(item, repo) == "2026-01-15T10:00:00+02:00"


def test_created_at_returns_none_for_untracked_file(repo: Path) -> None:
    item = repo / ".edpa/backlog/stories/S-404.md"
    item.parent.mkdir(parents=True)
    item.write_text("---\n---\n")  # not committed
    assert gts.created_at(item, repo) is None


def test_created_at_accepts_relative_and_absolute_path(repo: Path) -> None:
    item = repo / ".edpa/backlog/stories/S-2.md"
    item.parent.mkdir(parents=True)
    item.write_text("---\nid: S-2\n---\n")
    _commit(repo, "add S-2", "2026-03-01T09:00:00+02:00")

    abs_result = gts.created_at(item, repo)
    rel_result = gts.created_at(Path(".edpa/backlog/stories/S-2.md"), repo)
    assert abs_result == rel_result == "2026-03-01T09:00:00+02:00"


# ---------------------------------------------------------------------------
# updated_at
# ---------------------------------------------------------------------------

def test_updated_at_returns_last_commit_time(repo: Path) -> None:
    item = repo / ".edpa/backlog/stories/S-3.md"
    item.parent.mkdir(parents=True)
    item.write_text("---\nid: S-3\nstatus: Planned\n---\n")
    _commit(repo, "add S-3", "2026-01-15T10:00:00+02:00")

    item.write_text("---\nid: S-3\nstatus: InProgress\n---\n")
    _commit(repo, "S-3 in progress", "2026-02-01T12:30:00+02:00")

    item.write_text("---\nid: S-3\nstatus: Review\n---\n")
    _commit(repo, "S-3 review", "2026-03-10T15:45:00+02:00")

    assert gts.updated_at(item, repo) == "2026-03-10T15:45:00+02:00"


def test_updated_at_equals_created_at_for_single_commit(repo: Path) -> None:
    item = repo / ".edpa/backlog/stories/S-4.md"
    item.parent.mkdir(parents=True)
    item.write_text("---\nid: S-4\n---\n")
    _commit(repo, "add S-4", "2026-04-01T08:00:00+00:00")

    assert gts.created_at(item, repo) == gts.updated_at(item, repo)


def test_updated_at_returns_none_for_untracked(repo: Path) -> None:
    assert gts.updated_at(repo / "nonexistent.md", repo) is None


# ---------------------------------------------------------------------------
# closed_at
# ---------------------------------------------------------------------------

def test_closed_at_returns_first_done_commit(repo: Path) -> None:
    item = repo / ".edpa/backlog/stories/S-5.md"
    item.parent.mkdir(parents=True)
    item.write_text("---\nid: S-5\nstatus: Planned\n---\n")
    _commit(repo, "add S-5", "2026-01-01T10:00:00+02:00")

    item.write_text("---\nid: S-5\nstatus: InProgress\n---\n")
    _commit(repo, "in progress", "2026-01-10T10:00:00+02:00")

    item.write_text("---\nid: S-5\nstatus: Done\n---\n")
    _commit(repo, "done!", "2026-02-15T17:30:00+02:00")

    assert gts.closed_at(item, repo) == "2026-02-15T17:30:00+02:00"


def test_closed_at_returns_none_when_never_done(repo: Path) -> None:
    item = repo / ".edpa/backlog/stories/S-6.md"
    item.parent.mkdir(parents=True)
    item.write_text("---\nid: S-6\nstatus: Planned\n---\n")
    _commit(repo, "add S-6", "2026-01-01T10:00:00+00:00")

    item.write_text("---\nid: S-6\nstatus: InProgress\n---\n")
    _commit(repo, "S-6 in progress", "2026-02-01T10:00:00+00:00")

    assert gts.closed_at(item, repo) is None


def test_closed_at_uses_first_done_when_reopened(repo: Path) -> None:
    item = repo / ".edpa/backlog/stories/S-7.md"
    item.parent.mkdir(parents=True)
    item.write_text("---\nid: S-7\nstatus: Done\n---\n")
    _commit(repo, "S-7 done", "2026-01-01T10:00:00+02:00")

    item.write_text("---\nid: S-7\nstatus: InProgress\n---\n")
    _commit(repo, "S-7 reopened", "2026-02-01T10:00:00+02:00")

    item.write_text("---\nid: S-7\nstatus: Done\n---\n")
    _commit(repo, "S-7 done again", "2026-03-01T10:00:00+02:00")

    assert gts.closed_at(item, repo) == "2026-01-01T10:00:00+02:00"


# ---------------------------------------------------------------------------
# Format & robustness
# ---------------------------------------------------------------------------

def test_returns_iso8601_with_timezone(repo: Path) -> None:
    item = repo / ".edpa/backlog/stories/S-8.md"
    item.parent.mkdir(parents=True)
    item.write_text("---\nid: S-8\n---\n")
    _commit(repo, "add S-8", "2026-05-25T14:00:00+02:00")

    result = gts.created_at(item, repo)
    assert result is not None
    assert ISO_RE.match(result), f"unexpected format: {result!r}"


def test_no_git_binary_returns_none(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If git is missing from PATH, all functions return None — never crash."""
    monkeypatch.setenv("PATH", "")
    assert gts.created_at(repo / "anything.md", repo) is None
    assert gts.updated_at(repo / "anything.md", repo) is None
    assert gts.closed_at(repo / "anything.md", repo) is None
