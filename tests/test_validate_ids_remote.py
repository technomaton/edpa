"""validate_ids.py against a real remote: pre-push collision detection and
the remote-authority reservation check (ADR-014).

test_validate_ids.py covers ``--staged`` under the local authority in a
single repository. Everything here needs an ``origin`` and a second
developer, which is exactly the situation the hooks exist for.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

import pytest

from ledger_world import (  # noqa: F401  (fixtures are used by name)
    World, _isolated_git_config, _templates, alice, bob, git, item,
    ledger_ready, project, world,
)

import _id_ledger as ledger  # noqa: E402
import id_counter  # noqa: E402
import validate_ids  # noqa: E402

ZERO = "0" * 40


@pytest.fixture(autouse=True)
def _no_authority_override(monkeypatch):
    monkeypatch.delenv(id_counter.AUTHORITY_ENV, raising=False)


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A", ".edpa")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def run_staged(repo: Path) -> int:
    old = Path.cwd()
    try:
        os.chdir(repo)
        return validate_ids.cmd_staged(None)
    finally:
        os.chdir(old)


def run_pre_push(repo: Path, monkeypatch, branch: str = "feat") -> int:
    """Simulate ``git push origin <branch>`` of a branch the remote has
    not seen yet."""
    sha = git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(sys, "stdin", io.StringIO(
        f"refs/heads/{branch} {sha} refs/heads/{branch} {ZERO}\n"))
    old = Path.cwd()
    try:
        os.chdir(repo)
        return validate_ids.cmd_pre_push(argparse.Namespace(remote="origin"))
    finally:
        os.chdir(old)


def land_on_main(repo: Path, message: str) -> None:
    commit_all(repo, message)
    git(repo, "push", "-q", "origin", "HEAD:main")


# ---------------------------------------------------------------------------
# --pre-push: the same ID at the same path
# ---------------------------------------------------------------------------

def test_pre_push_blocks_two_stories_with_the_same_number(
        world: World, alice: Path, bob: Path, monkeypatch, capsys) -> None:
    """The standard collision. The old check only fired when the same ID
    sat in a *different* directory, i.e. never for this."""
    project(alice)
    item(alice, "S-5", title="Auth", created_at="2026-10-08T09:00:00Z")
    land_on_main(alice, "feat(S-5): Auth")

    project(bob)
    git(bob, "checkout", "-q", "-b", "feat")
    item(bob, "S-5", title="Reports", created_at="2026-10-08T09:07:00Z")
    commit_all(bob, "feat(S-5): Reports")

    assert run_pre_push(bob, monkeypatch) == 1
    err = capsys.readouterr().err
    assert "S-5 already exists on refs/remotes/origin/main as a different item" in err
    assert '"Reports"' in err and '"Auth"' in err
    assert "renumber_collisions.py" in err


def test_pre_push_accepts_this_branchs_own_item_already_merged(
        world: World, alice: Path, bob: Path, monkeypatch) -> None:
    """After a squash merge the item is on main under a different commit;
    pushing the branch again must not look like a collision."""
    project(bob)
    git(bob, "checkout", "-q", "-b", "feat")
    mine = item(bob, "S-6", title="Reports", created_at="2026-10-08T09:07:00Z")
    commit_all(bob, "feat(S-6): Reports")

    project(alice)                      # the "squash": same content, new commit
    (alice / ".edpa/backlog/stories/S-6.md").write_text(
        mine.read_text(encoding="utf-8") + "\nmerged body edit\n",
        encoding="utf-8")
    land_on_main(alice, "feat(S-6): Reports (#12)")

    assert run_pre_push(bob, monkeypatch) == 0


def test_pre_push_uses_lineage_for_items_without_created_at(
        world: World, alice: Path, bob: Path, monkeypatch) -> None:
    """Items older than the created_at stamp: the version that entered
    main must be one this branch has had."""
    project(bob)
    git(bob, "checkout", "-q", "-b", "feat")
    mine = item(bob, "S-7", title="Legacy mine")
    commit_all(bob, "feat(S-7): mine")

    project(alice)
    (alice / ".edpa/backlog/stories/S-7.md").write_bytes(mine.read_bytes())
    land_on_main(alice, "feat(S-7): mine (#13)")
    assert run_pre_push(bob, monkeypatch) == 0


def test_pre_push_blocks_unrelated_item_without_created_at(
        world: World, alice: Path, bob: Path, monkeypatch) -> None:
    project(alice)
    item(alice, "S-7", title="Legacy theirs")
    land_on_main(alice, "feat(S-7): theirs")

    project(bob)
    git(bob, "checkout", "-q", "-b", "feat")
    item(bob, "S-7", title="Legacy mine")
    commit_all(bob, "feat(S-7): mine")
    assert run_pre_push(bob, monkeypatch) == 1


def test_pre_push_still_works_when_origin_head_is_unset(
        world: World, alice: Path, bob: Path, monkeypatch, capsys) -> None:
    """Used to skip silently — a clone made with --no-checkout or an old
    git has no origin/HEAD."""
    project(alice)
    item(alice, "S-5", title="Auth", created_at="2026-10-08T09:00:00Z")
    land_on_main(alice, "feat(S-5): Auth")

    project(bob)
    git(bob, "remote", "set-head", "origin", "-d")
    git(bob, "checkout", "-q", "-b", "feat")
    item(bob, "S-5", title="Reports", created_at="2026-10-08T09:07:00Z")
    commit_all(bob, "feat(S-5): Reports")
    assert run_pre_push(bob, monkeypatch) == 1


def test_pre_push_passes_unrelated_new_items(
        world: World, alice: Path, bob: Path, monkeypatch) -> None:
    project(alice)
    item(alice, "S-5", title="Auth", created_at="2026-10-08T09:00:00Z")
    land_on_main(alice, "feat(S-5): Auth")

    project(bob)
    git(bob, "checkout", "-q", "-b", "feat")
    item(bob, "S-6", title="Reports", created_at="2026-10-08T09:07:00Z")
    commit_all(bob, "feat(S-6): Reports")
    assert run_pre_push(bob, monkeypatch) == 0


# ---------------------------------------------------------------------------
# --staged under the remote authority
# ---------------------------------------------------------------------------

mcp_server = pytest.importorskip("mcp_server")


def allocate(repo: Path, title: str = "Login button greyed out") -> str:
    """Create a Defect through the real write layer; returns its path."""
    import json
    out = mcp_server._handle_item_create(repo / ".edpa",
                                         {"type": "Defect", "title": title})
    return json.loads(out[0].text)["path"]


def test_reserved_item_passes_without_any_counter_bump(
        ledger_ready: World, alice: Path) -> None:
    project(alice, authority="remote", counters={"Defect": 0, "Story": 10})
    commit_all(alice, "chore(no-ticket): skeleton")
    git(alice, "add", allocate(alice))
    assert run_staged(alice) == 0


def test_hand_made_item_above_the_floor_is_blocked(
        ledger_ready: World, alice: Path, capsys) -> None:
    project(alice, authority="remote")
    item(alice, "S-11", title="hand made", created_at="2026-10-08T09:00:00Z")
    git(alice, "add", ".edpa/backlog/stories/S-11.md")
    assert run_staged(alice) == 1
    err = capsys.readouterr().err
    assert "S-11 has no reservation in the ID ledger" in err
    assert "up to S-10 predate it" in err


def test_item_at_or_below_the_floor_predates_the_ledger(
        ledger_ready: World, alice: Path) -> None:
    project(alice, authority="remote")
    item(alice, "S-9", title="minted before the cut-over")
    git(alice, "add", ".edpa/backlog/stories/S-9.md")
    assert run_staged(alice) == 0


def test_someone_elses_reserved_number_is_blocked(
        ledger_ready: World, alice: Path, bob: Path, capsys) -> None:
    """Bob holds S-11, unmerged. Alice's cache has never heard of it — the
    check refreshes before judging."""
    ledger.reserve(bob, "Story", "S", title="Bob's story",
                   created_at="2026-10-08T09:00:00Z")
    project(alice, authority="remote")
    item(alice, "S-11", title="Alice's story", created_at="2026-10-08T09:05:00Z")
    git(alice, "add", ".edpa/backlog/stories/S-11.md")
    assert run_staged(alice) == 1
    err = capsys.readouterr().err
    assert "S-11 is reserved in the ID ledger for a different item" in err
    assert "Bob's story" in err and "by bob" in err


def test_number_from_a_pre_reserved_block_accepts_any_item(
        ledger_ready: World, alice: Path) -> None:
    ledger.reserve(alice, "Story", "S", count=2)       # S-11, S-12: no created_at
    project(alice, authority="remote")
    item(alice, "S-12", title="written offline", created_at="2026-10-09T08:00:00Z")
    git(alice, "add", ".edpa/backlog/stories/S-12.md")
    assert run_staged(alice) == 0


def test_unreachable_ledger_warns_instead_of_blocking_the_commit(
        ledger_ready: World, alice: Path, capsys) -> None:
    """Offline at commit time: the push-time check is the one that must
    be online."""
    project(alice, authority="remote")
    ledger.refresh(alice)
    git(alice, "remote", "set-url", "origin", str(ledger_ready.base / "gone.git"))
    item(alice, "S-11", title="x", created_at="2026-10-08T09:00:00Z")
    git(alice, "add", ".edpa/backlog/stories/S-11.md")
    assert run_staged(alice) == 0
    assert "cannot reach the ID ledger" in capsys.readouterr().err


def test_merge_in_progress_skips_the_reservation_check(
        ledger_ready: World, alice: Path) -> None:
    project(alice, authority="remote")
    item(alice, "S-11", title="arrived through a merge")
    git(alice, "add", ".edpa/backlog/stories/S-11.md")
    (alice / ".git" / "MERGE_HEAD").write_text(
        git(alice, "rev-parse", "HEAD") + "\n", encoding="utf-8")
    assert run_staged(alice) == 0


def test_local_authority_keeps_the_counter_rule(
        world: World, alice: Path, capsys) -> None:
    project(alice, counters={"Story": 4})
    commit_all(alice, "chore(no-ticket): skeleton")
    item(alice, "S-5", title="no counter bump")
    git(alice, "add", ".edpa/backlog/stories/S-5.md")
    assert run_staged(alice) == 1
    assert "counter[Story]=4" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# --pre-push under the remote authority
# ---------------------------------------------------------------------------

def test_pre_push_blocks_an_unreserved_item_that_skipped_the_commit_hook(
        ledger_ready: World, alice: Path, monkeypatch, capsys) -> None:
    """--no-verify, or an outdated plugin minting from its local counter."""
    project(alice, authority="remote")
    git(alice, "checkout", "-q", "-b", "feat")
    item(alice, "S-11", title="minted locally", created_at="2026-10-08T09:00:00Z")
    commit_all(alice, "feat(S-11): minted locally")
    assert run_pre_push(alice, monkeypatch) == 1
    assert "S-11 has no reservation in the ID ledger" in capsys.readouterr().err


def test_pre_push_passes_reserved_items(
        ledger_ready: World, alice: Path, monkeypatch) -> None:
    project(alice, authority="remote")
    git(alice, "checkout", "-q", "-b", "feat")
    allocate(alice)
    commit_all(alice, "feat(D-1): Login button greyed out")
    assert run_pre_push(alice, monkeypatch) == 0
