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


# ===== Phase 1 additions: scenarios A (multi), B (parent chain), C (cascading) =====

def _init_remote(remote: Path, counters: dict, initial_items: list[tuple[str, str, dict, str]]) -> None:
    """Initialize a remote with .edpa scaffolding + counters + initial items.

    initial_items: list of (rel_path, commit_msg, frontmatter_dict, body)
    """
    _git(["init", "-q", "-b", "main"], cwd=remote)
    _git(["config", "user.email", "t@x"], cwd=remote)
    _git(["config", "user.name", "T"], cwd=remote)
    _git(["config", "commit.gpgsign", "false"], cwd=remote)
    for d in ("initiatives", "epics", "features", "stories", "defects",
              "events", "risks"):
        (remote / ".edpa" / "backlog" / d).mkdir(parents=True)
    (remote / ".edpa" / "config").mkdir(parents=True)
    (remote / ".edpa" / "config" / "id_counters.yaml").write_text(
        yaml.safe_dump({"counters": counters})
    )
    for rel, _msg, fm, body in initial_items:
        _write_md(remote, rel, fm, body)
    _git(["add", "."], cwd=remote)
    _git(["commit", "-q", "-m", "initial"], cwd=remote,
         env_extra=_date_env("2026-01-01T00:00:00+00:00"))


def _clone_local(remote: Path, local: Path, parent: Path) -> None:
    """Clone remote into local and set git identity."""
    local.mkdir(parents=True, exist_ok=True)
    _git(["clone", "-q", str(remote), str(local)], cwd=parent)
    _git(["config", "user.email", "t@x"], cwd=local)
    _git(["config", "user.name", "T"], cwd=local)
    _git(["config", "commit.gpgsign", "false"], cwd=local)


def _commit_to_remote(remote: Path, items: list[tuple[str, dict, str]],
                       counter_updates: dict, msg: str, date: str) -> None:
    """Simulate someone pushing additional items + updated counters to main."""
    for rel, fm, body in items:
        _write_md(remote, rel, fm, body)
    if counter_updates:
        cur = yaml.safe_load(
            (remote / ".edpa" / "config" / "id_counters.yaml").read_text()
        ) or {"counters": {}}
        cur.setdefault("counters", {}).update(counter_updates)
        (remote / ".edpa" / "config" / "id_counters.yaml").write_text(
            yaml.safe_dump(cur)
        )
    _git(["add", "."], cwd=remote)
    _git(["commit", "-q", "-m", msg], cwd=remote, env_extra=_date_env(date))


