"""Tests for payroll_export.py — billable hours CSV generation."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "edpa" / "scripts"))

from payroll_export import (  # noqa: E402
    build_rows,
    export,
    load_people_config,
    load_project_code,
    load_results,
    render_csv,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ITERATION_ID = "PI-2026-1.1"

SAMPLE_RESULTS = {
    "iteration": ITERATION_ID,
    "generated_at": "2026-06-09T00:00:00Z",
    "capacity_config": {
        "people": [
            {"id": "alice", "name": "Alice", "role": "Dev", "team": "Alpha"},
            {"id": "bob", "name": "Bob", "role": "Arch", "team": "Beta"},
        ]
    },
    "derived_reports": [
        {"person": "alice", "name": "Alice", "role": "Dev", "capacity": 40, "total_derived": 38.5},
        {"person": "bob", "name": "Bob", "role": "Arch", "capacity": 20, "total_derived": 19.0},
    ],
    "items": [],
    "invariants": {"all_passed": True},
}

SAMPLE_PEOPLE_YAML = """\
people:
  - id: alice
    name: Alice
    role: Dev
    team: Alpha
    fte: 1.0
    capacity_per_iteration: 40
    hourly_rate: 1500
    currency: CZK
  - id: bob
    name: Bob
    role: Arch
    team: Beta
    fte: 0.5
    capacity_per_iteration: 20
"""

SAMPLE_EDPA_YAML = """\
project:
  name: "Test Project"
  funding:
    registration: "CZ.01.01.01/01/24_TEST"
"""


@pytest.fixture
def workspace(tmp_path):
    edpa = tmp_path / ".edpa"
    (edpa / "config").mkdir(parents=True)
    (edpa / "reports" / f"iteration-{ITERATION_ID}").mkdir(parents=True)

    (edpa / "reports" / f"iteration-{ITERATION_ID}" / "edpa_results.json").write_text(
        json.dumps(SAMPLE_RESULTS), encoding="utf-8"
    )
    (edpa / "config" / "people.yaml").write_text(SAMPLE_PEOPLE_YAML, encoding="utf-8")
    (edpa / "config" / "edpa.yaml").write_text(SAMPLE_EDPA_YAML, encoding="utf-8")
    return edpa


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_load_results(workspace):
    r = load_results(workspace, ITERATION_ID)
    assert r["iteration"] == ITERATION_ID
    assert len(r["derived_reports"]) == 2


def test_load_results_missing_raises(workspace):
    with pytest.raises(FileNotFoundError):
        load_results(workspace, "PI-2099-1.1")


def test_load_people_config(workspace):
    cfg = load_people_config(workspace)
    assert cfg["alice"]["hourly_rate"] == 1500
    assert cfg["alice"]["currency"] == "CZK"
    assert cfg["bob"]["hourly_rate"] is None


def test_load_project_code(workspace):
    code = load_project_code(workspace)
    assert "CZ.01.01.01" in code


def test_load_project_code_legacy_registration(tmp_path):
    edpa = tmp_path / ".edpa"
    (edpa / "config").mkdir(parents=True)
    (edpa / "config" / "edpa.yaml").write_text(
        "project:\n  registration: LEGACY-123\n", encoding="utf-8"
    )
    assert load_project_code(edpa) == "LEGACY-123"


def test_build_rows_basic(workspace):
    results = load_results(workspace, ITERATION_ID)
    people = load_people_config(workspace)
    rows = build_rows(results, people, "CODE-1", "CZK")
    assert len(rows) == 2
    alice = next(r for r in rows if r["person"] == "alice")
    assert alice["hours"] == 38.5
    assert alice["rate"] == 1500
    assert alice["cost"] == pytest.approx(38.5 * 1500)
    assert alice["currency"] == "CZK"
    assert alice["code"] == "CODE-1"


def test_build_rows_missing_rate_leaves_cost_empty(workspace):
    results = load_results(workspace, ITERATION_ID)
    people = load_people_config(workspace)
    rows = build_rows(results, people, "", "")
    bob = next(r for r in rows if r["person"] == "bob")
    assert bob["rate"] == ""
    assert bob["cost"] == ""


def test_build_rows_cli_currency_fallback(workspace):
    results = load_results(workspace, ITERATION_ID)
    # bob has no currency in people.yaml — should use CLI flag
    people = load_people_config(workspace)
    rows = build_rows(results, people, "", "EUR")
    bob = next(r for r in rows if r["person"] == "bob")
    assert bob["currency"] == "EUR"


def test_render_csv_headers(workspace):
    results = load_results(workspace, ITERATION_ID)
    people = load_people_config(workspace)
    rows = build_rows(results, people, "", "")
    text = render_csv(rows)
    reader = csv.DictReader(text.splitlines())
    assert set(reader.fieldnames) >= {"person", "hours", "rate", "cost", "currency", "iteration"}


def test_export_writes_file(workspace):
    out = workspace / "reports" / f"iteration-{ITERATION_ID}" / "payroll.csv"
    result = export(workspace, ITERATION_ID, currency="CZK", output=out)
    assert out.exists()
    assert result["rows"] == 2
    assert result["total_hours"] == pytest.approx(38.5 + 19.0)
    # Verify CSV is parseable
    rows = list(csv.DictReader(out.read_text(encoding="utf-8").splitlines()))
    assert len(rows) == 2


def test_export_default_output_path(workspace):
    result = export(workspace, ITERATION_ID)
    path = Path(result["path"])
    assert path.exists()
    assert path.suffix == ".csv"
    assert ITERATION_ID in path.name


def test_export_missing_people_yaml(workspace):
    (workspace / "config" / "people.yaml").unlink()
    # Should not crash — people config is optional
    result = export(workspace, ITERATION_ID)
    assert result["rows"] == 2


def test_export_missing_edpa_yaml(workspace):
    (workspace / "config" / "edpa.yaml").unlink()
    result = export(workspace, ITERATION_ID)
    # code column should be empty string, not crash
    out = Path(result["path"])
    rows = list(csv.DictReader(out.read_text(encoding="utf-8").splitlines()))
    assert all(r["code"] == "" for r in rows)
