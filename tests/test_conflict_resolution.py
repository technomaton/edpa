"""Unit tests for sync.py resolve_conflicts pure function (Gap 3).

These tests are isolated from real GitHub — they verify only the pure
'pick winner per (item, field) under strategy' logic. The full apply path
is exercised in test_e2e_sync.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin/edpa/scripts"))
import sync


def _entry(item, field, source, new, ts):
    return {"item": item, "field": field, "source": source,
            "new": new, "ts": ts}


def test_report_strategy_returns_no_winner():
    gh = {"S-1": [_entry("S-1", "status", "github", "Done",  "2026-05-04T12:00:00Z")]}
    git = {"S-1": [_entry("S-1", "status", "git",    "Implementing", "2026-05-04T13:00:00Z")]}
    plan = sync.resolve_conflicts(gh, git, "report")
    assert len(plan) == 1
    assert plan[0]["winner"] is None
    assert plan[0]["reason"] == "manual"


def test_local_wins_picks_local_value_regardless_of_ts():
    gh =  {"S-1": [_entry("S-1", "js", "github", 8, "2026-05-04T15:00:00Z")]}  # newer
    git = {"S-1": [_entry("S-1", "js", "git",    5, "2026-05-04T10:00:00Z")]}  # older
    plan = sync.resolve_conflicts(gh, git, "local-wins")
    assert plan[0]["winner"] == "local"
    assert plan[0]["value"] == 5


def test_remote_wins_picks_github_value_regardless_of_ts():
    gh =  {"S-1": [_entry("S-1", "js", "github", 8, "2026-05-04T10:00:00Z")]}  # older
    git = {"S-1": [_entry("S-1", "js", "git",    5, "2026-05-04T15:00:00Z")]}  # newer
    plan = sync.resolve_conflicts(gh, git, "remote-wins")
    assert plan[0]["winner"] == "remote"
    assert plan[0]["value"] == 8


def test_last_write_wins_picks_newest_timestamp():
    gh =  {"S-1": [_entry("S-1", "status", "github", "Done", "2026-05-04T15:00:00Z")]}
    git = {"S-1": [_entry("S-1", "status", "git",    "Implementing", "2026-05-04T10:00:00Z")]}
    plan = sync.resolve_conflicts(gh, git, "last-write-wins")
    assert plan[0]["winner"] == "remote"
    assert plan[0]["value"] == "Done"

    # Reverse: git newer
    gh2 =  {"S-1": [_entry("S-1", "status", "github", "Done", "2026-05-04T10:00:00Z")]}
    git2 = {"S-1": [_entry("S-1", "status", "git",    "Implementing", "2026-05-04T15:00:00Z")]}
    plan = sync.resolve_conflicts(gh2, git2, "last-write-wins")
    assert plan[0]["winner"] == "local"
    assert plan[0]["value"] == "Implementing"


def test_single_source_change_is_not_a_conflict():
    """If only one source changed a particular field, no conflict on that field."""
    gh =  {"S-1": [_entry("S-1", "status", "github", "Done", "2026-05-04T12:00:00Z")]}
    git = {"S-1": [_entry("S-1", "js",     "git",    8,      "2026-05-04T13:00:00Z")]}
    # Both items appear in conflict_ids (same item modified by both sources),
    # but no shared field → no entries in plan
    plan = sync.resolve_conflicts(gh, git, "last-write-wins")
    assert plan == []


def test_multiple_fields_per_item_each_resolved_independently():
    gh = {"S-1": [
        _entry("S-1", "status", "github", "Done", "2026-05-04T15:00:00Z"),
        _entry("S-1", "js",     "github", 8,       "2026-05-04T10:00:00Z"),
    ]}
    git = {"S-1": [
        _entry("S-1", "status", "git", "Implementing", "2026-05-04T10:00:00Z"),
        _entry("S-1", "js",     "git", 5,               "2026-05-04T15:00:00Z"),
    ]}
    plan = sync.resolve_conflicts(gh, git, "last-write-wins")
    by_field = {p["field"]: p for p in plan}
    # status: github newer → remote wins
    assert by_field["status"]["winner"] == "remote"
    assert by_field["status"]["value"] == "Done"
    # js: git newer → local wins
    assert by_field["js"]["winner"] == "local"
    assert by_field["js"]["value"] == 5


def test_unknown_strategy_raises():
    with pytest.raises(ValueError):
        sync.resolve_conflicts({}, {}, "make-it-up")


def test_no_conflicts_returns_empty():
    plan = sync.resolve_conflicts({}, {}, "last-write-wins")
    assert plan == []


def test_only_conflict_items_appear_in_plan():
    """Items modified by only one source should not appear at all."""
    gh = {
        "S-1": [_entry("S-1", "status", "github", "Done", "2026-05-04T12:00:00Z")],
        "S-2": [_entry("S-2", "status", "github", "Done", "2026-05-04T12:00:00Z")],
    }
    git = {
        "S-1": [_entry("S-1", "status", "git", "Implementing", "2026-05-04T13:00:00Z")],
        # S-2 NOT in git_changes
    }
    plan = sync.resolve_conflicts(gh, git, "last-write-wins")
    assert {p["item_id"] for p in plan} == {"S-1"}
