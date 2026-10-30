"""Tests for validate_syntax.py backlog-schema validation.

Covers D-4: Event entry in ITEM_SCHEMA + roam_status enum enforcement.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

import validate_syntax  # noqa: E402
from validate_syntax import validate_backlog_schema, ROAM_STATUSES  # noqa: E402


def _path(type_dir: str, item_id: str) -> Path:
    return Path(f"/repo/.edpa/backlog/{type_dir}/{item_id}.md")


# ---------------------------------------------------------------------------
# Event schema present in ITEM_SCHEMA
# ---------------------------------------------------------------------------

def test_event_schema_exists():
    assert "Event" in validate_syntax.ITEM_SCHEMA
    schema = validate_syntax.ITEM_SCHEMA["Event"]
    assert schema["dir"] == "events"
    assert {"id", "type", "title", "status"} <= schema["required"]


def test_event_prefix_in_type_prefixes():
    assert validate_syntax.TYPE_PREFIXES.get("Event") == "EV"


def test_valid_event_passes():
    data = {"id": "EV-1", "type": "Event", "title": "Sprint Review", "status": "Backlog"}
    errors, warnings = validate_backlog_schema(_path("events", "EV-1.md"), data)
    assert not errors, errors


def test_event_missing_status_fails():
    data = {"id": "EV-1", "type": "Event", "title": "Sprint Review"}
    errors, _ = validate_backlog_schema(_path("events", "EV-1.md"), data)
    assert any("status" in e for e in errors)


def test_event_bad_id_prefix_fails():
    data = {"id": "S-1", "type": "Event", "title": "Sprint Review", "status": "Backlog"}
    errors, _ = validate_backlog_schema(_path("events", "S-1.md"), data)
    assert any("EV" in e for e in errors)


# ---------------------------------------------------------------------------
# roam_status enum for Risk
# ---------------------------------------------------------------------------

def test_roam_statuses_constant_complete():
    assert ROAM_STATUSES == {"resolved", "owned", "accepted", "mitigated"}


def test_valid_roam_status_passes():
    for rs in ROAM_STATUSES:
        data = {"id": "R-1", "type": "Risk", "title": "Scope creep", "roam_status": rs}
        errors, _ = validate_backlog_schema(_path("risks", "R-1.md"), data)
        assert not errors, f"Expected no errors for roam_status={rs!r}: {errors}"


def test_invalid_roam_status_rejected():
    data = {"id": "R-1", "type": "Risk", "title": "Scope creep", "roam_status": "nonsense"}
    errors, _ = validate_backlog_schema(_path("risks", "R-1.md"), data)
    assert any("roam_status" in e for e in errors), errors


def test_roam_status_on_non_risk_ignored():
    """roam_status field on a non-Risk item must not trigger an error."""
    data = {"id": "EV-1", "type": "Event", "title": "Review", "status": "Backlog",
            "roam_status": "nonsense"}
    errors, _ = validate_backlog_schema(_path("events", "EV-1.md"), data)
    assert not any("roam_status" in e for e in errors), errors


# ---------------------------------------------------------------------------
# D-69: parent-axis create-vs-validate alignment.
#
# backlog.py `add --help` documents "Defect/Event/Risk land at top level — no
# parent required" and mcp_server.PARENT_RULES maps all three to None (create
# allows them parentless). validate_backlog_schema must agree: parent is
# OPTIONAL for the top-level types and REQUIRED only for the Epic/Feature/Story
# spine. These lock that contract so nobody flips parent_required back on for
# Defect/Event/Risk and re-opens the create-vs-validate disagreement.
# ---------------------------------------------------------------------------

def test_parentless_top_level_types_pass():
    """Defect/Event/Risk validate with no `parent` field (top-level items)."""
    cases = [
        ("defects", "Defect", "D-1", {"js": 3}),
        ("events", "Event", "EV-1", {}),
        ("risks", "Risk", "R-1", {}),
    ]
    for type_dir, itype, iid, extra in cases:
        data = {"id": iid, "type": itype, "title": "X", "status": "Backlog", **extra}
        errors, _ = validate_backlog_schema(_path(type_dir, f"{iid}.md"), data)
        assert not any("parent" in e for e in errors), (itype, errors)


def test_parentless_spine_types_fail():
    """Epic/Feature/Story still REQUIRE a parent — only top-level types exempt."""
    cases = [
        ("epics", "Epic", "E-1", {}),
        ("features", "Feature", "F-1", {"js": 3}),
        ("stories", "Story", "S-1", {"js": 3, "iteration": "PI-2026-1.1"}),
    ]
    for type_dir, itype, iid, extra in cases:
        data = {"id": iid, "type": itype, "title": "X", "status": "Backlog", **extra}
        errors, _ = validate_backlog_schema(_path(type_dir, f"{iid}.md"), data)
        assert any("parent" in e for e in errors), (itype, errors)


# ---------------------------------------------------------------------------
# D-100: create leaves a Story's iteration unset, so the schema requires it
# only once the Story is Done — its delivery iteration.
# ---------------------------------------------------------------------------

def _story(**fields):
    return {"id": "S-1", "type": "Story", "title": "X", "parent": "F-1", "js": 3, **fields}


@pytest.mark.parametrize("status", ["Funnel", "Analyzing", "Backlog"])
def test_unplanned_story_without_iteration_passes(status):
    errors, _ = validate_backlog_schema(_path("stories", "S-1"), _story(status=status))
    assert not errors, errors


def test_done_story_without_iteration_fails():
    errors, _ = validate_backlog_schema(_path("stories", "S-1"), _story(status="Done"))
    assert any("missing required field 'iteration'" in e for e in errors), errors


def test_done_story_with_iteration_passes():
    errors, _ = validate_backlog_schema(
        _path("stories", "S-1"), _story(status="Done", iteration="PI-2026-1.1"))
    assert not errors, errors


# ---------------------------------------------------------------------------
# D-102: create writes a Feature with `js: 0`; the estimate is due when work
# starts — from Implementing on, all four WSJF inputs above 0.
# ---------------------------------------------------------------------------

def _feature(**fields):
    return {"id": "F-1", "type": "Feature", "title": "X", "parent": "E-1", **fields}


@pytest.mark.parametrize("status", ["Funnel", "Analyzing", "Backlog"])
def test_unstarted_feature_without_estimate_passes(status):
    errors, _ = validate_backlog_schema(
        _path("features", "F-1"), _feature(status=status, js=0))
    assert not errors, errors


@pytest.mark.parametrize("status", ["Implementing", "Done"])
def test_started_feature_without_wsjf_estimate_fails(status):
    errors, _ = validate_backlog_schema(
        _path("features", "F-1"), _feature(status=status, js=5, bv=0, tc=3))
    assert any("needs its WSJF estimate" in e and e.endswith("bv, rr_oe") for e in errors), errors


def test_started_feature_with_wsjf_estimate_passes():
    errors, _ = validate_backlog_schema(
        _path("features", "F-1"), _feature(status="Implementing", js=5, bv=8, tc=3, rr_oe=2))
    assert not errors, errors
