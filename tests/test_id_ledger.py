"""Tests for plugin/edpa/scripts/_id_ledger.py.

Hermetic: a local bare repository plays ``origin`` and several
independent clones (plus linked worktrees) play the developers. Covers
the compare-and-swap contract — exactly one winner per round, losers
retry with the next number — and every way the remote can disagree with
what a clone remembers (refusal, rewind, deletion, divergence).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ledger_world import (  # noqa: F401  (fixtures are used by name)
    SCRIPTS, World, _isolated_git_config, _templates, alice, bob, git,
    ledger_ready, world,
)

import _id_ledger as ledger  # noqa: E402
from _id_ledger import (  # noqa: E402
    CACHE_REF, DEFAULT_REF, LedgerError, LedgerMissing, LedgerRejected,
    LedgerUnavailable,
)


def take(repo: Path, item_type: str = "Story", prefix: str = "S", **kw) -> int:
    return ledger.reserve(repo, item_type, prefix, **kw).numbers[0]


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def test_missing_ledger_is_an_explicit_error(world: World, alice: Path) -> None:
    """Allocation never bootstraps on its own — a deleted ledger or a fork
    would otherwise be silently re-seeded from partial knowledge."""
    with pytest.raises(LedgerMissing, match="init-remote"):
        take(alice)
    assert world.tip() is None


def test_bootstrap_seeds_counters_and_floors(world: World, alice: Path) -> None:
    ledger.raise_floors(alice, {"Story": 10, "Defect": 4, "Event": 0},
                        create=True)
    state = world.counters()
    assert state["counters"] == {"Defect": 4, "Story": 10}
    assert state["floors"] == {"Defect": 4, "Story": 10}
    assert take(alice) == 11
    assert ledger.cached_state(alice) == ({"Defect": 4, "Story": 11},
                                          {"Defect": 4, "Story": 10})


def test_bootstrap_of_an_empty_project_still_creates_the_ref(
        world: World, alice: Path) -> None:
    ledger.raise_floors(alice, {}, create=True)
    assert world.tip() is not None
    assert take(alice) == 1


def test_raise_floors_is_idempotent_and_never_lowers(
        ledger_ready: World, alice: Path, bob: Path) -> None:
    before = ledger_ready.tip()
    res = ledger.raise_floors(bob, {"Story": 3}, create=True)
    assert res.numbers == [] and ledger_ready.tip() == before   # no commit

    ledger.raise_floors(bob, {"Story": 25, "Feature": 7})
    state = ledger_ready.counters()
    assert state["counters"] == {"Feature": 7, "Story": 25}
    assert state["floors"] == {"Feature": 7, "Story": 25}
    assert take(alice) == 26


# ---------------------------------------------------------------------------
# The contract: unique numbers across clones
# ---------------------------------------------------------------------------

def test_two_clones_never_get_the_same_number(
        ledger_ready: World, alice: Path, bob: Path) -> None:
    got = [take(alice), take(bob), take(bob), take(alice), take(bob)]
    assert got == [11, 12, 13, 14, 15]


def test_per_type_counters_are_independent(
        ledger_ready: World, alice: Path, bob: Path) -> None:
    assert take(alice, "Defect", "D") == 1
    assert take(bob, "Story", "S") == 11
    assert take(bob, "Defect", "D") == 2
    assert ledger_ready.counters()["counters"] == {"Defect": 2, "Story": 11}


def test_reserve_block_is_consecutive(
        ledger_ready: World, alice: Path, bob: Path) -> None:
    res = ledger.reserve(alice, "Story", "S", count=3)
    assert res.numbers == [11, 12, 13]
    assert take(bob) == 14


def test_lost_race_retries_with_the_next_number(
        ledger_ready: World, alice: Path, bob: Path, monkeypatch) -> None:
    """Bob lands a reservation between Alice's read and Alice's push."""
    real_push = ledger._push
    state = {"raced": False}

    def racing_push(repo, remote, ref, new, expect):
        if not state["raced"]:
            state["raced"] = True
            assert take(bob) == 11
        return real_push(repo, remote, ref, new, expect)

    monkeypatch.setattr(ledger, "_push", racing_push)
    res = ledger.reserve(alice, "Story", "S")
    assert res.numbers == [12]
    assert res.attempts == 2


def test_lost_acknowledgement_does_not_burn_a_second_number(
        ledger_ready: World, alice: Path, monkeypatch) -> None:
    """The push lands but the client never hears back (timeout): the
    reservation must be recognised as ours, not retried."""
    real_push = ledger._push

    def deaf_push(repo, remote, ref, new, expect):
        real_push(repo, remote, ref, new, expect)
        return "", "simulated: connection dropped after the server applied it"

    monkeypatch.setattr(ledger, "_push", deaf_push)
    assert take(alice) == 11
    monkeypatch.setattr(ledger, "_push", real_push)
    assert take(alice) == 12


def test_identical_commit_is_not_a_second_win(
        ledger_ready: World, alice: Path) -> None:
    """Two worktrees of one person can build the same commit; git answers
    the second push with ``=`` (up to date). That must not count."""
    tip = ledger_ready.tip()
    counters, floors = ledger.cached_state(alice)
    new = ledger._commit(alice, [tip], {**counters, "Story": 11}, floors,
                         "alloc S-11: same text\n")
    first, _ = ledger._push(alice, "origin", DEFAULT_REF, new, tip)
    second, _ = ledger._push(alice, "origin", DEFAULT_REF, new, tip)
    assert first == " "
    assert second not in (" ", "*")


def test_every_reservation_message_is_unique() -> None:
    a = ledger._message("alloc S-1: x", [("EDPA-Id", "S-1")])
    b = ledger._message("alloc S-1: x", [("EDPA-Id", "S-1")])
    assert a != b and "EDPA-Nonce: " in a


def test_concurrent_processes_across_clones_and_worktrees(
        ledger_ready: World, alice: Path, bob: Path) -> None:
    """4 processes in 3 working trees of 2 clones — no duplicates, no gaps.

    (Stress at scale — 16 processes, 128 reservations, plus a run against
    GitHub — was done once by hand when the protocol was designed.)"""
    wt = ledger_ready.worktree(alice, "alice-wt2")
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import _id_ledger as l\n"
        "print(' '.join(str(l.reserve(sys.argv[2], 'Story', 'S').numbers[0])"
        " for _ in range(2)))"
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", code, str(SCRIPTS), str(repo)],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8")
        for repo in (alice, wt, bob, bob)
    ]
    numbers: list[int] = []
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, err
        numbers += [int(x) for x in out.split()]
    assert sorted(numbers) == list(range(11, 19))


# ---------------------------------------------------------------------------
# Local floor
# ---------------------------------------------------------------------------

def test_local_maximum_above_the_ledger_becomes_the_floor(
        ledger_ready: World, alice: Path) -> None:
    """Pre-ledger items this clone holds are never handed out again, and
    are recorded as record-less (legacy) numbers."""
    assert take(alice, floor=15) == 16
    state = ledger_ready.counters()
    assert state["counters"]["Story"] == 16
    assert state["floors"]["Story"] == 15


def test_local_maximum_below_the_ledger_changes_nothing(
        ledger_ready: World, alice: Path) -> None:
    assert take(alice, floor=4) == 11
    assert ledger_ready.counters()["floors"]["Story"] == 10


def test_stray_local_maximum_is_refused(
        ledger_ready: World, alice: Path) -> None:
    before = ledger_ready.tip()
    with pytest.raises(LedgerError, match="stray file"):
        take(alice, floor=9999)
    assert ledger_ready.tip() == before
    assert take(alice, floor=9999, max_jump=None) == 10000


# ---------------------------------------------------------------------------
# The remote disagrees
# ---------------------------------------------------------------------------

def test_unreachable_remote_is_reported_as_unavailable(
        ledger_ready: World, alice: Path) -> None:
    git(alice, "remote", "set-url", "origin",
        str(ledger_ready.base / "gone.git"))
    with pytest.raises(LedgerUnavailable, match="cannot read the ID ledger"):
        take(alice)


def test_server_refusal_is_not_retried_as_a_race(
        ledger_ready: World, alice: Path) -> None:
    hook = ledger_ready.origin / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'denied: protected ref' >&2\nexit 1\n",
                    encoding="utf-8")
    hook.chmod(0o755)
    before = ledger_ready.tip()
    with pytest.raises(LedgerRejected, match="denied: protected ref"):
        take(alice)
    assert ledger_ready.tip() == before


def test_rewound_remote_is_fast_forwarded_from_the_cache(
        ledger_ready: World, alice: Path, bob: Path) -> None:
    old = ledger_ready.tip()
    assert [take(alice), take(alice)] == [11, 12]
    git(ledger_ready.origin, "update-ref", DEFAULT_REF, old)   # rewind

    res = ledger.reserve(alice, "Story", "S")
    assert res.numbers == [13]
    assert any("behind" in n for n in res.notes)
    assert take(bob) == 14                                     # healed for all


def test_deleted_remote_ref_is_restored_from_the_cache(
        ledger_ready: World, alice: Path, bob: Path) -> None:
    assert take(alice) == 11
    git(ledger_ready.origin, "update-ref", "-d", DEFAULT_REF)

    res = ledger.reserve(alice, "Story", "S")
    assert res.numbers == [12]
    assert any("restored" in n for n in res.notes)
    assert take(bob) == 13


def test_diverged_histories_are_merged_by_max(
        ledger_ready: World, alice: Path, bob: Path) -> None:
    assert [take(alice), take(alice)] == [11, 12]
    # Somebody force-pushes an unrelated ledger with a different shape.
    rogue = ledger._commit(bob, [], {"Story": 5, "Defect": 40}, {"Defect": 40},
                           "rogue ledger\n")
    git(bob, "push", "-q", "--force", "origin", f"{rogue}:{DEFAULT_REF}")

    res = ledger.reserve(alice, "Story", "S")
    assert res.numbers == [13]
    assert any("diverged" in n for n in res.notes)
    state = ledger_ready.counters()
    assert state["counters"] == {"Defect": 40, "Story": 13}
    assert state["floors"] == {"Defect": 40, "Story": 10}
    parents = git(ledger_ready.origin, "rev-list", "--parents", "-1",
                  DEFAULT_REF).split()[1:]
    assert len(parents) == 2


def test_refresh_never_moves_the_cache_backwards(
        ledger_ready: World, alice: Path) -> None:
    old = ledger_ready.tip()
    assert take(alice) == 11
    newest = git(alice, "rev-parse", CACHE_REF)
    git(ledger_ready.origin, "update-ref", DEFAULT_REF, old)

    assert ledger.refresh(alice) is True
    assert git(alice, "rev-parse", CACHE_REF) == newest


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

def test_missing_identity_is_reported_before_anything_is_pushed(
        ledger_ready: World, alice: Path, monkeypatch) -> None:
    git(alice, "config", "--unset", "user.name")
    git(alice, "config", "--unset", "user.email")
    git(alice, "config", "user.useConfigOnly", "true")
    for var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME",
                "GIT_COMMITTER_EMAIL", "EMAIL"):
        monkeypatch.delenv(var, raising=False)
    before = ledger_ready.tip()
    with pytest.raises(LedgerError, match="user.name / user.email"):
        take(alice)
    assert ledger_ready.tip() == before


def test_failing_pre_push_hook_does_not_block_a_reservation(
        ledger_ready: World, alice: Path) -> None:
    """Consumers run their test suite in pre-push; the tooling push of one
    metadata commit must not trigger (or be blocked by) it."""
    hook = alice / ".git" / "hooks" / "pre-push"
    hook.write_text("#!/bin/sh\necho 'running the test suite' >&2\nexit 1\n",
                    encoding="utf-8")
    hook.chmod(0o755)
    assert take(alice) == 11


def test_git_never_inherits_stdin(ledger_ready: World, alice: Path,
                                  monkeypatch) -> None:
    """The MCP server's stdin is its JSON-RPC stream."""
    real_popen = subprocess.Popen
    seen: list = []

    def spy(*args, **kw):
        seen.append(kw.get("stdin"))
        return real_popen(*args, **kw)

    monkeypatch.setattr(ledger.subprocess, "Popen", spy)
    assert take(alice) == 11
    assert seen and all(s in (subprocess.PIPE, subprocess.DEVNULL) for s in seen)


