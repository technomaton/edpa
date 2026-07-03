#!/usr/bin/env python3
"""
CI-suite tests for reports.py — timesheet + PI summary generator (S-246).

reports.py is the documented manual CLI (docs/playbook.md) and the e2e
fallback path for /edpa:reports; its only coverage used to live in the
opt-in e2e_v2_full harness (phases/11_verify_reports.py), which needs real
GitHub access and never runs in CI. These tests plant engine-shaped
edpa_results.json fixtures and run the script via subprocess, asserting the
Markdown it materialises.

Fixture shape mirrors what engine.py writes (see engine.py main(): iteration,
methodology, planning_factor, people[], team_total, all_invariants_passed;
person entries carry id/name/role/capacity/total_derived/items/invariant_ok
plus optional capacity_baseline/capacity_override).

The planted project + the default iteration run are module-scoped
(subprocess spawns are the dominant cost); tests that need pristine or
extra state plant their own tmp tree, so tests stay order-independent.

Run: python -m pytest tests/test_reports.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "plugin" / "edpa" / "scripts" / "reports.py"

PEOPLE_YAML = """\
people:
  - id: alice
    name: Alice Dev
    role: Dev
"""


def _alice():
    return {
        "id": "alice", "name": "Alice Dev", "role": "Dev",
        "capacity": 40, "total_derived": 40.0,
        "items": [
            # multi-signal: commit_author outranks pr_reviewer → role "owner"
            {"id": "S-1", "level": "Story", "js": 5, "cw": 0.62, "rs": 1.0,
             "score": 3.1, "evidence": ["commit_author", "pr_reviewer"],
             "ratio": 0.775, "hours": 31.0},
            {"id": "S-2", "level": "Story", "js": 3, "cw": 0.3, "rs": 1.0,
             "score": 0.9, "evidence": ["pr_reviewer"],
             "ratio": 0.225, "hours": 9.0},
        ],
        "invariant_ok": True,
    }


def _bob():
    return {
        "id": "bob-arch", "name": "Bob Arch", "role": "Arch",
        "capacity": 20, "total_derived": 0,
        "items": [],
        "invariant_ok": True,
    }


def _carol():
    return {
        "id": "carol", "name": "Carol QA", "role": "QA",
        "capacity": 10, "total_derived": 10.0,
        "items": [
            # manual /contribute directive → role "key"
            {"id": "F-1", "level": "Feature", "js": 8, "cw": 0.5, "rs": 1.0,
             "score": 4.0, "evidence": ["manual:pr_body"],
             "ratio": 1.0, "hours": 10.0},
        ],
        "invariant_ok": True,
    }


def _results(iteration, people, team_total):
    return {
        "iteration": iteration,
        "computed_at": "2026-01-16T12:00:00+00:00",
        "methodology": "EDPA-TEST",
        "planning_factor": 0.8,
        "people": people,
        "team_total": team_total,
        "all_invariants_passed": True,
    }


def _plant(edpa_root, iteration, results):
    out = edpa_root / "reports" / f"iteration-{iteration}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "edpa_results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )


def _plant_project(root, iterations=("PI-2026-1.1",)):
    edpa = root / ".edpa"
    (edpa / "config").mkdir(parents=True)
    (edpa / "config" / "people.yaml").write_text(PEOPLE_YAML, encoding="utf-8")
    for iteration in iterations:
        _plant(edpa, iteration,
               _results(iteration, [_alice(), _bob(), _carol()], 50.0))
    return edpa


def _run_reports(root, *args):
    return subprocess.run(
        [sys.executable, str(REPORTS), *args,
         "--edpa-root", str(root / ".edpa")],
        cwd=root, capture_output=True, text=True, encoding="utf-8",
        timeout=60,
    )


def _iter_dir(root, iteration="PI-2026-1.1"):
    return root / ".edpa" / "reports" / f"iteration-{iteration}"


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("reports-project")
    _plant_project(root)
    return root


@pytest.fixture(scope="module")
def iteration_run(project):
    """One `reports.py PI-2026-1.1` run shared by the content tests."""
    proc = _run_reports(project, "PI-2026-1.1")
    assert proc.returncode == 0, proc.stderr
    return proc


def test_iteration_reports_exit0_and_files(project, iteration_run):
    out_dir = _iter_dir(project)
    for name in ("timesheet-alice.md", "timesheet-bob-arch.md",
                 "timesheet-carol.md", "timesheet-team.md"):
        assert (out_dir / name).is_file(), name
    assert "Reports for PI-2026-1.1" in iteration_run.stdout
    assert "timesheet-alice.md" in iteration_run.stdout
    assert "(team rollup)" in iteration_run.stdout


def test_person_timesheet_content(project, iteration_run):
    text = (_iter_dir(project) / "timesheet-alice.md").read_text(encoding="utf-8")
    assert "# Timesheet — Alice Dev (Dev)" in text
    assert "- Iteration: **PI-2026-1.1**" in text
    assert "- Methodology: **EDPA-TEST**" in text
    assert "- Capacity: **40h**" in text
    assert "- Derived: **40.0h**" in text
    assert "- Invariant: **OK**" in text
    assert "| Item | Level | Role | JS | CW | Score | Ratio | Hours |" in text
    assert "| S-1 | Story | owner | 5 | 0.62 | 3.10 | 77.5% | 31.00 |" in text
    assert "| S-2 | Story | reviewer | 3 | 0.30 | 0.90 | 22.5% | 9.00 |" in text
    assert "**Total: 40.0h / 40h capacity**" in text
    # e2e phase 11 keyword vocabulary (_check_md_content)
    assert len(text) >= 50
    lower = text.lower()
    assert "capacity" in lower and "derived" in lower


def test_manual_signal_maps_to_key_role(project, iteration_run):
    text = (_iter_dir(project) / "timesheet-carol.md").read_text(encoding="utf-8")
    assert "| F-1 | Feature | key | 8 | 0.50 | 4.00 | 100.0% | 10.00 |" in text


def test_person_without_items(project, iteration_run):
    text = (_iter_dir(project) / "timesheet-bob-arch.md").read_text(encoding="utf-8")
    assert "_No items credited this iteration._" in text
    assert "**Total: 0h / 20h capacity**" in text


def test_team_rollup_content(project, iteration_run):
    text = (_iter_dir(project) / "timesheet-team.md").read_text(encoding="utf-8")
    assert "# Team Rollup — PI-2026-1.1" in text
    assert "- Methodology: **EDPA-TEST**" in text
    assert "- Planning factor: **0.8**" in text
    assert "- Team capacity: **70h**" in text
    assert "- Team derived: **50.0h**" in text
    assert "| Person | Role | Capacity | Derived | Items | Invariant |" in text
    assert "| Alice Dev | Dev | 40h | 40.0h | 2 | OK |" in text
    assert "| Bob Arch | Arch | 20h | 0h | 0 | OK |" in text
    assert "| Carol QA | QA | 10h | 10.0h | 1 | OK |" in text
    # Override column appears only when someone actually has an override
    assert "Override" not in text


def test_out_flag_overrides_output_dir(tmp_path):
    _plant_project(tmp_path)
    custom = tmp_path / "custom-out"
    proc = _run_reports(tmp_path, "PI-2026-1.1", "--out", str(custom))
    assert proc.returncode == 0, proc.stderr
    assert (custom / "timesheet-alice.md").is_file()
    assert (custom / "timesheet-team.md").is_file()
    # default location untouched apart from the planted results JSON
    assert not (_iter_dir(tmp_path) / "timesheet-team.md").exists()


def test_capacity_override_rendering(tmp_path):
    dana = {
        "id": "dana", "name": "Dana Ops", "role": "DevSecOps",
        "capacity": 32, "total_derived": 32.0,
        "capacity_baseline": 40,
        "capacity_override": {"capacity": 32, "note": "vacation"},
        "items": [
            {"id": "S-9", "level": "Story", "js": 5, "cw": 1.0, "rs": 1.0,
             "score": 5.0, "evidence": ["commit_author"],
             "ratio": 1.0, "hours": 32.0},
        ],
        "invariant_ok": True,
    }
    erik = {
        "id": "erik", "name": "Erik Dev", "role": "Dev",
        "capacity": 40, "total_derived": 40.0,
        "items": [
            {"id": "S-10", "level": "Story", "js": 5, "cw": 1.0, "rs": 1.0,
             "score": 5.0, "evidence": ["commit_author"],
             "ratio": 1.0, "hours": 40.0},
        ],
        "invariant_ok": True,
    }
    edpa = tmp_path / ".edpa"
    _plant(edpa, "PI-2026-1.1", _results("PI-2026-1.1", [dana, erik], 72.0))
    proc = _run_reports(tmp_path, "PI-2026-1.1")
    assert proc.returncode == 0, proc.stderr

    person = (_iter_dir(tmp_path) / "timesheet-dana.md").read_text(encoding="utf-8")
    assert ('- Capacity: **32h** (baseline 40h, override '
            'abs 32h (-8h vs baseline 40h) ("vacation"))') in person

    team = (_iter_dir(tmp_path) / "timesheet-team.md").read_text(encoding="utf-8")
    assert "| Person | Role | Capacity | Override | Derived | Items | Invariant |" in team
    assert ('| Dana Ops | DevSecOps | 32h | '
            'abs 32h (-8h vs baseline 40h) ("vacation") | 32.0h | 1 | OK |') in team
    # people without an override get the placeholder cell
    assert "| Erik Dev | Dev | 40h | — | 40.0h | 1 | OK |" in team


def test_pi_summary(tmp_path):
    edpa = _plant_project(tmp_path)
    _plant(edpa, "PI-2026-1.2", _results("PI-2026-1.2", [_alice()], 40.0))
    # different PI — must NOT be aggregated under PI-2026-1
    _plant(edpa, "PI-2026-2.1", _results("PI-2026-2.1", [_alice()], 40.0))

    proc = _run_reports(tmp_path, "--pi", "PI-2026-1")
    assert proc.returncode == 0, proc.stderr
    assert "2 iteration(s) aggregated" in proc.stdout

    summary = edpa / "reports" / "pi-PI-2026-1" / "pi-summary-PI-2026-1.md"
    assert summary.is_file()
    text = summary.read_text(encoding="utf-8")
    assert "# PI Summary — PI-2026-1" in text
    assert "- Iterations: PI-2026-1.1, PI-2026-1.2" in text
    assert "| Person | Role | Capacity Σ | Derived Σ | Iterations |" in text
    assert "| Alice Dev | Dev | 80h | 80.0h | 2 |" in text
    assert "| Bob Arch | Arch | 20h | 0h | 1 |" in text
    assert "| Carol QA | QA | 10h | 10.0h | 1 |" in text
    assert "- **PI-2026-1.1**: team_total=50.0h, invariants_passed=True" in text
    assert "- **PI-2026-1.2**: team_total=40.0h, invariants_passed=True" in text
    assert "PI-2026-2.1" not in text
    # e2e phase 11: the rich summary must reference every iteration of the PI
    for iter_id in ("PI-2026-1.1", "PI-2026-1.2"):
        assert iter_id in text, iter_id


def test_missing_results_exit2(project):
    proc = _run_reports(project, "PI-2026-9.9")
    assert proc.returncode == 2
    assert "engine results not found" in proc.stderr


def test_pi_without_iterations_exit2(project):
    proc = _run_reports(project, "--pi", "PI-2099-9")
    assert proc.returncode == 2
    assert "no iterations under" in proc.stderr


def test_requires_iteration_or_pi(project):
    proc = _run_reports(project)
    assert proc.returncode == 2
    assert "either an iteration ID or --pi" in proc.stderr
