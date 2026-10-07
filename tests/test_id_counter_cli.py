"""Tests for the ``id_counter.py`` command line: bootstrap of the remote ID
ledger, scripted allocation, the offline pool, and the doctor."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
import yaml

from ledger_world import (  # noqa: F401  (fixtures are used by name)
    COUNTER, World, _isolated_git_config, _templates, alice, bob, git, item,
    ledger_ready, project, world,
)

import _id_ledger as ledger  # noqa: E402
import id_counter  # noqa: E402
from id_counter import IdCounterError, next_id  # noqa: E402


@pytest.fixture(autouse=True)
def _no_authority_override(monkeypatch):
    monkeypatch.delenv(id_counter.AUTHORITY_ENV, raising=False)


def cli(root: Path, *args: str) -> int:
    return id_counter.main(["--root", str(root), *args])


# ---------------------------------------------------------------------------
# init-remote
# ---------------------------------------------------------------------------

def _spread_out_project(world: World, alice: Path, bob: Path) -> None:
    """IDs scattered the way a real cut-over finds them: main, a remote
    branch this clone never fetched, another worktree's uncommitted file."""
    project(alice, counters={"Story": 3, "Defect": 1})
    item(alice, "S-3")
    item(alice, "D-1", "defects")
    git(alice, "add", "-A", ".edpa")
    git(alice, "commit", "-q", "-m", "seed")
    git(alice, "push", "-q", "origin", "HEAD:main")

    git(bob, "pull", "-q", "origin", "main")
    git(bob, "checkout", "-q", "-b", "feat/y")
    item(bob, "S-8")
    git(bob, "add", "-A", ".edpa")
    git(bob, "commit", "-q", "-m", "feat(S-8): on bob's branch")
    git(bob, "push", "-q", "origin", "feat/y")

    wt = world.worktree(alice, "alice-wt2")
    item(wt, "S-5")                      # uncommitted, in a sibling worktree


def test_init_remote_seeds_from_everything_this_clone_can_reach(
        world: World, alice: Path, bob: Path, capsys) -> None:
    _spread_out_project(world, alice, bob)
    assert cli(alice, "init-remote", "--headroom", "5", "--apply") == 0
    out = capsys.readouterr().out
    assert "S-8" in out and "floor S-13" in out and "first new ID S-14" in out

    state = world.counters()
    assert state["floors"] == {"Defect": 6, "Story": 13}
    assert state["counters"] == {"Defect": 6, "Story": 13}
    # Types without any item get no headroom: the first Risk is R-1.
    assert "Risk" not in state["floors"]
    # The private scan namespace is cleaned up again.
    assert git(alice, "for-each-ref", "refs/edpa/scan") == ""
    # ...and the whole clone is switched, without any tracked flag yet.
    assert next_id("Story", alice) == "S-14"
    assert next_id("Risk", alice) == "R-1"


def test_init_remote_twice_changes_nothing(
        world: World, alice: Path, bob: Path) -> None:
    _spread_out_project(world, alice, bob)
    assert cli(alice, "init-remote", "--headroom", "5", "--apply") == 0
    tip = world.tip()
    assert cli(alice, "init-remote", "--headroom", "5", "--apply") == 0
    assert world.tip() == tip


def test_init_remote_asks_before_writing(
        world: World, alice: Path, monkeypatch, capsys) -> None:
    project(alice)
    item(alice, "S-3")
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))       # EOF = no answer
    assert cli(alice, "init-remote") == 1
    assert "nothing was written" in capsys.readouterr().out
    assert world.tip() is None


def test_init_remote_refuses_to_guess_when_branches_cannot_be_fetched(
        world: World, alice: Path, capsys) -> None:
    project(alice)
    item(alice, "S-3")
    git(alice, "remote", "set-url", "origin", str(world.base / "gone.git"))
    assert cli(alice, "init-remote", "--apply") == 1
    assert "the floor would be a guess" in capsys.readouterr().err


def test_write_config_prepares_the_opt_in_without_committing(
        world: World, alice: Path) -> None:
    project(alice, counters={"Story": 3})
    cfg = alice / ".edpa" / "config" / "edpa.yaml"
    cfg.write_text("# my project\nproject:\n  name: Demo   # keep me\n",
                   encoding="utf-8")
    item(alice, "S-3")
    git(alice, "add", "-A", ".edpa")
    git(alice, "commit", "-q", "-m", "seed")
    head = git(alice, "rev-parse", "HEAD")

    assert cli(alice, "init-remote", "--headroom", "10", "--apply",
               "--write-config") == 0
    text = cfg.read_text(encoding="utf-8")
    assert text.startswith("# my project\nproject:\n  name: Demo   # keep me\n")
    assert yaml.safe_load(text)["ids"] == {"authority": "remote"}
    # Fenced, not deleted: old vendored hooks still read it.
    assert yaml.safe_load((alice / COUNTER).read_text())["counters"]["Story"] == 13
    assert git(alice, "rev-parse", "HEAD") == head             # not committed
    assert id_counter.resolve_authority(alice).source == "config"


