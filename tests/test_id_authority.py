"""Tests for the allocation authority in plugin/edpa/scripts/id_counter.py.

Three things ADR-014 added on top of the per-tree counter:

* per-clone state in the git common dir, so worktrees of one clone share
  one sequence even in local mode;
* ``resolve_authority`` — who hands out IDs, decided per clone;
* remote mode — ``next_id`` reserves through the ledger and fails closed.

(The per-tree contract itself stays pinned by test_id_counter.py, which
runs in plain directories.)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from ledger_world import (  # noqa: F401  (fixtures are used by name)
    SCRIPTS, World, _isolated_git_config, _templates, alice, bob, git,
    ledger_ready, world,
)

import _id_ledger as ledger  # noqa: E402
import id_counter  # noqa: E402
from id_counter import (  # noqa: E402
    AUTHORITY_ENV, IdCounterError, TYPE_DIRS, next_id, resolve_authority,
    scan_known_max, seed_counters_from_fs,
)

COUNTER = Path(".edpa/config/id_counters.yaml")


def project(root: Path, *, authority: str | None = None,
            counters: dict | None = None, extra_ids: dict | None = None) -> Path:
    """Lay an (untracked) ``.edpa/`` skeleton into a checkout."""
    (root / ".edpa" / "config").mkdir(parents=True, exist_ok=True)
    for d in TYPE_DIRS.values():
        (root / ".edpa" / "backlog" / d).mkdir(parents=True, exist_ok=True)
    if authority or extra_ids:
        ids = {**({"authority": authority} if authority else {}),
               **(extra_ids or {})}
        (root / ".edpa" / "config" / "edpa.yaml").write_text(
            yaml.safe_dump({"ids": ids}), encoding="utf-8")
    if counters is not None:
        (root / COUNTER).write_text(
            yaml.safe_dump({"counters": counters}), encoding="utf-8")
    return root


def item(root: Path, item_id: str, dirname: str = "stories") -> Path:
    path = root / ".edpa" / "backlog" / dirname / f"{item_id}.md"
    path.write_text(f"---\nid: {item_id}\n---\n", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _no_authority_override(monkeypatch):
    monkeypatch.delenv(AUTHORITY_ENV, raising=False)


# ---------------------------------------------------------------------------
# Local mode: one sequence per clone
# ---------------------------------------------------------------------------

def test_worktrees_of_one_clone_share_the_sequence(
        world: World, alice: Path) -> None:
    """Before ADR-014 each worktree had its own lock + counter and all
    three would have minted S-1."""
    trees = [project(alice),
             project(world.worktree(alice, "wt2")),
             project(world.worktree(alice, "wt3"))]
    assert [next_id("Story", t) for t in trees] == ["S-1", "S-2", "S-3"]
    assert next_id("Story", trees[0]) == "S-4"
    # ...while the tracked counter of each tree still moves, for the hooks.
    assert yaml.safe_load((trees[1] / COUNTER).read_text())["counters"]["Story"] == 2


def test_processes_in_different_worktrees_get_unique_ids(
        world: World, alice: Path) -> None:
    trees = [project(alice), project(world.worktree(alice, "wt2")),
             project(world.worktree(alice, "wt3"))]
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import id_counter\n"
            "print(' '.join(id_counter.next_id('Story', sys.argv[2])"
            " for _ in range(4)))")
    procs = [subprocess.Popen([sys.executable, "-c", code, str(SCRIPTS), str(t)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True) for t in trees]
    ids: list[str] = []
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, err
        ids += out.split()
    assert sorted(int(i[2:]) for i in ids) == list(range(1, 13))


def test_first_use_sees_unmerged_items_in_other_worktrees_and_branches(
        world: World, alice: Path) -> None:
    project(alice)
    git(alice, "checkout", "-q", "-b", "feat/x")
    item(alice, "S-7")
    git(alice, "add", ".edpa/backlog/stories/S-7.md")
    git(alice, "commit", "-q", "-m", "feat(S-7): on a side branch")
    git(alice, "checkout", "-q", "main")
    assert not (alice / ".edpa/backlog/stories/S-7.md").exists()
    wt = project(world.worktree(alice, "wt2"))
    item(wt, "S-9")                                  # not even committed

    assert scan_known_max(alice)["Story"] == 9
    assert next_id("Story", alice) == "S-10"


def test_nested_projects_keep_separate_state(world: World, alice: Path) -> None:
    a = project(alice / "apps" / "a")
    b = project(alice / "apps" / "b")
    assert [next_id("Story", a), next_id("Story", a)] == ["S-1", "S-2"]
    assert next_id("Story", b) == "S-1"
    assert id_counter._state_dir(a) != id_counter._state_dir(b)
    assert id_counter._state_dir(a).parent == id_counter._state_dir(alice)


def test_state_lives_in_the_git_dir_not_the_checkout(
        world: World, alice: Path) -> None:
    project(alice)
    next_id("Story", alice)
    assert (alice / ".git" / "edpa" / "id_hwm.yaml").exists()
    untracked = git(alice, "status", "--porcelain", "--untracked-files=all")
    assert "id_hwm" not in untracked and "id.lock" not in untracked


def test_plain_directory_keeps_the_per_tree_behaviour(tmp_path: Path) -> None:
    project(tmp_path)
    assert id_counter._state_dir(tmp_path) is None
    assert next_id("Story", tmp_path) == "S-1"
    assert not list(tmp_path.rglob("id_hwm.yaml"))


def test_stubbed_git_is_treated_as_no_repository(
        world: World, alice: Path, monkeypatch) -> None:
    """Suites that stub ``subprocess.run`` (exit 0, empty output) must not
    make the allocator invent a state dir from an empty answer."""
    project(alice)

    class Fake:
        returncode, stdout, stderr = 0, "", ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fake())
    assert id_counter._state_dir(alice) is None
    assert next_id("Story", alice) == "S-1"
    assert not (alice / ".git" / "edpa").exists()


# ---------------------------------------------------------------------------
# resolve_authority
# ---------------------------------------------------------------------------

def test_default_is_local(world: World, alice: Path) -> None:
    project(alice)
    auth = resolve_authority(alice)
    assert (auth.mode, auth.source) == ("local", "default")
    assert (auth.remote, auth.ref) == ("origin", "refs/edpa/ids")


def test_tracked_flag_selects_remote(world: World, alice: Path) -> None:
    project(alice, authority="remote",
            extra_ids={"remote": "upstream", "ref": "refs/heads/edpa-ids"})
    auth = resolve_authority(alice)
    assert (auth.mode, auth.source) == ("remote", "config")
    assert (auth.remote, auth.ref) == ("upstream", "refs/heads/edpa-ids")


def test_env_overrides_the_tracked_flag(world: World, alice: Path,
                                        monkeypatch) -> None:
    project(alice, authority="remote")
    monkeypatch.setenv(AUTHORITY_ENV, "local")
    assert resolve_authority(alice).mode == "local"
    assert resolve_authority(alice).source == "env"


def test_a_clone_that_has_seen_a_ledger_switches_as_a_whole(
        ledger_ready: World, bob: Path) -> None:
    """The tracked flag is per branch; worktrees cut before the opt-in
    commit lack it. Discovery through the shared cache flips them all."""
    stale = project(ledger_ready.worktree(bob, "stale"))
    project(bob)
    assert resolve_authority(stale).mode == "local"

    ledger.refresh(bob)
    for tree in (bob, stale):
        auth = resolve_authority(tree)
        assert (auth.mode, auth.source) == ("remote", "discovered")


def test_explicit_local_beats_discovery(ledger_ready: World, bob: Path) -> None:
    project(bob, authority="local")
    ledger.refresh(bob)
    assert resolve_authority(bob).mode == "local"


def test_unknown_authority_value_is_an_error(world: World, alice: Path) -> None:
    project(alice, authority="github")
    with pytest.raises(IdCounterError, match="auto, local or remote"):
        resolve_authority(alice)


def test_allocator_works_without_the_ledger_module(
        world: World, alice: Path, monkeypatch) -> None:
    """Tools that vendor only id_counter.py keep working in local mode."""
    project(alice)
    monkeypatch.setattr(id_counter, "_ledger", lambda: None)
    assert resolve_authority(alice).mode == "local"
    assert next_id("Story", alice) == "S-1"

    project(alice, authority="remote")
    with pytest.raises(IdCounterError, match="_id_ledger.py is missing"):
        next_id("Story", alice)


# ---------------------------------------------------------------------------
# Remote mode
# ---------------------------------------------------------------------------

def test_remote_mode_ids_are_unique_across_clones_and_worktrees(
        ledger_ready: World, alice: Path, bob: Path) -> None:
    trees = [project(alice, authority="remote"),
             project(bob, authority="remote"),
             project(ledger_ready.worktree(bob, "bob-wt2"), authority="remote")]
    got = [next_id("Story", t) for t in (trees[0], trees[1], trees[2], trees[0])]
    assert got == ["S-11", "S-12", "S-13", "S-14"]


def test_remote_mode_records_the_claim(ledger_ready: World, alice: Path) -> None:
    project(alice, authority="remote")
    git(alice, "checkout", "-q", "-b", "feat/oauth")
    new = next_id("Story", alice, meta={
        "title": "OAuth callback", "parent": "F-3",
        "created_at": "2026-10-08T09:00:00Z"})
    rec = ledger.find_record(alice, new)
    assert rec["title"] == "OAuth callback" and rec["parent"] == "F-3"
    assert rec["created_at"] == "2026-10-08T09:00:00Z"
    assert rec["branch"] == "feat/oauth" and rec["by"] == "alice"


def test_remote_mode_never_reuses_pre_ledger_items_of_this_checkout(
        ledger_ready: World, alice: Path) -> None:
    project(alice, authority="remote")
    item(alice, "S-14")          # minted locally before the cut-over, unpushed
    assert next_id("Story", alice) == "S-15"
    assert ledger_ready.counters()["floors"]["Story"] == 14


def test_remote_mode_leaves_the_tracked_counter_alone(
        ledger_ready: World, alice: Path) -> None:
    """The file every parallel ticket branch used to conflict on."""
    project(alice, authority="remote", counters={"Story": 10})
    before = (alice / COUNTER).read_bytes()
    assert next_id("Story", alice) == "S-11"
    assert (alice / COUNTER).read_bytes() == before


def test_remote_mode_mirrors_the_number_for_an_old_vendored_hook(
        ledger_ready: World, alice: Path) -> None:
    """A worktree whose vendored engine predates the ledger still runs the
    old pre-commit check, which wants the counter to grow."""
    project(alice, authority="remote", counters={"Story": 10})
    engine = alice / ".edpa" / "engine" / "scripts"
    engine.mkdir(parents=True)
    (engine / "validate_ids.py").write_text("# pre-ledger validator\n")
    assert next_id("Story", alice) == "S-11"
    assert yaml.safe_load((alice / COUNTER).read_text())["counters"]["Story"] == 11

    (engine / "_id_ledger.py").write_text("# ledger-aware engine\n")
    assert next_id("Story", alice) == "S-12"
    assert yaml.safe_load((alice / COUNTER).read_text())["counters"]["Story"] == 11


def test_remote_mode_without_a_ledger_says_how_to_create_one(
        world: World, alice: Path) -> None:
    project(alice, authority="remote", counters={"Story": 3})
    with pytest.raises(IdCounterError, match="init-remote"):
        next_id("Story", alice)
    assert world.tip() is None                       # never bootstraps itself


def test_remote_mode_fails_closed_when_the_remote_is_unreachable(
        ledger_ready: World, alice: Path) -> None:
    """No optimistic local number: that is how V1's --local fallback grew
    two diverging ID series."""
    project(alice, authority="remote", counters={"Story": 10})
    git(alice, "remote", "set-url", "origin", str(ledger_ready.base / "gone.git"))
    before = (alice / COUNTER).read_bytes()
    with pytest.raises(IdCounterError, match="only reserved online"):
        next_id("Story", alice)
    assert (alice / COUNTER).read_bytes() == before
    assert not list((alice / ".edpa" / "backlog" / "stories").iterdir())


def test_remote_reservations_raise_the_clone_high_water_mark(
        ledger_ready: World, alice: Path, monkeypatch) -> None:
    project(alice, authority="remote")
    assert next_id("Story", alice) == "S-11"
    monkeypatch.setenv(AUTHORITY_ENV, "local")       # e.g. a tool forcing local
    assert next_id("Story", alice) == "S-12"


def test_stray_file_does_not_inflate_the_shared_sequence(
        ledger_ready: World, alice: Path) -> None:
    project(alice, authority="remote")
    item(alice, "S-9999")
    with pytest.raises(IdCounterError, match="stray file"):
        next_id("Story", alice)
    assert ledger_ready.counters()["counters"]["Story"] == 10


# ---------------------------------------------------------------------------
# seed_counters_from_fs
# ---------------------------------------------------------------------------

def test_seed_never_lowers_a_counter(tmp_path: Path) -> None:
    """A counter above the files means the highest item was deleted; a
    re-run of setup must not hand its number out again."""
    project(tmp_path, counters={"Story": 20, "Defect": 2})
    item(tmp_path, "S-5")
    item(tmp_path, "D-9", "defects")
    counters = seed_counters_from_fs(tmp_path)
    assert counters["Story"] == 20 and counters["Defect"] == 9
    assert next_id("Story", tmp_path) == "S-21"


def test_setup_does_not_resurrect_the_counter_under_remote_authority(
        ledger_ready: World, alice: Path) -> None:
    """project_setup re-seeds on every run (the release checklist runs it);
    once a remote-mode project has dropped the file it must stay gone."""
    import project_setup

    project(alice, authority="remote")
    item(alice, "S-4")
    project_setup.seed_id_counters(alice)
    assert not (alice / COUNTER).exists()

    project(alice, counters={"Story": 30})           # still fenced on main
    project_setup.seed_id_counters(alice)
    assert yaml.safe_load((alice / COUNTER).read_text())["counters"]["Story"] == 30