def test_multi_collision_both_renumbered_sequentially(tmp_path: Path) -> None:
    """Scenario A variant: local has 2 Story collisions; both get renumbered with
    sequential new IDs (S-5, S-6) without re-using the same number."""
    remote = tmp_path / "remote"
    remote.mkdir()
    _init_remote(remote, counters={"Story": 2}, initial_items=[
        (".edpa/backlog/stories/S-1.md", "init S-1",
         {"id": "S-1", "type": "Story"}, ""),
        (".edpa/backlog/stories/S-2.md", "init S-2",
         {"id": "S-2", "type": "Story"}, ""),
    ])

    local = tmp_path / "local"
    _clone_local(remote, local, tmp_path)

    # Simulate Dev A merging S-3 (Auth) + S-4 (Reports) into main
    _commit_to_remote(remote, [
        (".edpa/backlog/stories/S-3.md",
         {"id": "S-3", "type": "Story", "title": "Auth (A)"}, ""),
        (".edpa/backlog/stories/S-4.md",
         {"id": "S-4", "type": "Story", "title": "Reports (A)"}, ""),
    ], counter_updates={"Story": 4}, msg="A merges S-3+S-4",
       date="2026-01-02T10:00:00+00:00")

    # Dev B's local: independently added S-3 (Logs) + S-4 (Search) before A merged
    _write_md(local, ".edpa/backlog/stories/S-3.md",
              {"id": "S-3", "type": "Story", "title": "Logs (B)"})
    _write_md(local, ".edpa/backlog/stories/S-4.md",
              {"id": "S-4", "type": "Story", "title": "Search (B)"})
    (local / ".edpa" / "config" / "id_counters.yaml").write_text(
        yaml.safe_dump({"counters": {"Story": 4}})
    )
    _git(["add", "."], cwd=local)
    _git(["commit", "-q", "-m", "B adds S-3+S-4"], cwd=local,
         env_extra=_date_env("2026-01-02T11:00:00+00:00"))

    # B runs renumber against fetched origin/main
    old = Path.cwd()
    try:
        os.chdir(local)
        collisions = rc.find_collisions(local, remote="origin")
        summary = rc.apply_collisions(local, collisions)
    finally:
        os.chdir(old)

    # 2 collisions detected
    assert len(collisions) == 2, f"expected 2 collisions, got {collisions}"
    by_old = {c["old_id"]: c["new_id"] for c in collisions}
    # Sequential new IDs (working_max increments inside the loop)
    assert by_old == {"S-3": "S-5", "S-4": "S-6"}

    # Local files renamed
    assert not (local / ".edpa/backlog/stories/S-3.md").exists()
    assert not (local / ".edpa/backlog/stories/S-4.md").exists()
    assert (local / ".edpa/backlog/stories/S-5.md").exists()
    assert (local / ".edpa/backlog/stories/S-6.md").exists()

    # IDs rewritten inside files
    assert "id: S-5" in (local / ".edpa/backlog/stories/S-5.md").read_text()
    assert "id: S-6" in (local / ".edpa/backlog/stories/S-6.md").read_text()
    # Titles preserved (B's content survives the rename)
    assert "Logs (B)" in (local / ".edpa/backlog/stories/S-5.md").read_text()
    assert "Search (B)" in (local / ".edpa/backlog/stories/S-6.md").read_text()

    # Counter bumped to highest new id
    counter = yaml.safe_load(
        (local / ".edpa/config/id_counters.yaml").read_text()
    )
    assert counter["counters"]["Story"] == 6

    # Summary
    assert summary["renamed"] == 2
    assert summary["counter_bumps"] == {"Story": 6}


