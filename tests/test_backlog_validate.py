"""Tests for backlog.py `validate`: the parent-requirement rule (D-72) and the
Story assignee/iteration lifecycle and references (D-100, at the end).

The standalone `backlog validate` hierarchy check must agree with the rest of
the system. Both create-side (`mcp_server._handle_item_create` via
`PARENT_RULES`) and the syntax validator (`validate_syntax.ITEM_SCHEMA`
`parent_required`) treat Defect / Event / Risk as top-level items that need
NO parent ("Defect/Event/Risk land at top level — no parent required", per
`backlog add --help`), while the Epic->Initiative / Feature->Epic /
Story->Feature spine still requires one.

Regression (D-72, deferred from D-69): cmd_validate rule #4 previously flagged
*every* parentless non-Initiative item as "missing parent reference", so a
valid parentless Defect/Event/Risk was reported as an error — contradicting
both create-side checks.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import backlog  # noqa: E402


def _run(*items):
    """Run cmd_validate over an in-memory backlog; return (rc, stdout lines)."""
    rc = backlog.cmd_validate({"items": list(items)}, argparse.Namespace())
    return rc


# ---------------------------------------------------------------------------
# Defect / Event / Risk land at top level — parentless is valid (the D-72 bug)
# ---------------------------------------------------------------------------

def test_parentless_defect_event_risk_pass(capsys):
    """A backlog of parentless Defect + Event + Risk validates with 0 errors."""
    rc = _run(
        {"id": "D-1", "type": "Defect", "title": "Crash on upload", "status": "Backlog"},
        {"id": "EV-1", "type": "Event", "title": "Sprint Review", "status": "Backlog"},
        {"id": "R-1", "type": "Risk", "title": "Scope creep"},
    )
    out = capsys.readouterr().out
    assert "missing parent reference" not in out, out
    assert rc == 0, out


# ---------------------------------------------------------------------------
# The Epic->Feature->Story spine still requires a parent (guard against regress)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "item",
    [
        {"id": "E-9", "type": "Epic", "title": "Orphan epic", "status": "Ready"},
        {"id": "F-9", "type": "Feature", "title": "Orphan feature",
         "status": "Backlog", "js": 3},
        {"id": "S-9", "type": "Story", "title": "Orphan story", "status": "Backlog",
         "js": 3, "assignee": "someone", "iteration": "PI-1"},
    ],
    ids=["Epic", "Feature", "Story"],
)
def test_parentless_spine_item_errors(item, capsys):
    """A parentless Epic/Feature/Story is still a 'missing parent reference' error."""
    rc = _run(item)
    out = capsys.readouterr().out
    assert any(
        item["id"] in line and "missing parent reference" in line
        for line in out.splitlines()
    ), out
    assert rc >= 1, out


# ---------------------------------------------------------------------------
# A dangling parent reference is still caught (existing behavior preserved)
# ---------------------------------------------------------------------------

def test_dangling_parent_reference_still_errors(capsys):
    """A Feature pointing at a non-existent parent still errors."""
    rc = _run(
        {"id": "F-2", "type": "Feature", "title": "Bad parent",
         "status": "Backlog", "js": 3, "parent": "E-404"},
    )
    out = capsys.readouterr().out
    assert any(
        "F-2" in line and "does not exist" in line for line in out.splitlines()
    ), out
    assert rc >= 1, out


# ---------------------------------------------------------------------------
# D-100: create leaves a Story without assignee and iteration — the assignee is
# decided when someone takes the work, the iteration at planning. validate must
# accept that, warn about a missing iteration only once work has started, and
# still reject a supplied assignee or iteration that resolves to nothing.
# ---------------------------------------------------------------------------

SPINE = [
    {"id": "I-1", "type": "Initiative", "title": "Platform", "status": "Implementing"},
    {"id": "E-1", "type": "Epic", "title": "Access", "parent": "I-1",
     "status": "Implementing"},
    {"id": "F-1", "type": "Feature", "title": "Auth", "parent": "E-1",
     "status": "Implementing", "js": 3, "bv": 5, "tc": 3, "rr_oe": 2},
]


def _story(status, **fields):
    return {"id": "S-1", "type": "Story", "title": "Login", "parent": "F-1",
            "status": status, "js": 3, **fields}


@pytest.fixture
def edpa_root(tmp_path):
    """A .edpa/ with one person, one PI record and one iteration record."""
    edpa = tmp_path / ".edpa"
    (edpa / "config").mkdir(parents=True)
    (edpa / "iterations").mkdir()
    (edpa / "config" / "people.yaml").write_text(
        yaml.safe_dump({"people": [{"id": "alice", "name": "Alice"}]}), encoding="utf-8")
    (edpa / "iterations" / "PI-2026-1.yaml").write_text(
        yaml.safe_dump({"pi": {"id": "PI-2026-1"}}), encoding="utf-8")
    (edpa / "iterations" / "PI-2026-1.1.yaml").write_text(
        yaml.safe_dump({"iteration": {"id": "PI-2026-1.1"}}), encoding="utf-8")
    return edpa


def _run_in(edpa_root, *items):
    """Run cmd_validate with the project root, as main() does."""
    return backlog.cmd_validate({"items": list(items)}, argparse.Namespace(_root=edpa_root))


@pytest.mark.parametrize("status", ["Funnel", "Analyzing", "Backlog"])
def test_unplanned_story_needs_no_assignee_or_iteration(edpa_root, status, capsys):
    """The Story create leaves behind validates with no error or warning."""
    rc = _run_in(edpa_root, *SPINE, _story(status))
    out = capsys.readouterr().out
    assert "missing" not in out, out
    assert rc == 0, out


@pytest.mark.parametrize("status", ["Implementing", "Validating", "Deploying", "Releasing", "Done"])
def test_started_story_without_iteration_warns(edpa_root, status, capsys):
    """From the start of work a missing iteration is reported, as a warning:
    a snapshot cannot tell a legacy item from a new one."""
    rc = _run_in(edpa_root, *SPINE, _story(status))
    out = capsys.readouterr().out
    assert "S-1 (Login): missing iteration assignment" in out, out
    assert rc == 0, out


def test_resolved_assignee_and_iteration_pass(edpa_root, capsys):
    rc = _run_in(edpa_root, *SPINE,
                 _story("Implementing", assignee="alice", iteration="PI-2026-1.1"))
    out = capsys.readouterr().out
    assert rc == 0, out


@pytest.mark.parametrize("assignee", ["mallory", ["alice"]], ids=["unknown", "not-a-string"])
def test_unresolved_assignee_errors(edpa_root, assignee, capsys):
    rc = _run_in(edpa_root, *SPINE, _story("Backlog", assignee=assignee))
    out = capsys.readouterr().out
    assert "is not a person id from config/people.yaml" in out, out
    assert rc == 1, out


@pytest.mark.parametrize("iteration", ["PI-2026-1", "PI-2026-1.9", 2026.1],
                         ids=["pi", "no-record", "not-a-string"])
def test_unresolved_iteration_errors(edpa_root, iteration, capsys):
    rc = _run_in(edpa_root, *SPINE, _story("Implementing", iteration=iteration))
    out = capsys.readouterr().out
    assert "has no iteration record in iterations/" in out, out
    assert rc == 1, out


# ---------------------------------------------------------------------------
# D-102: a Feature in progress without its WSJF estimate draws a warning;
# an unstarted Feature does not need one, and Done Features are history.
# ---------------------------------------------------------------------------

def _feature(status, **fields):
    return {"id": "F-2", "type": "Feature", "title": "Search", "parent": "E-1",
            "status": status, **fields}


@pytest.mark.parametrize("status", ["Implementing", "Releasing"])
def test_feature_in_progress_without_estimate_warns(status, capsys):
    rc = _run(*SPINE, _feature(status, js=5))
    out = capsys.readouterr().out
    assert "F-2 (Search): has no WSJF estimate (needs bv, tc, rr_oe above 0)" in out, out
    assert rc == 0, out


@pytest.mark.parametrize("status", ["Backlog", "Done"])
def test_unstarted_or_done_feature_draws_no_estimate_warning(status, capsys):
    rc = _run(*SPINE, _feature(status))
    out = capsys.readouterr().out
    assert "has no WSJF estimate" not in out, out
    assert rc == 0, out