# ---------------------------------------------------------------------------
# next / reserve
# ---------------------------------------------------------------------------

def test_next_prints_one_id(ledger_ready: World, alice: Path, capsys) -> None:
    project(alice, authority="remote")
    assert cli(alice, "next", "--type", "Story", "--title", "From a script") == 0
    assert capsys.readouterr().out.strip() == "S-11"
    assert ledger.find_record(alice, "S-11")["title"] == "From a script"


def test_next_works_under_the_local_authority(tmp_path: Path, capsys) -> None:
    project(tmp_path)
    assert cli(tmp_path, "next", "--type", "Defect") == 0
    assert capsys.readouterr().out.strip() == "D-1"


def test_reserved_block_is_used_only_when_the_remote_is_unreachable(
        ledger_ready: World, alice: Path, capsys) -> None:
    """Reserve-then-use cannot diverge from the ledger; that is the whole
    offline story — there is no optimistic local number."""
    project(alice, authority="remote")
    assert cli(alice, "reserve", "--type", "Story", "--count", "2") == 0
    assert "S-11..S-12" in capsys.readouterr().out
    assert next_id("Story", alice) == "S-13"          # online: pool untouched

    git(alice, "remote", "set-url", "origin", str(ledger_ready.base / "gone.git"))
    assert [next_id("Story", alice), next_id("Story", alice)] == ["S-11", "S-12"]
    assert "using pre-reserved S-12 (0 left" in capsys.readouterr().err
    with pytest.raises(IdCounterError, match="only reserved online"):
        next_id("Story", alice)


def test_reserve_makes_no_sense_under_the_local_authority(
        world: World, alice: Path, capsys) -> None:
    project(alice)
    assert cli(alice, "reserve", "--type", "Story", "--count", "2") == 1
    assert "only be pre-reserved under the remote ID authority" in \
        capsys.readouterr().err


# ---------------------------------------------------------------------------
# status / doctor
# ---------------------------------------------------------------------------

def test_status_reports_every_layer(ledger_ready: World, alice: Path, capsys) -> None:
    project(alice, authority="remote", counters={"Story": 10})
    item(alice, "S-4")
    next_id("Story", alice)
    assert cli(alice, "status", "--json") == 0
    info = json.loads(capsys.readouterr().out)
    assert info["authority"] == "remote" and info["source"] == "config"
    assert info["ledger"] == {"counters": {"Story": 11}, "floors": {"Story": 10}}
    assert info["local"]["Story"] == {"files": 4, "tracked": 10, "clone": 11}

    assert cli(alice, "status") == 0
    assert "ID authority: remote" in capsys.readouterr().out


def test_status_refresh_discovers_a_ledger(
        ledger_ready: World, bob: Path, capsys) -> None:
    project(bob)
    assert cli(bob, "status", "--json") == 0
    assert json.loads(capsys.readouterr().out)["authority"] == "local"
    assert cli(bob, "status", "--json", "--refresh") == 0
    info = json.loads(capsys.readouterr().out)
    assert info["authority"] == "remote" and info["source"] == "discovered"


def test_doctor_finds_and_adopts_unreserved_items(
        ledger_ready: World, alice: Path, capsys) -> None:
    project(alice, authority="remote")
    assert cli(alice, "doctor") == 0

    item(alice, "S-12")              # minted by an outdated session, unpushed
    assert cli(alice, "doctor") == 1
    out = capsys.readouterr().out
    assert "1 item(s) above the floor without a reservation: S-12" in out
    assert "doctor --raise" in out

    assert cli(alice, "doctor", "--raise") == 0
    assert ledger_ready.counters()["floors"]["Story"] == 12
    assert cli(alice, "doctor") == 0
    assert next_id("Story", alice) == "S-13"


def test_doctor_rebuild_is_the_documented_recovery(tmp_path: Path, capsys) -> None:
    """docs/dev-collisions.md pointed at this command before it existed."""
    project(tmp_path)
    item(tmp_path, "S-7")
    assert cli(tmp_path, "doctor", "--rebuild") == 0
    assert "Story=7" in capsys.readouterr().out
    assert yaml.safe_load((tmp_path / COUNTER).read_text())["counters"]["Story"] == 7


def test_doctor_forget_drops_only_the_local_cache(
        ledger_ready: World, alice: Path) -> None:
    project(alice)
    ledger.refresh(alice)
    assert cli(alice, "doctor", "--forget") == 0
    assert ledger.known_locally(alice) is False
    assert ledger_ready.tip() is not None


def test_cli_outside_a_project(tmp_path: Path, capsys) -> None:
    assert cli(tmp_path, "status") == 2
    assert "no .edpa/ directory" in capsys.readouterr().err