def test_parent_chain_renumber_propagates_to_children_only(tmp_path: Path) -> None:
    """Scenario B: F-3 renumber → F-4 must update direct children S-9 + EV-1
    parent refs, but leave grandchild S-10 (whose parent is S-9, not F-3) alone."""
    remote = tmp_path / "remote"
    remote.mkdir()
    _init_remote(remote, counters={"Initiative": 1, "Epic": 1, "Feature": 2}, initial_items=[
        (".edpa/backlog/initiatives/I-1.md", "init",
         {"id": "I-1", "type": "Initiative"}, ""),
        (".edpa/backlog/epics/E-1.md", "init",
         {"id": "E-1", "type": "Epic", "parent": "I-1"}, ""),
        (".edpa/backlog/features/F-1.md", "init",
         {"id": "F-1", "type": "Feature", "parent": "E-1"}, ""),
        (".edpa/backlog/features/F-2.md", "init",
         {"id": "F-2", "type": "Feature", "parent": "E-1"}, ""),
    ])

    local = tmp_path / "local"
    _clone_local(remote, local, tmp_path)

    # Simulate Dev A merging F-3 (Auth) + S-7/S-8 children + D-1 grandchild
    _commit_to_remote(remote, [
        (".edpa/backlog/features/F-3.md",
         {"id": "F-3", "type": "Feature", "parent": "E-1", "title": "Auth (A)"}, ""),
        (".edpa/backlog/stories/S-7.md",
         {"id": "S-7", "type": "Story", "parent": "F-3"}, ""),
        (".edpa/backlog/stories/S-8.md",
         {"id": "S-8", "type": "Story", "parent": "F-3"}, ""),
        (".edpa/backlog/defects/D-1.md",
         {"id": "D-1", "type": "Defect", "parent": "S-7"}, ""),
    ], counter_updates={"Feature": 3, "Story": 8, "Defect": 1},
       msg="A merges F-3 + children", date="2026-01-02T10:00:00+00:00")

    # Dev B's local: F-3 (Reports) + S-9 (parent F-3) + EV-1 (parent F-3)
    # + S-10 (parent S-9 — grandchild relative to F-3)
    _write_md(local, ".edpa/backlog/features/F-3.md",
              {"id": "F-3", "type": "Feature", "parent": "E-1", "title": "Reports (B)"})
    _write_md(local, ".edpa/backlog/stories/S-9.md",
              {"id": "S-9", "type": "Story", "parent": "F-3", "title": "List endpoint"})
    _write_md(local, ".edpa/backlog/events/EV-1.md",
              {"id": "EV-1", "type": "Event", "parent": "F-3"})
    _write_md(local, ".edpa/backlog/stories/S-10.md",
              {"id": "S-10", "type": "Story", "parent": "S-9", "title": "Pagination"})
    (local / ".edpa" / "config" / "id_counters.yaml").write_text(
        yaml.safe_dump({"counters": {
            "Initiative": 1, "Epic": 1, "Feature": 3, "Story": 10, "Event": 1
        }})
    )
    _git(["add", "."], cwd=local)
    _git(["commit", "-q", "-m", "B adds F-3 + S-9 + EV-1 + S-10"], cwd=local,
         env_extra=_date_env("2026-01-02T11:00:00+00:00"))

    # B runs renumber
    old = Path.cwd()
    try:
        os.chdir(local)
        collisions = rc.find_collisions(local, remote="origin")
        summary = rc.apply_collisions(local, collisions)
    finally:
        os.chdir(old)

    # Only F-3 should collide (S-9, EV-1, S-10 are unique locally)
    assert len(collisions) == 1
    c = collisions[0]
    assert c["old_id"] == "F-3"
    # Remote_max Feature=3, so renumber to F-4
    assert c["new_id"] == "F-4"
    assert c["type"] == "Feature"

    # File renamed
    assert not (local / ".edpa/backlog/features/F-3.md").exists()
    assert (local / ".edpa/backlog/features/F-4.md").exists()
    # Content preserved + id field rewritten
    f4_text = (local / ".edpa/backlog/features/F-4.md").read_text()
    assert "id: F-4" in f4_text
    assert "Reports (B)" in f4_text
    assert "parent: E-1" in f4_text  # parent ref preserved

    # Direct children S-9 + EV-1 had their parent ref updated
    s9_text = (local / ".edpa/backlog/stories/S-9.md").read_text()
    assert "parent: F-4" in s9_text
    assert "parent: F-3" not in s9_text
    ev1_text = (local / ".edpa/backlog/events/EV-1.md").read_text()
    assert "parent: F-4" in ev1_text
    assert "parent: F-3" not in ev1_text

    # Grandchild S-10 (parent S-9) is UNCHANGED — not part of the F-3 chain
    s10_text = (local / ".edpa/backlog/stories/S-10.md").read_text()
    assert "parent: S-9" in s10_text
    # And does not accidentally mention F-4
    assert "F-4" not in s10_text
    assert "F-3" not in s10_text

    # Counter bumped Feature → 4
    counter = yaml.safe_load(
        (local / ".edpa/config/id_counters.yaml").read_text()
    )
    assert counter["counters"]["Feature"] == 4

    # Summary: 1 file renamed, 2 parent refs updated (S-9 + EV-1)
    assert summary["renamed"] == 1
    assert summary["parent_refs_updated"] == 2
    assert summary["counter_bumps"] == {"Feature": 4}


