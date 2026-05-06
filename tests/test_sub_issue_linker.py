"""Tests for plugin/edpa/scripts/_sub_issue_linker.py.

Pure-function coverage of the link helper. The actual GraphQL call
is mocked — we never hit github.com from the unit suite. Real-world
proof comes from the workflow run that creates a PR (separate
integration test category).

Run: python -m pytest tests/test_sub_issue_linker.py -v
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import _sub_issue_linker as sil  # noqa: E402


# --- link_sub_issue --------------------------------------------------------

def test_link_returns_false_for_blank_ids():
    ok, msg = sil.link_sub_issue("", "child")
    assert ok is False
    assert "missing" in msg


def test_link_returns_true_on_clean_response(monkeypatch):
    monkeypatch.setattr(sil, "_gh_graphql",
                        lambda q: {"data": {"addSubIssue": {"issue": {"id": "P"},
                                                            "subIssue": {"id": "C"}}}})
    ok, msg = sil.link_sub_issue("PARENT", "CHILD")
    assert ok is True
    assert msg == "linked"


def test_link_treats_already_linked_as_success(monkeypatch):
    monkeypatch.setattr(sil, "_gh_graphql",
                        lambda q: {"errors": [{"message": "Issue is already a sub-issue of this parent"}]})
    ok, msg = sil.link_sub_issue("PARENT", "CHILD")
    assert ok is True
    assert msg == "already linked"


def test_link_returns_false_on_real_error(monkeypatch):
    monkeypatch.setattr(sil, "_gh_graphql",
                        lambda q: {"errors": [{"message": "Could not resolve to a node"}]})
    ok, msg = sil.link_sub_issue("BAD", "CHILD")
    assert ok is False
    assert "Could not resolve" in msg


def test_link_returns_false_on_subprocess_failure(monkeypatch):
    monkeypatch.setattr(sil, "_gh_graphql", lambda q: None)
    ok, msg = sil.link_sub_issue("PARENT", "CHILD")
    assert ok is False
    assert "subprocess" in msg


# --- link_items ------------------------------------------------------------

def make_items(*pairs):
    """Build a list of items from `(id, parent)` pairs."""
    return [{"id": i, "parent": p} for i, p in pairs]


def make_map(*ids):
    """Build issue_map: each id gets `(<num>, <project_item>, <node>)`
    so that the linker actually has all three fields populated."""
    return {iid: (str(idx + 1), f"PRJ{idx}", f"NODE_{iid}")
            for idx, iid in enumerate(ids)}


def test_link_items_skips_when_no_parent(monkeypatch):
    monkeypatch.setattr(sil, "link_sub_issue",
                        lambda p, c: (True, "linked"))
    items = [{"id": "I-1", "parent": None}, {"id": "I-2"}]
    counts = sil.link_items(items, make_map("I-1", "I-2"))
    assert counts == {"linked": 0, "errors": 0, "skipped": 0}


def test_link_items_skips_when_parent_missing_from_map(monkeypatch):
    monkeypatch.setattr(sil, "link_sub_issue",
                        lambda p, c: (True, "linked"))
    items = make_items(("S-1", "F-99"))
    counts = sil.link_items(items, make_map("S-1"))   # F-99 not in map
    assert counts["skipped"] == 1
    assert counts["linked"] == 0


def test_link_items_counts_success_and_failure(monkeypatch):
    """Mixed: 2 succeed, 1 errors out."""
    def fake(parent, child):
        # Fail only when child node is NODE_S-2
        if child == "NODE_S-2":
            return False, "permission denied"
        return True, "linked"
    monkeypatch.setattr(sil, "link_sub_issue", fake)

    items = make_items(("S-1", "F-1"), ("S-2", "F-1"), ("S-3", "F-1"))
    counts = sil.link_items(items,
                            make_map("F-1", "S-1", "S-2", "S-3"))
    assert counts == {"linked": 2, "errors": 1, "skipped": 0}


def test_link_items_invokes_callbacks(monkeypatch):
    """Callers (project_setup, sync.py) plug their own loggers in."""
    monkeypatch.setattr(sil, "link_sub_issue",
                        lambda p, c: (True, "linked"))
    seen_link = []
    sil.link_items(make_items(("S-1", "F-1")),
                   make_map("F-1", "S-1"),
                   on_link=lambda cid, pid, msg: seen_link.append((cid, pid, msg)))
    assert seen_link == [("S-1", "F-1", "linked")]


def test_link_items_skip_callback_fires(monkeypatch):
    monkeypatch.setattr(sil, "link_sub_issue",
                        lambda p, c: (True, "linked"))
    seen_skip = []
    sil.link_items(make_items(("S-1", "GHOST")),
                   make_map("S-1"),
                   on_skip=lambda cid, pid, msg: seen_skip.append((cid, pid, msg)))
    assert len(seen_skip) == 1
    assert seen_skip[0][0] == "S-1"
    assert seen_skip[0][1] == "GHOST"


def test_link_items_handles_empty_node_id(monkeypatch):
    """If issue_map has the id but with blank node_id, skip — don't try."""
    monkeypatch.setattr(sil, "link_sub_issue",
                        lambda p, c: (True, "linked"))
    items = make_items(("S-1", "F-1"))
    issue_map = {
        "S-1": ("1", "PRJ1", "NODE_S-1"),
        "F-1": ("2", "PRJ2", ""),         # missing node id
    }
    counts = sil.link_items(items, issue_map)
    assert counts["skipped"] == 1
    assert counts["linked"] == 0
