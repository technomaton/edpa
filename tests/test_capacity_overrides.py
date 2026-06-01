"""Tests for v1.9.0 per-person, per-iteration capacity overrides.

The override is expressed as a top-level `people:` block in
.edpa/iterations/<id>.yaml that reuses the people.yaml schema as a
partial override. Engine matches by `id`, applies recognised fields
(capacity_per_iteration / capacity), and preserves an optional `note`
for audit. RFC: docs/proposals/per-iteration-capacity-overrides.md.

Engine helpers under test:
  - _load_iteration_people_overrides
  - _resolve_capacity
  - run_edpa(edpa_root=, iteration_id=) integration
  - _snapshot_payload baseline + override persistence

Validator helpers under test:
  - validate_iteration_people_overrides
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))
import engine  # noqa: E402
from _md_frontmatter import save_md  # noqa: E402
from validate_syntax import validate_iteration_people_overrides  # noqa: E402


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _seed_minimal_edpa(tmp_path: Path, *, iteration_id="PI-2026-1.1",
                       people_overrides: list | None = None,
                       cw=1.0):
    """Create a minimal .edpa/ with two Done stories so engine has work
    to allocate to both bob (40h baseline) and alice (20h baseline).
    """
    edpa = tmp_path / ".edpa"
    (edpa / "config").mkdir(parents=True)
    (edpa / "iterations").mkdir(parents=True)
    (edpa / "backlog" / "stories").mkdir(parents=True)
    (edpa / "backlog" / "features").mkdir(parents=True)

    (edpa / "config" / "people.yaml").write_text(yaml.safe_dump({
        "teams": [{"id": "T", "planning_factor": 0.8}],
        "people": [
            {"id": "bob-dev",   "name": "Bob",   "role": "Dev",  "team": "T",
             "fte": 1.0, "capacity_per_iteration": 40, "email": "b@e.t",
             "github": "bob",   "availability": "confirmed"},
            {"id": "alice-arch", "name": "Alice", "role": "Arch", "team": "T",
             "fte": 0.5, "capacity_per_iteration": 20, "email": "a@e.t",
             "github": "alice", "availability": "confirmed"},
        ],
    }))
    (edpa / "config" / "heuristics.yaml").write_text(yaml.safe_dump({
        "version": "1.0.0", "evidence_threshold": 1.0,
        "role_weights": {"owner": 1.0, "key": 0.6, "reviewer": 0.25, "consulted": 0.15},
    }))

    iteration_doc = {
        "iteration": {
            "id": iteration_id, "pi": iteration_id.rsplit(".", 1)[0],
            "type": "delivery", "sequence": 1,
            "start_date": "2026-05-04", "end_date": "2026-05-10",
            "status": "closed",
        },
    }
    if people_overrides is not None:
        iteration_doc["people"] = people_overrides
    (edpa / "iterations" / f"{iteration_id}.yaml").write_text(
        yaml.safe_dump(iteration_doc))

    save_md(edpa / "backlog" / "stories" / "S-1.md", {
        "id": "S-1", "type": "Story", "title": "test",
        "parent": "F-1", "js": 5, "status": "Done",
        "iteration": iteration_id,
        "contributors": [{"person": "bob-dev", "as": "owner", "cw": cw}],
    })
    save_md(edpa / "backlog" / "stories" / "S-2.md", {
        "id": "S-2", "type": "Story", "title": "test 2",
        "parent": "F-1", "js": 3, "status": "Done",
        "iteration": iteration_id,
        "contributors": [{"person": "alice-arch", "as": "owner", "cw": cw}],
    })
    return edpa


def _run(edpa_root: Path, iteration_id: str):
    capacity = engine.load_yaml(edpa_root / "config" / "people.yaml")
    heuristics = engine.load_heuristics(edpa_root)
    items, _ = engine.load_backlog_items(edpa_root, iteration_id)
    return engine.run_edpa(
        capacity, heuristics, items,
        edpa_root=edpa_root, iteration_id=iteration_id,
    )


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------

def test_capacity_override_applied(tmp_path):
    """capacity_per_iteration override → engine uses overridden value."""
    edpa = _seed_minimal_edpa(tmp_path, people_overrides=[
        {"id": "bob-dev", "capacity_per_iteration": 44,
         "note": "IP weekend deploy push"},
    ])
    people = _run(edpa, "PI-2026-1.1")
    bob = next(p for p in people if p["id"] == "bob-dev")
    assert bob["capacity"] == 44
    assert bob["capacity_baseline"] == 40
    assert bob["capacity_override"]["capacity"] == 44
    assert bob["capacity_override"]["note"] == "IP weekend deploy push"
    assert bob["total_derived"] == 44.0
    assert bob["invariant_ok"] is True


def test_lower_capacity_override_for_pto(tmp_path):
    """capacity_per_iteration: 10 (vacation) → effective 10h."""
    edpa = _seed_minimal_edpa(tmp_path, people_overrides=[
        {"id": "alice-arch", "capacity_per_iteration": 10,
         "note": "vacation Jun 9-11 (3 days PTO)"},
    ])
    people = _run(edpa, "PI-2026-1.1")
    alice = next(p for p in people if p["id"] == "alice-arch")
    assert alice["capacity"] == 10
    assert alice["capacity_baseline"] == 20
    assert alice["total_derived"] == 10.0


def test_person_without_override_keeps_baseline(tmp_path):
    """Person not in iteration.people[] → baseline + no metadata."""
    edpa = _seed_minimal_edpa(tmp_path, people_overrides=[
        {"id": "bob-dev", "capacity_per_iteration": 44, "note": "overtime"},
    ])
    people = _run(edpa, "PI-2026-1.1")
    alice = next(p for p in people if p["id"] == "alice-arch")
    assert alice["capacity"] == 20
    assert "capacity_baseline" not in alice
    assert "capacity_override" not in alice


def test_no_override_section_is_no_op(tmp_path):
    """Iteration without iteration.people[] → behavior identical to v1.8.x."""
    edpa = _seed_minimal_edpa(tmp_path, people_overrides=None)
    people = _run(edpa, "PI-2026-1.1")
    for p in people:
        assert "capacity_baseline" not in p
        assert "capacity_override" not in p


def test_note_only_override_records_metadata(tmp_path):
    """Override entry with only `note:` (no capacity change) preserves
    baseline but records the note for audit."""
    edpa = _seed_minimal_edpa(tmp_path, people_overrides=[
        {"id": "bob-dev",
         "note": "worked usual hours, but pulled in C-Suite review meetings"},
    ])
    people = _run(edpa, "PI-2026-1.1")
    bob = next(p for p in people if p["id"] == "bob-dev")
    assert bob["capacity"] == 40              # baseline unchanged
    assert bob["capacity_baseline"] == 40
    assert bob["capacity_override"]["note"].startswith("worked usual hours")


def test_negative_capacity_rejected(tmp_path):
    """capacity_per_iteration: -5 → engine raises ValueError."""
    edpa = _seed_minimal_edpa(tmp_path, people_overrides=[
        {"id": "bob-dev", "capacity_per_iteration": -5,
         "note": "operator typo, should be 50"},
    ])
    with pytest.raises(ValueError, match="negative capacity"):
        _run(edpa, "PI-2026-1.1")


def test_invariant_holds_with_overrides(tmp_path):
    """Σ DerivedHours = effective capacity per person, even with overrides."""
    edpa = _seed_minimal_edpa(tmp_path, people_overrides=[
        {"id": "bob-dev",   "capacity_per_iteration": 44, "note": "overtime"},
        {"id": "alice-arch", "capacity_per_iteration": 12,
         "note": "partial vacation"},
    ])
    people = _run(edpa, "PI-2026-1.1")
    for p in people:
        if p["items"]:
            assert abs(p["total_derived"] - p["capacity"]) < 0.1
            assert p["invariant_ok"] is True


# ---------------------------------------------------------------------------
# Validator integration
# ---------------------------------------------------------------------------

def test_validator_rejects_unknown_person(tmp_path):
    edpa = _seed_minimal_edpa(tmp_path)
    iter_path = edpa / "iterations" / "PI-2026-1.1.yaml"
    data = {
        "iteration": {"id": "PI-2026-1.1"},
        "people": [
            {"id": "ghost-dev", "capacity_per_iteration": 44, "note": "phantom"},
        ],
    }
    errors, _ = validate_iteration_people_overrides(iter_path, data)
    assert any("not found in" in e for e in errors)


def test_validator_rejects_duplicate_person(tmp_path):
    edpa = _seed_minimal_edpa(tmp_path)
    iter_path = edpa / "iterations" / "PI-2026-1.1.yaml"
    data = {
        "iteration": {"id": "PI-2026-1.1"},
        "people": [
            {"id": "bob-dev", "capacity_per_iteration": 44, "note": "first"},
            {"id": "bob-dev", "capacity_per_iteration": 50, "note": "second"},
        ],
    }
    errors, _ = validate_iteration_people_overrides(iter_path, data)
    assert any("duplicates earlier entry" in e for e in errors)


def test_validator_rejects_entry_without_id(tmp_path):
    edpa = _seed_minimal_edpa(tmp_path)
    iter_path = edpa / "iterations" / "PI-2026-1.1.yaml"
    data = {
        "iteration": {"id": "PI-2026-1.1"},
        "people": [
            {"capacity_per_iteration": 44, "note": "no id"},
        ],
    }
    errors, _ = validate_iteration_people_overrides(iter_path, data)
    assert any("missing 'id'" in e for e in errors)


def test_validator_rejects_entry_without_override_fields(tmp_path):
    """Entry without capacity AND without note is almost certainly a typo."""
    edpa = _seed_minimal_edpa(tmp_path)
    iter_path = edpa / "iterations" / "PI-2026-1.1.yaml"
    data = {
        "iteration": {"id": "PI-2026-1.1"},
        "people": [
            {"id": "bob-dev"},
        ],
    }
    errors, _ = validate_iteration_people_overrides(iter_path, data)
    assert any("no override fields" in e for e in errors)


def test_validator_rejects_negative_capacity(tmp_path):
    edpa = _seed_minimal_edpa(tmp_path)
    iter_path = edpa / "iterations" / "PI-2026-1.1.yaml"
    data = {
        "iteration": {"id": "PI-2026-1.1"},
        "people": [
            {"id": "bob-dev", "capacity_per_iteration": -5,
             "note": "trying to be clever"},
        ],
    }
    errors, _ = validate_iteration_people_overrides(iter_path, data)
    assert any(">= 0" in e for e in errors)


def test_validator_accepts_clean_override(tmp_path):
    edpa = _seed_minimal_edpa(tmp_path)
    iter_path = edpa / "iterations" / "PI-2026-1.1.yaml"
    data = {
        "iteration": {"id": "PI-2026-1.1"},
        "people": [
            {"id": "bob-dev", "capacity_per_iteration": 44,
             "note": "IP weekend deploy push (Jun 13-14)"},
            {"id": "alice-arch", "capacity_per_iteration": 10,
             "note": "vacation Jun 9-11 (3 days PTO)"},
        ],
    }
    errors, warnings = validate_iteration_people_overrides(iter_path, data)
    assert errors == [], f"unexpected errors: {errors}"


def test_validator_accepts_note_only_override(tmp_path):
    edpa = _seed_minimal_edpa(tmp_path)
    iter_path = edpa / "iterations" / "PI-2026-1.1.yaml"
    data = {
        "iteration": {"id": "PI-2026-1.1"},
        "people": [
            {"id": "bob-dev", "note": "audit annotation only, no capacity change"},
        ],
    }
    errors, _ = validate_iteration_people_overrides(iter_path, data)
    assert errors == []


# ---------------------------------------------------------------------------
# Snapshot persistence
# ---------------------------------------------------------------------------

def test_snapshot_records_baseline_and_override(tmp_path):
    """write_snapshot output captures capacity, capacity_baseline, capacity_override."""
    edpa = _seed_minimal_edpa(tmp_path, people_overrides=[
        {"id": "bob-dev", "capacity_per_iteration": 44,
         "note": "IP weekend deploy push"},
    ])
    capacity_cfg = engine.load_yaml(edpa / "config" / "people.yaml")
    heuristics = engine.load_heuristics(edpa)
    items, _ = engine.load_backlog_items(edpa, "PI-2026-1.1")
    results = engine.run_edpa(
        capacity_cfg, heuristics, items,
        edpa_root=edpa, iteration_id="PI-2026-1.1",
    )
    output = {
        "iteration": "PI-2026-1.1",
        "mode": "simple",
        "computed_at": "2026-05-06T00:00:00+00:00",
        "methodology": "EDPA test",
        "people": results,
        "team_total": sum(r["total_derived"] for r in results),
        "all_invariants_passed": all(r["invariant_ok"] for r in results if r["items"]),
    }
    engine.write_snapshot(edpa, "PI-2026-1.1", output, capacity_cfg)
    snap = json.loads((edpa / "snapshots" / "PI-2026-1.1.json").read_text())
    bob_record = next(r for r in snap["derived_reports"] if r["person"] == "bob-dev")
    assert bob_record["capacity"] == 44
    assert bob_record["capacity_baseline"] == 40
    assert bob_record["capacity_override"]["capacity"] == 44
    assert bob_record["capacity_override"]["note"] == "IP weekend deploy push"
    alice_record = next(r for r in snap["derived_reports"] if r["person"] == "alice-arch")
    assert "capacity_baseline" not in alice_record
    assert "capacity_override" not in alice_record