def test_collision_detected_when_on_feature_branch_against_main(tmp_path: Path) -> None:
    """REGRESSION: find_collisions must compare against integration target
    (origin/main), NOT against matching remote branch.

    Pre-fix: when bob pushes feature/foo to origin and runs renumber while still
    on feature/foo, the script compared against origin/feature/foo (= same as
    HEAD), found no diff, returned []. This false negative hid real collisions
    with main, breaking the PR workflow.

    Post-fix: script auto-detects remote default branch via refs/remotes/origin/HEAD
    and compares against that. Collision with main's S-5 is correctly detected
    even when bob is on (and has pushed) feature branch.
    """
    remote = tmp_path / "remote"
    remote.mkdir()
    _init_remote(remote, counters={"Story": 4}, initial_items=[
        (".edpa/backlog/stories/S-1.md", "init",
         {"id": "S-1", "type": "Story"}, ""),
        (".edpa/backlog/stories/S-2.md", "init",
         {"id": "S-2", "type": "Story"}, ""),
        (".edpa/backlog/stories/S-3.md", "init",
         {"id": "S-3", "type": "Story"}, ""),
        (".edpa/backlog/stories/S-4.md", "init",
         {"id": "S-4", "type": "Story"}, ""),
    ])

    local = tmp_path / "local"
    _clone_local(remote, local, tmp_path)

    # Alice merges S-5 (Auth) to main
    _commit_to_remote(remote, [
        (".edpa/backlog/stories/S-5.md",
         {"id": "S-5", "type": "Story", "title": "Auth (alice)"}, ""),
    ], counter_updates={"Story": 5}, msg="alice merges S-5",
       date="2026-01-02T10:00:00+00:00")

    # Bob creates feature branch + S-5 (Reports), pushes (simulated by checkout + commit
    # on a branch; no actual remote push needed for the test — find_collisions fetches)
    _git(["checkout", "-q", "-b", "feature/reports"], cwd=local)
    _write_md(local, ".edpa/backlog/stories/S-5.md",
              {"id": "S-5", "type": "Story", "title": "Reports (bob)"})
    (local / ".edpa" / "config" / "id_counters.yaml").write_text(
        yaml.safe_dump({"counters": {"Story": 5}})
    )
    _git(["add", "."], cwd=local)
    _git(["commit", "-q", "-m", "bob adds S-5 on feature/reports"], cwd=local,
         env_extra=_date_env("2026-01-02T11:00:00+00:00"))

    # Simulate bob pushing his branch to origin (creates origin/feature/reports
    # that matches HEAD exactly — this is the pre-fix gotcha)
    _git(["push", "-q", "origin", "feature/reports"], cwd=local)

    # Now run find_collisions. With PRE-fix bug: would return [] because
    # origin/feature/reports == HEAD. With POST-fix: detects S-5 vs origin/main.
    old = Path.cwd()
    try:
        os.chdir(local)
        collisions = rc.find_collisions(local, remote="origin")
    finally:
        os.chdir(old)

    assert len(collisions) == 1, (
        f"Expected 1 collision against origin/main (post-fix), got {collisions}. "
        "If empty: target_branch resolution is broken — should auto-detect "
        "remote's default branch, not the matching remote branch."
    )
    c = collisions[0]
    assert c["old_id"] == "S-5"
    assert c["new_id"] == "S-6"  # max(remote=5, local=5) + 1
    assert c["type"] == "Story"


def test_collision_target_branch_arg_overrides_default(tmp_path: Path) -> None:
    """Verify --target arg lets caller compare against a non-default branch
    (Git Flow with `develop` etc.)."""
    remote = tmp_path / "remote"
    remote.mkdir()
    _init_remote(remote, counters={"Story": 2}, initial_items=[
        (".edpa/backlog/stories/S-1.md", "init",
         {"id": "S-1", "type": "Story"}, ""),
        (".edpa/backlog/stories/S-2.md", "init",
         {"id": "S-2", "type": "Story"}, ""),
    ])

    # Create a `develop` branch on remote with S-3
    _git(["checkout", "-q", "-b", "develop"], cwd=remote)
    _write_md(remote, ".edpa/backlog/stories/S-3.md",
              {"id": "S-3", "type": "Story", "title": "develop S-3"})
    (remote / ".edpa" / "config" / "id_counters.yaml").write_text(
        yaml.safe_dump({"counters": {"Story": 3}})
    )
    _git(["add", "."], cwd=remote)
    _git(["commit", "-q", "-m", "develop S-3"], cwd=remote,
         env_extra=_date_env("2026-01-02T10:00:00+00:00"))
    _git(["checkout", "-q", "main"], cwd=remote)

    local = tmp_path / "local"
    _clone_local(remote, local, tmp_path)

    # local adds S-3 (would only collide with develop, not main)
    _write_md(local, ".edpa/backlog/stories/S-3.md",
              {"id": "S-3", "type": "Story", "title": "local S-3"})
    _git(["add", "."], cwd=local)
    _git(["commit", "-q", "-m", "local S-3"], cwd=local,
         env_extra=_date_env("2026-01-02T11:00:00+00:00"))

    # Default target (main) → NO collision (S-3 not on main)
    old = Path.cwd()
    try:
        os.chdir(local)
        c_default = rc.find_collisions(local, remote="origin")
        # Explicit --target develop → DOES detect collision
        c_develop = rc.find_collisions(local, remote="origin", target_branch="develop")
    finally:
        os.chdir(old)

    assert c_default == []
    assert len(c_develop) == 1
    assert c_develop[0]["old_id"] == "S-3"


