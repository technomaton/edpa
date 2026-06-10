"""Tests for explain.py — allocation narrative generator."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

from explain import explain_person, load_results  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ITERATION_ID = "PI-2026-1.1"

# Mirrors the REAL engine output schema (engine.py writes `people[]` with each
# person's items NESTED under their entry — key `js`, not a flat top-level
# `items` keyed by `contributor`). Keep it that way: an earlier fictional
# `derived_reports` fixture let explain.py ship broken (D-16). If you change the
# engine's edpa_results.json shape, change this with it.
RESULTS = {
    "iteration": ITERATION_ID,
    "computed_at": "2026-06-09T00:00:00Z",
    "methodology": "EDPA 2.6.0",
    "planning_factor": 0.8,
    "people": [
        {
            "id": "alice", "name": "Alice", "role": "Dev",
            "capacity": 40, "total_derived": 40.0, "invariant_ok": True,
            "items": [
                {"id": "S-1", "level": "Story", "js": 5, "cw": 0.7, "rs": 1.0,
                 "score": 3.5, "evidence": [], "ratio": 0.5833, "hours": 23.33},
                {"id": "S-2", "level": "Story", "js": 4, "cw": 1.0, "rs": 1.0,
                 "score": 4.0, "evidence": [], "ratio": 0.4167, "hours": 16.67},
            ],
        },
        {
            "id": "bob", "name": "Bob", "role": "Arch",
            "capacity": 20, "total_derived": 20.0, "invariant_ok": True,
            "items": [
                {"id": "S-1", "level": "Story", "js": 5, "cw": 0.3, "rs": 1.0,
                 "score": 1.5, "evidence": [], "ratio": 1.0, "hours": 20.0},
            ],
        },
    ],
    "team_total": 60.0,
    "all_invariants_passed": True,
    "gate_events": [],
}

STORY_WITH_SIGNALS = """\
---
id: S-1
type: Story
title: Implement login
js: 5
status: Done
contributors:
  - person: alice
    cw: 0.7
    contribution_score: 6.78
    signals:
      - type: commit_author
        ref: pr#42/commit/abc
        weight: 2.78
      - type: pr_author
        ref: pr#42
        weight: 4.00
  - person: bob
    cw: 0.3
    contribution_score: 2.25
    signals:
      - type: pr_reviewer
        ref: pr#42/review/r1
        weight: 2.25
---
"""

STORY_MANUAL_CW = """\
---
id: S-2
type: Story
title: Add tests
js: 4
status: Done
contributors:
  - person: alice
    cw: 1.0
    as: owner
---
"""


@pytest.fixture
def workspace(tmp_path):
    edpa = tmp_path / ".edpa"
    (edpa / "reports" / f"iteration-{ITERATION_ID}").mkdir(parents=True)
    (edpa / "reports" / f"iteration-{ITERATION_ID}" / "edpa_results.json").write_text(
        json.dumps(RESULTS), encoding="utf-8"
    )
    stories = edpa / "backlog" / "stories"
    stories.mkdir(parents=True)
    (stories / "S-1.md").write_text(STORY_WITH_SIGNALS, encoding="utf-8")
    (stories / "S-2.md").write_text(STORY_MANUAL_CW, encoding="utf-8")
    return edpa


# ---------------------------------------------------------------------------
# load_results
# ---------------------------------------------------------------------------

def test_load_results_ok(workspace):
    r = load_results(workspace, ITERATION_ID)
    assert r["iteration"] == ITERATION_ID


def test_load_results_missing_raises(workspace):
    with pytest.raises(FileNotFoundError):
        load_results(workspace, "PI-2099-1.1")


# ---------------------------------------------------------------------------
# explain_person — happy paths
# ---------------------------------------------------------------------------

def test_explain_contains_person_name(workspace):
    results = load_results(workspace, ITERATION_ID)
    md = explain_person(results, "alice", workspace)
    assert "Alice" in md
    assert "Dev" in md


def test_explain_contains_item_ids(workspace):
    results = load_results(workspace, ITERATION_ID)
    md = explain_person(results, "alice", workspace)
    assert "S-1" in md
    assert "S-2" in md


def test_explain_contains_item_title(workspace):
    results = load_results(workspace, ITERATION_ID)
    md = explain_person(results, "alice", workspace)
    assert "Implement login" in md
    assert "Add tests" in md


def test_explain_shows_signal_details(workspace):
    results = load_results(workspace, ITERATION_ID)
    md = explain_person(results, "alice", workspace)
    assert "commit_author" in md
    assert "pr_author" in md
    assert "4.00" in md or "4.0" in md  # signal weight


def test_explain_shows_manual_cw(workspace):
    results = load_results(workspace, ITERATION_ID)
    md = explain_person(results, "alice", workspace)
    assert "manual CW" in md or "owner" in md


def test_explain_contains_hours(workspace):
    results = load_results(workspace, ITERATION_ID)
    md = explain_person(results, "alice", workspace)
    assert "23.33h" in md or "16.67h" in md


def test_explain_invariant_footer_ok(workspace):
    results = load_results(workspace, ITERATION_ID)
    md = explain_person(results, "alice", workspace)
    assert "✓" in md


def test_explain_bob_only_one_item(workspace):
    results = load_results(workspace, ITERATION_ID)
    md = explain_person(results, "bob", workspace)
    assert "S-1" in md
    assert "S-2" not in md


def test_explain_item_filter(workspace):
    results = load_results(workspace, ITERATION_ID)
    md = explain_person(results, "alice", workspace, item_filter="S-1")
    assert "S-1" in md
    assert "S-2" not in md
    # No invariant footer when filtering
    assert "Invariant" not in md


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_explain_unknown_person(workspace):
    results = load_results(workspace, ITERATION_ID)
    md = explain_person(results, "nobody", workspace)
    assert md.startswith("ERROR:")


def test_explain_item_not_attributed(workspace):
    results = load_results(workspace, ITERATION_ID)
    md = explain_person(results, "alice", workspace, item_filter="S-99")
    assert md.startswith("ERROR:")


def test_explain_missing_backlog_graceful(tmp_path):
    """Works even if backlog files are missing — signals section shows fallback."""
    edpa = tmp_path / ".edpa"
    (edpa / "reports" / f"iteration-{ITERATION_ID}").mkdir(parents=True)
    (edpa / "reports" / f"iteration-{ITERATION_ID}" / "edpa_results.json").write_text(
        json.dumps(RESULTS), encoding="utf-8"
    )
    # No backlog directory at all
    results = load_results(edpa, ITERATION_ID)
    md = explain_person(results, "alice", edpa)
    assert "S-1" in md  # item still appears
    assert "No contributors[] block" in md or "heuristics" in md
