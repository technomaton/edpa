"""Tests for plugin/edpa/scripts/sync_pr_contributions.py.

Exercise the deterministic event→YAML pipeline without hitting gh:
build a synthetic PR payload, feed it through ``event_to_signals`` +
``apply_signals``, assert ``evidence`` block is written/deduped.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import sync_pr_contributions as spc  # noqa: E402
from _md_frontmatter import load_md, save_md_item  # noqa: E402


@pytest.fixture
def edpa_root(tmp_path: Path) -> Path:
    root = tmp_path / ".edpa"
    (root / "config").mkdir(parents=True)
    for d in ("initiatives", "epics", "features", "stories", "defects",
              "events", "risks"):
        (root / "backlog" / d).mkdir(parents=True)
    save_md_item(
        root / "backlog" / "stories" / "S-1.md",
        {"id": "S-1", "type": "Story", "title": "Login"},
    )
    save_md_item(
        root / "backlog" / "stories" / "S-2.md",
        {"id": "S-2", "type": "Story", "title": "Signup"},
    )
    return root


def _pr_payload(number=42, title="S-1: implement login",
                body="closes S-1", author="alice", reviews=None, comments=None,
                branch="feat/login", state="closed", merged=True) -> dict:
    return {
        "number": number, "title": title, "body": body,
        "author": {"login": author},
        "reviews": reviews or [],
        "comments": comments or [],
        "headRefName": branch, "state": state, "merged": merged,
    }


# ---------------------------------------------------------------------------
# extract_item_ids
# ---------------------------------------------------------------------------

def test_extract_finds_refs_in_title_body_branch() -> None:
    pr = _pr_payload(title="S-1: login", body="depends on F-3 and S-2",
                     branch="feat/EV-5/login")
    ids = set()
    for chunk in (pr["title"], pr["body"], pr["headRefName"]):
        ids.update(spc.extract_item_ids(chunk))
    assert ids == {"S-1", "F-3", "S-2", "EV-5"}


def test_extract_dedupes_within_one_string() -> None:
    assert spc.extract_item_ids("S-1 closes S-1 again") == ["S-1"]


# ---------------------------------------------------------------------------
# event_to_signals
# ---------------------------------------------------------------------------

def test_signals_from_minimal_pr(edpa_root: Path) -> None:
    weights = spc._load_weights(edpa_root)
    """V2.1 demotion: PR with only an author (no reviews/comments) →
    sync_pr_contributions emits NOTHING. local_evidence.py owns
    commit_author attribution."""
    pr = _pr_payload()
    signals = spc.event_to_signals(pr, weights)
    assert signals == []


def test_signals_include_reviews_and_comments(edpa_root: Path) -> None:
    pr = _pr_payload(
        reviews=[{"id": "RV1", "author": {"login": "bob"}, "submittedAt": "2026-05-01T10:00:00Z"}],
        comments=[{"id": "C1", "author": {"login": "carol"}, "createdAt": "2026-05-01T11:00:00Z"}],
    )
    weights = spc._load_weights(edpa_root)
    signals = spc.event_to_signals(pr, weights)
    types = {s["signal"]["type"] for s in signals}
    # V2.1: only pr_reviewer + issue_comment (pr_author moved to local
    # commit_author).
    assert types == {"pr_reviewer", "issue_comment"}


def test_signals_explode_across_multiple_items(edpa_root: Path) -> None:
    pr = _pr_payload(
        title="S-1 + S-2 dual fix", body="",
        reviews=[{"id": "RV1", "author": {"login": "bob"},
                  "submittedAt": "2026-05-01T10:00:00Z"}],
    )
    weights = spc._load_weights(edpa_root)
    signals = spc.event_to_signals(pr, weights)
    items = {s["item_id"] for s in signals}
    assert items == {"S-1", "S-2"}


def test_signals_empty_when_no_refs(edpa_root: Path) -> None:
    pr = _pr_payload(title="generic refactor", body="no refs here",
                     branch="feat/refactor")
    weights = spc._load_weights(edpa_root)
    assert spc.event_to_signals(pr, weights) == []


# ---------------------------------------------------------------------------
# apply_signals + dedupe
# ---------------------------------------------------------------------------

def test_apply_writes_evidence_block(edpa_root: Path) -> None:
    pr = _pr_payload(reviews=[
        {"id": "RV1", "author": {"login": "bob"},
         "submittedAt": "2026-05-01T10:00:00Z"},
    ])
    weights = spc._load_weights(edpa_root)
    signals = spc.event_to_signals(pr, weights)
    summary = spc.apply_signals(edpa_root, signals)

    assert summary == {"S-1": 1}
    data = load_md(edpa_root / "backlog" / "stories" / "S-1.md")
    assert len(data["evidence"]) == 1
    sig = data["evidence"][0]
    assert sig["type"] == "pr_reviewer"
    assert sig["person"] == "bob"
    assert sig["ref"] == "PR#42:review:RV1"


def test_apply_is_idempotent(edpa_root: Path) -> None:
    pr = _pr_payload(reviews=[
        {"id": "RV1", "author": {"login": "bob"},
         "submittedAt": "2026-05-01T10:00:00Z"},
    ])
    weights = spc._load_weights(edpa_root)
    signals = spc.event_to_signals(pr, weights)
    spc.apply_signals(edpa_root, signals)
    spc.apply_signals(edpa_root, signals)

    data = load_md(edpa_root / "backlog" / "stories" / "S-1.md")
    assert len(data["evidence"]) == 1, "Re-applying same signals should dedupe"


def test_apply_merges_new_signals_into_existing(edpa_root: Path) -> None:
    # First apply: PR with a single reviewer
    pr1 = _pr_payload(
        number=1, title="S-1: first", author="alice",
        reviews=[{"id": "RV1", "author": {"login": "bob"},
                  "submittedAt": "2026-05-01T10:00:00Z"}],
    )
    weights = spc._load_weights(edpa_root)
    spc.apply_signals(edpa_root, spc.event_to_signals(pr1, weights))

    # Second apply: different PR adds another review
    pr2 = _pr_payload(
        number=2, title="S-1: review fix", author="bob",
        reviews=[{"id": "RV2", "author": {"login": "carol"},
                  "submittedAt": "2026-05-02T10:00:00Z"}],
    )
    spc.apply_signals(edpa_root, spc.event_to_signals(pr2, weights))

    data = load_md(edpa_root / "backlog" / "stories" / "S-1.md")
    refs = {s["ref"] for s in data["evidence"]}
    assert refs == {"PR#1:review:RV1", "PR#2:review:RV2"}


def test_apply_skips_unknown_items(edpa_root: Path) -> None:
    """A PR referencing F-99 (doesn't exist) → no-op for that item."""
    pr = _pr_payload(title="F-99: ghost feature", body="")
    weights = spc._load_weights(edpa_root)
    signals = spc.event_to_signals(pr, weights)
    summary = spc.apply_signals(edpa_root, signals)
    assert summary == {}  # F-99 not in backlog


# ---------------------------------------------------------------------------
# _load_weights override
# ---------------------------------------------------------------------------

def test_weights_overridable_via_heuristics_file(edpa_root: Path) -> None:
    (edpa_root / "config" / "cw_heuristics.yaml").write_text(yaml.safe_dump({
        "signal_weights": {"pr_reviewer": 9.99},
    }))
    weights = spc._load_weights(edpa_root)
    assert weights["pr_reviewer"] == 9.99
    # Other defaults preserved
    assert weights["issue_comment"] == 1.14


# ---------------------------------------------------------------------------
# D-33: out-of-iteration gate for GH-side signals
# ---------------------------------------------------------------------------

def _edpa_with_iterations(tmp_path: Path, item_iteration: str = "PI-2026-1.1") -> Path:
    root = tmp_path / ".edpa"
    (root / "config").mkdir(parents=True)
    for d in ("features", "stories", "defects"):
        (root / "backlog" / d).mkdir(parents=True)
    it = root / "iterations"
    it.mkdir()
    (it / "PI-2026-1.1.yaml").write_text(
        "iteration:\n  id: PI-2026-1.1\n  start_date: 2026-04-01\n  end_date: 2026-04-30\n",
        encoding="utf-8")
    (it / "PI-2026-3.1.yaml").write_text(
        "iteration:\n  id: PI-2026-3.1\n  start_date: 2026-06-01\n  end_date: 2026-06-30\n",
        encoding="utf-8")
    save_md_item(root / "backlog" / "stories" / "S-1.md",
                 {"id": "S-1", "type": "Story", "title": "Login",
                  "iteration": item_iteration})
    return root


def test_apply_gates_review_outside_item_iteration(tmp_path: Path) -> None:
    """D-33: a review whose submittedAt lands outside the host item's iteration
    is written to evidence[] but neutralised to weight 0 + out_of_iteration
    (raw_weight kept) — the GH-side mirror of the commit-side D-29 gate."""
    edpa = _edpa_with_iterations(tmp_path)  # S-1 in closed PI-2026-1.1 (April)
    pr = _pr_payload(title="S-1: late review", body="", reviews=[
        {"id": "RV1", "author": {"login": "bob"},
         "submittedAt": "2026-06-18T10:00:00Z"}])  # June -> foreign to 1.1
    weights = spc._load_weights(edpa)
    spc.apply_signals(edpa, spc.event_to_signals(pr, weights))
    rv = [s for s in load_md(edpa / "backlog" / "stories" / "S-1.md")["evidence"]
          if s["type"] == "pr_reviewer"]
    assert rv and rv[0]["weight"] == 0
    assert "out_of_iteration" in rv[0]["tags"]
    assert rv[0]["raw_weight"] > 0


def test_apply_keeps_review_inside_item_iteration(tmp_path: Path) -> None:
    """D-33: a review inside the item's own iteration window keeps full weight."""
    edpa = _edpa_with_iterations(tmp_path)  # S-1 in PI-2026-1.1 (April)
    pr = _pr_payload(title="S-1: review", body="", reviews=[
        {"id": "RV1", "author": {"login": "bob"},
         "submittedAt": "2026-04-10T10:00:00Z"}])  # April -> own window
    weights = spc._load_weights(edpa)
    spc.apply_signals(edpa, spc.event_to_signals(pr, weights))
    rv = [s for s in load_md(edpa / "backlog" / "stories" / "S-1.md")["evidence"]
          if s["type"] == "pr_reviewer"]
    assert rv and rv[0]["weight"] > 0
    assert "out_of_iteration" not in rv[0].get("tags", [])


def test_gate_keeps_pr_signal_on_unassigned_item(tmp_path: Path) -> None:
    """D-33: an item with no iteration: can't prove overflow -> signal kept
    (mirrors the D-28/D-29 blank-iteration rule)."""
    edpa = _edpa_with_iterations(tmp_path)
    item = {"type": "Story"}  # no iteration
    sigs = [{"type": "pr_reviewer", "weight": 2.25,
             "at": "2026-06-18T10:00:00+00:00"}]
    spc._gate_out_of_iteration(
        edpa, item, edpa / "backlog" / "stories" / "S-1.md", sigs)
    assert sigs[0]["weight"] == 2.25
    assert "out_of_iteration" not in sigs[0].get("tags", [])