def test_three_dev_cascading_collisions(tmp_path: Path) -> None:
    """Scenario C: A merges S-2 → main. B (also had S-2) renumbers to S-3, merges.
    C (cloned at S-1 only, then added S-2 + S-3 locally) faces 2 collisions and
    must renumber both with sequential new IDs (S-4, S-5)."""
    remote = tmp_path / "remote"
    remote.mkdir()
    _init_remote(remote, counters={"Story": 1}, initial_items=[
        (".edpa/backlog/stories/S-1.md", "init S-1",
         {"id": "S-1", "type": "Story"}, ""),
    ])

    # Dev C clones at this state (only S-1 known)
    local_c = tmp_path / "local_c"
    _clone_local(remote, local_c, tmp_path)

    # Simulate Dev A merging S-2 (Auth)
    _commit_to_remote(remote, [
        (".edpa/backlog/stories/S-2.md",
         {"id": "S-2", "type": "Story", "title": "Auth (A)"}, ""),
    ], counter_updates={"Story": 2}, msg="A merges S-2",
       date="2026-01-02T10:00:00+00:00")

    # Simulate Dev B's renumber + merge: their original S-2 was Logs;
    # after collision with A, B renumbered to S-3 (Logs).
    _commit_to_remote(remote, [
        (".edpa/backlog/stories/S-3.md",
         {"id": "S-3", "type": "Story", "title": "Logs (B, was S-2)"}, ""),
    ], counter_updates={"Story": 3}, msg="B merges S-3 (renumbered from S-2)",
       date="2026-01-02T11:00:00+00:00")

    # Now C (still on local clone with only S-1) adds S-2 (Search) and S-3 (Cache)
    _write_md(local_c, ".edpa/backlog/stories/S-2.md",
              {"id": "S-2", "type": "Story", "title": "Search (C)"})
    _write_md(local_c, ".edpa/backlog/stories/S-3.md",
              {"id": "S-3", "type": "Story", "title": "Cache (C)"})
    (local_c / ".edpa" / "config" / "id_counters.yaml").write_text(
        yaml.safe_dump({"counters": {"Story": 3}})
    )
    _git(["add", "."], cwd=local_c)
    _git(["commit", "-q", "-m", "C adds S-2+S-3"], cwd=local_c,
         env_extra=_date_env("2026-01-02T12:00:00+00:00"))

    # C runs renumber — should detect 2 collisions and assign S-4, S-5
    old = Path.cwd()
    try:
        os.chdir(local_c)
        collisions = rc.find_collisions(local_c, remote="origin")
        summary = rc.apply_collisions(local_c, collisions)
    finally:
        os.chdir(old)

    # 2 collisions
    assert len(collisions) == 2
    by_old = {c["old_id"]: c["new_id"] for c in collisions}
    # remote_max Story = 3 (after A + B), so first collision → S-4, second → S-5
    assert by_old == {"S-2": "S-4", "S-3": "S-5"}

    # Files renamed correctly
    assert not (local_c / ".edpa/backlog/stories/S-2.md").exists()
    assert not (local_c / ".edpa/backlog/stories/S-3.md").exists()
    assert (local_c / ".edpa/backlog/stories/S-4.md").exists()
    assert (local_c / ".edpa/backlog/stories/S-5.md").exists()

    # Content preserved
    assert "Search (C)" in (local_c / ".edpa/backlog/stories/S-4.md").read_text()
    assert "Cache (C)" in (local_c / ".edpa/backlog/stories/S-5.md").read_text()
    assert "id: S-4" in (local_c / ".edpa/backlog/stories/S-4.md").read_text()
    assert "id: S-5" in (local_c / ".edpa/backlog/stories/S-5.md").read_text()

    # Counter bumped to 5
    counter = yaml.safe_load(
        (local_c / ".edpa/config/id_counters.yaml").read_text()
    )
    assert counter["counters"]["Story"] == 5

    # Summary
    assert summary["renamed"] == 2
    assert summary["counter_bumps"] == {"Story": 5}
