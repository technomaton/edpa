"""Tests for backlog.py `validate` command parent-requirement rule (D-72).

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