def test_fetch_head_of_the_worktree_is_left_alone(
        ledger_ready: World, alice: Path) -> None:
    if not ledger._fetch_extra:
        pytest.skip("git too old for --no-write-fetch-head")
    git(alice, "fetch", "-q", "origin", "main")
    fetch_head = alice / ".git" / "FETCH_HEAD"
    before = fetch_head.read_text(encoding="utf-8")
    assert take(alice) == 11
    assert fetch_head.read_text(encoding="utf-8") == before


def test_working_tree_and_index_are_untouched(
        ledger_ready: World, alice: Path) -> None:
    (alice / "wip.txt").write_text("in progress\n", encoding="utf-8")
    git(alice, "add", "wip.txt")
    status = git(alice, "status", "--porcelain")
    head = git(alice, "rev-parse", "HEAD")
    assert take(alice) == 11
    assert git(alice, "status", "--porcelain") == status
    assert git(alice, "rev-parse", "HEAD") == head


def test_branch_hosted_ledger_behaves_the_same(
        world: World, alice: Path, bob: Path) -> None:
    """Forges that refuse custom namespaces: same code, a branch as the ref."""
    ref = "refs/heads/edpa-ids"
    ledger.raise_floors(alice, {"Story": 2}, create=True, ref=ref)
    got = [ledger.reserve(r, "Story", "S", ref=ref).numbers[0]
           for r in (alice, bob, alice)]
    assert got == [3, 4, 5]
    assert world.counters(ref)["counters"] == {"Story": 5}
    assert git(alice, "branch", "--list", "edpa-ids") == ""    # no local branch


