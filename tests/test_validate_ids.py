"""Tests for plugin/edpa/scripts/validate_ids.py.

Builds a small fixture git repo, stages files in various good/bad states,
runs ``validate_ids.py --staged`` (and ``--pre-push`` via simulated
stdin), and asserts exit code + stderr content.
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import validate_ids  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _git(args, cwd, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    subprocess.run(["git", *args], cwd=str(cwd), env=env, check=True,
                   capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(["init", "-q", "-b", "main"], cwd=tmp_path)
    _git(["config", "user.email", "t@x"], cwd=tmp_path)
    _git(["config", "user.name", "T"], cwd=tmp_path)
    _git(["config", "commit.gpgsign", "false"], cwd=tmp_path)
    (tmp_path / ".edpa" / "config").mkdir(parents=True)
    for d in ("initiatives", "epics", "features", "stories", "defects",
              "events", "risks"):
        (tmp_path / ".edpa" / "backlog" / d).mkdir(parents=True)
    # Initial commit so HEAD exists.
    (tmp_path / "README").write_text("init\n")
    _git(["add", "README"], cwd=tmp_path)
    _git(["commit", "-q", "-m", "init"], cwd=tmp_path,
         env_extra={"GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
                    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00"})
    return tmp_path


def _stage_md(repo: Path, rel_path: str, frontmatter: dict, body: str = "") -> None:
    p = repo / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = yaml.safe_dump(frontmatter, sort_keys=False)
    p.write_text(f"---\n{fm}---\n{body}", encoding="utf-8")
    _git(["add", rel_path], cwd=repo)


def _stage_counter(repo: Path, counters: dict) -> None:
    path = ".edpa/config/id_counters.yaml"
    (repo / path).write_text(yaml.safe_dump({"counters": counters}))
    _git(["add", path], cwd=repo)


def _run_staged(repo: Path) -> int:
    """Invoke validate_ids.cmd_staged with cwd=repo."""
    old = Path.cwd()
    try:
        os.chdir(repo)
        return validate_ids.cmd_staged(None)  # args ignored
    finally:
        os.chdir(old)


# ---------------------------------------------------------------------------
# --staged: happy path
# ---------------------------------------------------------------------------

def test_staged_passes_with_valid_new_item(repo: Path) -> None:
    _stage_md(repo, ".edpa/backlog/stories/S-1.md", {"id": "S-1", "type": "Story"})
    _stage_counter(repo, {"Story": 1})
    assert _run_staged(repo) == 0


def test_staged_passes_with_no_backlog_changes(repo: Path) -> None:
    (repo / "notes.md").write_text("hi\n")
    _git(["add", "notes.md"], cwd=repo)
    assert _run_staged(repo) == 0


def test_staged_passes_for_modification_not_addition(repo: Path) -> None:
    """Modifying an existing committed item — no counter bump expected."""
    _stage_md(repo, ".edpa/backlog/stories/S-1.md",
              {"id": "S-1", "type": "Story", "title": "first"})
    _stage_counter(repo, {"Story": 1})
    _git(["commit", "-q", "-m", "add S-1"], cwd=repo,
         env_extra={"GIT_AUTHOR_DATE": "2026-01-02T00:00:00+00:00",
                    "GIT_COMMITTER_DATE": "2026-01-02T00:00:00+00:00"})
    _stage_md(repo, ".edpa/backlog/stories/S-1.md",
              {"id": "S-1", "type": "Story", "title": "updated"})
    assert _run_staged(repo) == 0


# ---------------------------------------------------------------------------
# --staged: failures
# ---------------------------------------------------------------------------

def test_staged_blocks_filename_id_mismatch(repo: Path, capsys) -> None:
    _stage_md(repo, ".edpa/backlog/stories/S-1.md",
              {"id": "S-2", "type": "Story"})
    _stage_counter(repo, {"Story": 1})
    rc = _run_staged(repo)
    assert rc == 1
    err = capsys.readouterr().err
    assert "filename ID" in err and "frontmatter id" in err


def test_staged_blocks_missing_id_field(repo: Path, capsys) -> None:
    _stage_md(repo, ".edpa/backlog/stories/S-1.md", {"type": "Story"})
    _stage_counter(repo, {"Story": 1})
    rc = _run_staged(repo)
    assert rc == 1
    assert "no `id:` field" in capsys.readouterr().err


def test_staged_blocks_counter_too_low_for_new_items(repo: Path, capsys) -> None:
    """Adding 1 new Story without bumping the counter → caught."""
    _stage_md(repo, ".edpa/backlog/stories/S-1.md",
              {"id": "S-1", "type": "Story"})
    # Counter at 0 (default); old=0, added=1 → needs >= 1. Leave at 0.
    _stage_counter(repo, {"Story": 0})
    rc = _run_staged(repo)
    assert rc == 1
    assert "counter[Story]" in capsys.readouterr().err


def test_staged_blocks_duplicate_id_in_set(repo: Path, capsys) -> None:
    """Two staged files with same ID in different (wrong) dirs."""
    _stage_md(repo, ".edpa/backlog/stories/S-1.md",
              {"id": "S-1", "type": "Story"})
    _stage_md(repo, ".edpa/backlog/defects/S-1.md",
              {"id": "S-1", "type": "Defect"})
    _stage_counter(repo, {"Story": 1, "Defect": 1})
    rc = _run_staged(repo)
    assert rc == 1
    assert "duplicate ID S-1" in capsys.readouterr().err


def test_staged_blocks_id_already_at_head(repo: Path, capsys) -> None:
    """Committed S-1 at HEAD; stage another file claiming ID S-1."""
    _stage_md(repo, ".edpa/backlog/stories/S-1.md",
              {"id": "S-1", "type": "Story"})
    _stage_counter(repo, {"Story": 1})
    _git(["commit", "-q", "-m", "add S-1"], cwd=repo,
         env_extra={"GIT_AUTHOR_DATE": "2026-01-02T00:00:00+00:00",
                    "GIT_COMMITTER_DATE": "2026-01-02T00:00:00+00:00"})
    _stage_md(repo, ".edpa/backlog/defects/S-1.md",
              {"id": "S-1", "type": "Defect"})
    _stage_counter(repo, {"Story": 1, "Defect": 1})
    rc = _run_staged(repo)
    assert rc == 1
    assert "S-1 already exists at HEAD" in capsys.readouterr().err
