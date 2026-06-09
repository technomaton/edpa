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
