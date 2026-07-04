"""Tests for _results_compat.py — schema-tolerant edpa_results.json access (D-56).

Two producers write per-person results in different shapes:
  - engine CLI output: {"people": [{"id": ..., "capacity": ..., ...}]}
  - frozen snapshot:   {"derived_reports": [{"person": ..., ...}]}
Readers (payroll_export.py, insights.py) must accept both.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

from _results_compat import person_reports, registry_capacity_by_id  # noqa: E402


# person_reports — shape tolerance

def test_snapshot_shape_passthrough():
    results = {"derived_reports": [
        {"person": "alice", "name": "Alice", "capacity": 40, "total_derived": 38.5},
    ]}
    reports = person_reports(results)
    assert reports == [
        {"person": "alice", "name": "Alice", "capacity": 40, "total_derived": 38.5},
    ]


def test_engine_people_shape_normalized():
    """Engine CLI entries are keyed `id` — normalizer must expose `person`."""
    results = {"people": [
        {"id": "alice", "name": "Alice", "role": "Dev", "capacity": 60,
         "total_derived": 60.0, "items": [], "invariant_ok": True},
    ]}
    reports = person_reports(results)
    assert len(reports) == 1
    assert reports[0]["person"] == "alice"
    assert reports[0]["capacity"] == 60
    assert reports[0]["total_derived"] == 60.0


def test_derived_reports_preferred_over_people():
    results = {
        "derived_reports": [{"person": "a", "total_derived": 1.0}],
        "people": [{"id": "b", "total_derived": 2.0}],
    }
    assert [r["person"] for r in person_reports(results)] == ["a"]


def test_empty_derived_reports_falls_back_to_people():
    results = {"derived_reports": [], "people": [{"id": "b", "total_derived": 2.0}]}
    assert [r["person"] for r in person_reports(results)] == ["b"]


def test_missing_both_keys_returns_empty():
    assert person_reports({}) == []


def test_bogus_entries_skipped():
    results = {"people": ["not-a-dict", {"name": "no id"}, {"id": "ok"}]}
    assert [r["person"] for r in person_reports(results)] == ["ok"]


# person_reports — capacity fallback (people.yaml registry)

def test_capacity_fallback_from_registry():
    results = {"people": [{"id": "carol", "total_derived": 50.0}]}
    reports = person_reports(results, capacity_by_id={"carol": 40})
    assert reports[0]["capacity"] == 40


def test_capacity_explicit_zero_not_overridden():
    """capacity: 0 is an explicit value (e.g. vacation) — no fallback."""
    results = {"people": [{"id": "carol", "capacity": 0, "total_derived": 50.0}]}
    reports = person_reports(results, capacity_by_id={"carol": 40})
    assert reports[0]["capacity"] == 0


def test_input_entries_not_mutated():
    entry = {"id": "carol", "total_derived": 50.0}
    person_reports({"people": [entry]}, capacity_by_id={"carol": 40})
    assert "person" not in entry
    assert "capacity" not in entry


# registry_capacity_by_id

def test_registry_capacity_by_id(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "people.yaml").write_text(
        "people:\n"
        "  - id: alice\n"
        "    capacity_per_iteration: 60\n"
        "  - id: bob\n"
        "    capacity: 20\n"
        "  - id: carol\n"
        "    name: no capacity\n",
        encoding="utf-8",
    )
    caps = registry_capacity_by_id(tmp_path)
    assert caps == {"alice": 60, "bob": 20}


def test_registry_capacity_missing_file(tmp_path):
    assert registry_capacity_by_id(tmp_path) == {}
