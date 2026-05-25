"""Tests for plugin/edpa/scripts/renumber_collisions.py.

Builds a two-branch fixture repo where a local branch and the "remote"
ref both contain a file claiming the same ID. Calls find_collisions +
apply_collisions and asserts file rename, id rewrite, parent ref update,
and counter bump.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import renumber_collisions as rc  # noqa: E402


def _git(args, cwd, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(["git", *args], cwd=str(cwd), env=env, check=True,
                          capture_output=True, text=True).stdout


def _write_md(repo: Path, rel: str, fm: dict, body: str = "") -> Path:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    text = f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n{body}"
    p.write_text(text)
    return p


def _date_env(date: str) -> dict[str, str]:
    return {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}


@pytest.fixture
def colliding_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Two repos: 'remote' (bare-ish) and 'local' that share history then diverge.

    Both add S-3 → collision after pull/fetch.
    """
    remote = tmp_path / "remote"
    local = tmp_path / "local"
    remote.mkdir()
    local.mkdir()

    _git(["init", "-q", "-b", "main"], cwd=remote)
    _git(["config", "user.email", "t@x"], cwd=remote)
    _git(["config", "user.name", "T"], cwd=remote)
    _git(["config", "commit.gpgsign", "false"], cwd=remote)
    for d in ("initiatives", "epics", "features", "stories", "defects",
              "events", "risks"):
        (remote / ".edpa" / "backlog" / d).mkdir(parents=True)
    (remote / ".edpa" / "config").mkdir(parents=True)
    (remote / ".edpa" / "config" / "id_counters.yaml").write_text(
        yaml.safe_dump({"counters": {"Story": 2}})
    )
    _write_md(remote, ".edpa/backlog/stories/S-1.md", {"id": "S-1", "type": "Story"})
    _write_md(remote, ".edpa/backlog/stories/S-2.md", {"id": "S-2", "type": "Story"})
    _git(["add", "."], cwd=remote)
    _git(["commit", "-q", "-m", "initial"], cwd=remote,
         env_extra=_date_env("2026-01-01T00:00:00+00:00"))

    _git(["clone", "-q", str(remote), str(local)], cwd=tmp_path)
    _git(["config", "user.email", "t@x"], cwd=local)
    _git(["config", "user.name", "T"], cwd=local)
    _git(["config", "commit.gpgsign", "false"], cwd=local)

    # Remote adds S-3 (e.g., another collaborator pushed it)
    _write_md(remote, ".edpa/backlog/stories/S-3.md",
              {"id": "S-3", "type": "Story", "title": "remote story"})
    (remote / ".edpa" / "config" / "id_counters.yaml").write_text(
        yaml.safe_dump({"counters": {"Story": 3}})
    )
    _git(["add", "."], cwd=remote)
    _git(["commit", "-q", "-m", "add S-3 (remote)"], cwd=remote,
         env_extra=_date_env("2026-01-02T00:00:00+00:00"))

    # Local also adds S-3 (didn't pull first) + a child Defect referencing S-3
    _write_md(local, ".edpa/backlog/stories/S-3.md",
              {"id": "S-3", "type": "Story", "title": "local story"})
    _write_md(local, ".edpa/backlog/defects/D-1.md",
              {"id": "D-1", "type": "Defect", "parent": "S-3"})
    (local / ".edpa" / "config" / "id_counters.yaml").write_text(
        yaml.safe_dump({"counters": {"Story": 3, "Defect": 1}})
    )
    _git(["add", "."], cwd=local)
    _git(["commit", "-q", "-m", "add S-3 (local) + D-1 child"], cwd=local,
         env_extra=_date_env("2026-01-02T01:00:00+00:00"))

    return remote, local


def test_find_collisions_detects_shared_id(colliding_repo) -> None:
    _remote, local = colliding_repo
    old = Path.cwd()
    try:
        os.chdir(local)
        collisions = rc.find_collisions(local, remote="origin")
    finally:
        os.chdir(old)

    assert len(collisions) == 1
    c = collisions[0]
    assert c["old_id"] == "S-3"
    assert c["new_id"] == "S-4"  # bumped above remote max (3)
    assert c["type"] == "Story"


def test_apply_renames_file_and_rewrites_id(colliding_repo) -> None:
    _remote, local = colliding_repo
    old = Path.cwd()
    try:
        os.chdir(local)
        collisions = rc.find_collisions(local, remote="origin")
        summary = rc.apply_collisions(local, collisions)
    finally:
        os.chdir(old)

    # Old file gone, new file present
    assert not (local / ".edpa/backlog/stories/S-3.md").exists()
    assert (local / ".edpa/backlog/stories/S-4.md").exists()

    # id field rewritten
    text = (local / ".edpa/backlog/stories/S-4.md").read_text()
    assert "id: S-4" in text
    assert "S-3" not in text

    # parent ref in D-1 updated S-3 → S-4
    d_text = (local / ".edpa/backlog/defects/D-1.md").read_text()
    assert "parent: S-4" in d_text
    assert "parent: S-3" not in d_text

    # Counter bumped to 4
    counter = yaml.safe_load(
        (local / ".edpa/config/id_counters.yaml").read_text()
    )
    assert counter["counters"]["Story"] == 4

    # Summary
    assert summary["renamed"] == 1
    assert summary["parent_refs_updated"] == 1
    assert summary["counter_bumps"] == {"Story": 4}


def test_no_collisions_when_local_is_unique(tmp_path: Path) -> None:
    """Local has S-5 that doesn't exist anywhere upstream → no collision."""
    remote = tmp_path / "r"
    local = tmp_path / "l"
    remote.mkdir(); local.mkdir()

    _git(["init", "-q", "-b", "main"], cwd=remote)
    _git(["config", "user.email", "t@x"], cwd=remote)
    _git(["config", "user.name", "T"], cwd=remote)
    _git(["config", "commit.gpgsign", "false"], cwd=remote)
    for d in ("initiatives", "epics", "features", "stories", "defects",
              "events", "risks"):
        (remote / ".edpa" / "backlog" / d).mkdir(parents=True)
    (remote / ".edpa" / "config").mkdir(parents=True)
    _write_md(remote, ".edpa/backlog/stories/S-1.md", {"id": "S-1", "type": "Story"})
    _git(["add", "."], cwd=remote)
    _git(["commit", "-q", "-m", "init"], cwd=remote,
         env_extra=_date_env("2026-01-01T00:00:00+00:00"))

    _git(["clone", "-q", str(remote), str(local)], cwd=tmp_path)
    _git(["config", "user.email", "t@x"], cwd=local)
    _git(["config", "user.name", "T"], cwd=local)
    _git(["config", "commit.gpgsign", "false"], cwd=local)

    _write_md(local, ".edpa/backlog/stories/S-5.md", {"id": "S-5", "type": "Story"})
    _git(["add", "."], cwd=local)
    _git(["commit", "-q", "-m", "add S-5"], cwd=local,
         env_extra=_date_env("2026-01-02T00:00:00+00:00"))

    old = Path.cwd()
    try:
        os.chdir(local)
        collisions = rc.find_collisions(local, remote="origin")
    finally:
        os.chdir(old)
    assert collisions == []