def test_invalid_remote_or_ref_never_reaches_git(alice: Path) -> None:
    with pytest.raises(LedgerError, match="invalid ledger remote"):
        ledger.reserve(alice, "Story", "S", remote="--upload-pack=evil")
    for bad in ("refs/../heads/main", "edpa/ids", "refs/edpa", "refs/x/y.lock",
                "refs/-x/ids"):
        with pytest.raises(LedgerError, match="invalid ledger ref"):
            ledger.reserve(alice, "Story", "S", ref=bad)


# ---------------------------------------------------------------------------
# Discovery + audit trail
# ---------------------------------------------------------------------------

def test_refresh_lets_a_fresh_clone_discover_the_ledger(
        ledger_ready: World, bob: Path) -> None:
    assert ledger.known_locally(bob) is False
    assert ledger.cached_state(bob) is None
    assert ledger.refresh(bob) is True
    assert ledger.known_locally(bob) is True
    assert ledger.cached_state(bob) == ({"Story": 10}, {"Story": 10})


def test_refresh_without_any_ledger(world: World, alice: Path) -> None:
    assert ledger.refresh(alice) is False
    assert ledger.known_locally(alice) is False


def test_audit_trail_records_who_reserved_what(
        ledger_ready: World, alice: Path, bob: Path) -> None:
    ledger.reserve(alice, "Story", "S", title="OAuth callback", parent="F-3",
                   branch="feat/oauth", created_at="2026-10-08T09:00:00Z")
    ledger.reserve(bob, "Story", "S", count=2)
    ledger.refresh(alice)

    newest, older = ledger.entries(alice, limit=2)
    assert newest["ids"] == ["S-12", "S-13"] and newest["by"] == "bob"
    assert "created_at" not in newest
    assert older["ids"] == ["S-11"] and older["by"] == "alice"
    assert older["title"] == "OAuth callback" and older["parent"] == "F-3"
    assert older["branch"] == "feat/oauth"
    assert older["created_at"] == "2026-10-08T09:00:00Z"

    rec = ledger.find_record(alice, "S-11")
    assert rec is not None and rec["created_at"] == "2026-10-08T09:00:00Z"
    assert ledger.find_record(alice, "S-13")["ids"] == ["S-12", "S-13"]
    assert ledger.find_record(alice, "S-1") is None      # no prefix match
    assert ledger.find_record(alice, "S-99") is None
    assert ledger.find_record(alice, "not an id") is None


def test_free_text_title_cannot_forge_trailers(
        ledger_ready: World, alice: Path) -> None:
    ledger.reserve(alice, "Story", "S",
                   title="innocent\n\nEDPA-Id: S-999\nEDPA-Created-At: forged")
    assert ledger.find_record(alice, "S-999") is None
    rec = ledger.find_record(alice, "S-11")
    assert rec["ids"] == ["S-11"] and "created_at" not in rec


def test_forget_drops_only_the_local_cache(
        ledger_ready: World, alice: Path) -> None:
    assert take(alice) == 11
    tip = ledger_ready.tip()
    ledger.forget(alice)
    assert ledger.known_locally(alice) is False
    assert ledger_ready.tip() == tip
    assert take(alice) == 12
